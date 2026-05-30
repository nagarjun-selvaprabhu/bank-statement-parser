import pdfplumber
import re
from utils import get_category

def parse(pdf_path, password=None):
    print(f"Parsing Axis statement: {pdf_path}...")
    transactions = []
    
    # Matches dates like 16/04/2026 at the start of a line
    date_pattern = re.compile(r"^\s*(\d{2}/\d{2}/\d{4})")
    
    # Matches amounts ending in Cr or Dr (e.g., '579.00 Dr', '1,920.48 Cr')
    amount_pattern = re.compile(r"([\d,]+\.\d{2})\s*(Cr|Dr|CR|DR)")

    with pdfplumber.open(pdf_path, password=password) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        
        # Dynamically detect the Axis Card variant
        card_name = "Axis Bank Credit Card"
        if "Airtel" in first_page_text:
            card_name = "Axis Bank Airtel"
        elif "Neo" in first_page_text:
            card_name = "Axis Bank Neo"
        elif "Ace" in first_page_text:
            card_name = "Axis Bank Ace"
            
        in_transactions = False
            
        for page in pdf.pages:
            # layout=True preserves visual spaces
            text = page.extract_text(layout=True)
            if not text: continue
            
            lines = text.split('\n')
            current_txn = None
            
            for line in lines:
                if not line.strip(): continue
                
                # --- SECTION TRIGGERS ---
                # Start parsing when we hit the table header
                if "TRANSACTION DETAILS" in line and "AMOUNT" in line:
                    in_transactions = True
                    continue
                # Stop parsing when we hit the end of the statement or rewards section
                if "**** End of Statement" in line or "CASHBACK DETAILS" in line or "EDGE REWARDS" in line:
                    in_transactions = False
                    
                if not in_transactions:
                    continue
                    
                # Skip sub-headers injected inside the table
                is_name_header = (
                    re.search(r"\bName\b", line, flags=re.IGNORECASE)
                    and not date_pattern.search(line)
                    and not amount_pattern.search(line)
                )
                if "Card No:" in line or is_name_header:
                    continue

                date_match = date_pattern.search(line)
                
                # 1. Start a New Transaction
                if date_match:
                    if current_txn and current_txn['amount'] is not None:
                        transactions.append(current_txn)
                        
                    raw_date = date_match.group(1)
                    current_txn = {
                        "datetime": raw_date,
                        "description": "",
                        "amount": None,
                        "type": "DEBIT",
                        "bank": "Axis",
                        "card": card_name,
                        "category": "Uncategorized"
                    }
                    
                    desc = line.replace(raw_date, "")
                    amount_match = amount_pattern.search(line)
                    
                    if amount_match:
                        raw_amount_str = amount_match.group(1)
                        cr_dr_tag = amount_match.group(2).upper()
                        clean_amt = float(re.sub(r'[^\d.]', '', raw_amount_str))
                        
                        current_txn['amount'] = clean_amt
                        current_txn['type'] = "CREDIT" if "CR" in cr_dr_tag else "DEBIT"
                        
                        desc = desc.replace(amount_match.group(0), "")
                        
                    current_txn['description'] += " " + desc.strip()
                    
                # 2. Continue Transaction (Multi-line wrap)
                elif current_txn:
                    amount_match = amount_pattern.search(line)
                    if amount_match and current_txn['amount'] is None:
                        raw_amount_str = amount_match.group(1)
                        cr_dr_tag = amount_match.group(2).upper()
                        clean_amt = float(re.sub(r'[^\d.]', '', raw_amount_str))
                        
                        current_txn['amount'] = clean_amt
                        current_txn['type'] = "CREDIT" if "CR" in cr_dr_tag else "DEBIT"
                        
                        desc = line.replace(amount_match.group(0), "")
                        current_txn['description'] += " " + desc.strip()
                    else:
                        current_txn['description'] += " " + line.strip()
                        
            # Save the last transaction hanging in the buffer at the end of the page
            if current_txn and current_txn['amount'] is not None:
                transactions.append(current_txn)
                
    # 3. Final Cleanup Pass
    for t in transactions:
        desc = t['description']
        # Axis sometimes squishes the Merchant Category (like 'UTILITIES') into the description. 
        # This is actually great for our keyword categorizer, so we just normalize the spaces.
        desc = re.sub(r"\s+", " ", desc).strip()
        
        t['description'] = desc
        t['category'] = get_category(desc)

    return transactions
