import pdfplumber
import re
from datetime import datetime
from utils import get_category

def parse(pdf_path, password=None):
    print(f"Parsing HSBC statement: {pdf_path}...")
    transactions = []
    
    # Matches dates like 07MAR, 03APR at the start of a line
    date_pattern = re.compile(r"^\s*(\d{2}[a-zA-Z]{3})")
    
    # Matches amounts like 209.00 or 1,043.00 CR
    amount_pattern = re.compile(r"([\d,]+\.\d{2})\s*(CR|Cr)?")
    
    # Extracts the end date of the statement period (e.g., "07 APR 2026")
    statement_period_pattern = re.compile(r"To\s+(\d{2}\s+[a-zA-Z]{3}\s+\d{4})", re.IGNORECASE)

    with pdfplumber.open(pdf_path, password=password) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        
        # Determine the anchor year from the statement header
        statement_end_date = datetime.now()
        year_match = statement_period_pattern.search(first_page_text.replace('\n', ' '))
        if year_match:
            try:
                statement_end_date = datetime.strptime(year_match.group(1), "%d %b %Y")
            except ValueError:
                pass
                
        card_name = "HSBC Live+"
            
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if not text: continue
            
            lines = text.split('\n')
            current_txn = None
            
            for line in lines:
                if not line.strip(): continue
                
                # --- SKIPS ---
                if "TOTAL PURCHASE OUTSTANDING" in line or "NET OUTSTANDING BALANCE" in line:
                    continue
                    
                date_match = date_pattern.search(line)
                
                # 1. Start a New Transaction
                if date_match:
                    if current_txn and current_txn['amount'] is not None:
                        transactions.append(current_txn)
                        
                    raw_date = date_match.group(1) # e.g. "07MAR"
                    
                    # --- THE TIME TRAVEL FIX ---
                    # Safely attach the year based on the statement period
                    try:
                        txn_dt = datetime.strptime(f"{raw_date}{statement_end_date.year}", "%d%b%Y")
                        # If a Dec transaction is on a Jan statement, push the transaction back 1 year
                        if txn_dt > statement_end_date:
                            txn_dt = txn_dt.replace(year=statement_end_date.year - 1)
                        formatted_date = txn_dt.strftime("%d/%m/%Y")
                    except ValueError:
                        formatted_date = raw_date
                        
                    current_txn = {
                        "datetime": formatted_date,
                        "description": "",
                        "amount": None,
                        "type": "DEBIT",
                        "bank": "HSBC",
                        "card": card_name,
                        "category": "Uncategorized"
                    }
                    
                    amount_match = amount_pattern.search(line)
                    desc = line.replace(raw_date, "")
                    
                    if amount_match:
                        full_amount_str = amount_match.group(0)
                        raw_amount_str = amount_match.group(1)
                        is_credit = bool(amount_match.group(2) and "CR" in amount_match.group(2).upper())
                        
                        clean_amt = float(re.sub(r'[^\d.]', '', raw_amount_str))
                        current_txn['amount'] = clean_amt
                        current_txn['type'] = "CREDIT" if is_credit else "DEBIT"
                        
                        desc = desc.replace(full_amount_str, "")
                        
                    current_txn['description'] += " " + desc.strip()
                    
                # 2. Continue Transaction (Multi-line wrap)
                elif current_txn:
                    amount_match = amount_pattern.search(line)
                    
                    if amount_match and current_txn['amount'] is None:
                        full_amount_str = amount_match.group(0)
                        raw_amount_str = amount_match.group(1)
                        is_credit = bool(amount_match.group(2) and "CR" in amount_match.group(2).upper())
                        
                        clean_amt = float(re.sub(r'[^\d.]', '', raw_amount_str))
                        current_txn['amount'] = clean_amt
                        current_txn['type'] = "CREDIT" if is_credit else "DEBIT"
                        
                        desc = line.replace(full_amount_str, "")
                        current_txn['description'] += " " + desc.strip()
                    else:
                        # Prevent bleeding into summary tables
                        if "ACCOUNT SUMMARY" in line or "TOTAL PURCHASE" in line:
                            transactions.append(current_txn)
                            current_txn = None
                        else:
                            current_txn['description'] += " " + line.strip()
                            
            # Save the last transaction hanging in the buffer
            if current_txn and current_txn['amount'] is not None:
                transactions.append(current_txn)
                
    # 3. Final Cleanup Pass
    for t in transactions:
        desc = t['description']
        
        # Remove masked card numbers (e.g., '43xx xxxx xxxx 8570') that HSBC injects into descriptions
        desc = re.sub(r"\b\d{2,4}[xX]{2}\s*[xX]{4}\s*[xX]{4}\s*\d{4}\b", "", desc)
        desc = re.sub(r"\s+", " ", desc).strip()
        
        t['description'] = desc
        t['category'] = get_category(desc)

    return transactions