import pdfplumber
import re
from datetime import datetime
from utils import get_category
import logging
logging.getLogger("pdfminer").setLevel(logging.ERROR)
def format_date(date_str):
    """Converts SBI's '09 Apr 26' format to our standard '09/04/2026'"""
    try:
        # .title() ensures 'APR' or 'apr' becomes 'Apr' to safely match %b
        dt = datetime.strptime(date_str.strip().title(), "%d %b %y")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return date_str

def parse(pdf_path, password=None):
    print(f"Parsing SBI statement: {pdf_path}...")
    transactions = []
    
    # Matches dates at the start of a line like '09 Apr 26'
    date_pattern = re.compile(r"^\s*(\d{2}\s[a-zA-Z]{3}\s\d{2})")
    
    # Matches amounts with C or D (e.g., '4.26 C', 'C 4.24', '1,499.00 D')
    amount_pattern = re.compile(r"([CD]\s*[\d,]+\.\d{2}|[\d,]+\.\d{2}\s*[CD])")
    stop_markers = (
        "Transactions highlighted",
        "Important Messages",
        "Payment Options",
        "Reward Points",
        "Total Amount Due",
        "Previous Balance",
    )

    with pdfplumber.open(pdf_path, password=password) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        card_name = "BPCL SBI Card OCTANE"

        for page in pdf.pages:
            # We use Visual Layout parsing to bypass broken table grids
            text = page.extract_text(layout=True)
            if not text: continue
            
            lines = text.split('\n')
            current_txn = None
            
            for line in lines:
                if not line.strip(): continue

                if any(marker in line for marker in stop_markers):
                    if current_txn and current_txn['amount'] is not None:
                        transactions.append(current_txn)
                    current_txn = None
                    continue

                date_match = date_pattern.search(line)
                
                # 1. Start a New Transaction
                if date_match:
                    if current_txn and current_txn['amount'] is not None:
                        transactions.append(current_txn)
                        
                    raw_date = date_match.group(1)
                    
                    current_txn = {
                        "datetime": format_date(raw_date),
                        "description": "",
                        "amount": None,
                        "type": "DEBIT",
                        "bank": "SBI",
                        "card": card_name,
                        "category": "Uncategorized"
                    }
                    
                    desc = line.replace(raw_date, "")
                    amount_match = amount_pattern.search(line)
                    
                    # If the amount is on the same line as the date
                    if amount_match:
                        raw_amount_str = amount_match.group(1)
                        is_credit = 'C' in raw_amount_str
                        clean_amt = float(re.sub(r'[^\d.]', '', raw_amount_str))
                        
                        current_txn['amount'] = clean_amt
                        current_txn['type'] = "CREDIT" if is_credit else "DEBIT"
                        desc = desc.replace(raw_amount_str, "")
                        
                    current_txn['description'] += " " + desc.strip()
                    
                # 2. Continue Transaction or Handle Sub-Transactions
                elif current_txn:
                    amount_match = amount_pattern.search(line)
                    
                    if amount_match:
                        if current_txn['amount'] is None:
                            # This is the amount for the current transaction that just wrapped to the next line
                            raw_amount_str = amount_match.group(1)
                            is_credit = 'C' in raw_amount_str
                            clean_amt = float(re.sub(r'[^\d.]', '', raw_amount_str))
                            
                            current_txn['amount'] = clean_amt
                            current_txn['type'] = "CREDIT" if is_credit else "DEBIT"
                            desc = line.replace(raw_amount_str, "")
                            current_txn['description'] += " " + desc.strip()
                        else:
                            # --- SUB-TRANSACTION DETECTED (e.g. IGST) ---
                            # We found a new amount, but there is no date on this line.
                            # Save the current transaction...
                            transactions.append(current_txn)
                            
                            # ...and start a new one inheriting the SAME date!
                            raw_amount_str = amount_match.group(1)
                            is_credit = 'C' in raw_amount_str
                            clean_amt = float(re.sub(r'[^\d.]', '', raw_amount_str))
                            desc = line.replace(raw_amount_str, "")
                            
                            current_txn = {
                                "datetime": current_txn['datetime'],
                                "description": desc.strip(),
                                "amount": clean_amt,
                                "type": "CREDIT" if is_credit else "DEBIT",
                                "bank": "SBI",
                                "card": card_name,
                                "category": "Uncategorized"
                            }
                    else:
                        # No amount found, this is just a multi-line description
                        current_txn['description'] += " " + line.strip()
                        
            # Save the last transaction hanging in the buffer at the end of the page
            if current_txn and current_txn['amount'] is not None:
                transactions.append(current_txn)

    # 3. Final Cleanup Pass
    for t in transactions:
        desc = t['description']
        # Remove stray 'C' or 'D' letters left behind by the layout engine
        desc = re.sub(r"\b[CD]\b", "", desc) 
        desc = re.sub(r"\s+", " ", desc).strip()
        
        t['description'] = desc
        t['category'] = get_category(desc)

    return transactions
