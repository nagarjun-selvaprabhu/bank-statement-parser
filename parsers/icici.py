import pdfplumber
import re
from utils import get_category

def parse(pdf_path, password=None):
    print(f"Parsing ICICI statement: {pdf_path}...")
    transactions = []
    
    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages:
            # layout=True reads the text visually, preserving the spaces between columns
            text = page.extract_text(layout=True)
            if not text: continue
            
            lines = text.split('\n')
            current_txn = None
            
            for line in lines:
                if not line.strip(): continue
                
                # 1. Check if the line contains a Date (signals a transaction)
                date_match = re.search(r"(\d{2}/\d{2}/\d{4})", line)
                
                if date_match:
                    # Save previous transaction before starting this new one
                    if current_txn and current_txn['amount'] is not None:
                        transactions.append(current_txn)
                        
                    date = date_match.group(1)
                    current_txn = {
                        "datetime": date,
                        "description": "",
                        "amount": None,
                        "type": "DEBIT",
                        "bank": "ICICI",
                        "card": "Amazon Pay Credit Card",
                        "category": "Uncategorized"
                    }
                    
                    # Add everything else on this line to the description buffer
                    desc = line.replace(date, "")
                    desc = re.sub(r"\b\d{10,}\b", "", desc) # Strip the long reference numbers
                    
                    # Try to find the amount on this same line
                    # Returns a list of tuples: [('749.00', ''), ('10,477.59', 'CR')]
                    amounts = re.findall(r"([\d.,]+\.\d{2})\s*(CR)?", line)
                    if amounts:
                        raw_amount, is_cr = amounts[-1] # Grab the last matched amount
                        
                        # Clean ICICI typos (e.g., 10.477.59 becomes 10477.59)
                        clean_amt = re.sub(r'[^\d.]', '', raw_amount)
                        if clean_amt.count('.') > 1:
                            parts = clean_amt.rsplit('.', 1)
                            clean_amt = parts[0].replace('.', '') + '.' + parts[1]
                            
                        current_txn['amount'] = float(clean_amt)
                        current_txn['type'] = "CREDIT" if is_cr else "DEBIT"
                        
                        desc = desc.replace(raw_amount, "").replace("CR", "")
                        
                    current_txn['description'] += " " + desc.strip()
                    
                # 2. Handle multi-line wrapping (if the amount is on the next line)
                elif current_txn and current_txn['amount'] is None:
                    amounts = re.findall(r"([\d.,]+\.\d{2})\s*(CR)?", line)
                    
                    if amounts:
                        raw_amount, is_cr = amounts[-1]
                        clean_amt = re.sub(r'[^\d.]', '', raw_amount)
                        if clean_amt.count('.') > 1:
                            parts = clean_amt.rsplit('.', 1)
                            clean_amt = parts[0].replace('.', '') + '.' + parts[1]
                            
                        current_txn['amount'] = float(clean_amt)
                        current_txn['type'] = "CREDIT" if is_cr else "DEBIT"
                        
                        desc = line.replace(raw_amount, "").replace("CR", "")
                        current_txn['description'] += " " + desc.strip()
                    else:
                        current_txn['description'] += " " + line.strip()
                        
            # End of page: save the final transaction hanging in the buffer
            if current_txn and current_txn['amount'] is not None:
                transactions.append(current_txn)
                
    # 3. Final Polish and Categorization
    cleaned_transactions = []
    for t in transactions:
        desc = t['description']
        desc = re.sub(r"IGST-CI@18%", "IGST Fee", desc)
        # Remove the random "0" from the empty Reward Points column
        desc = re.sub(r"\b0\b", "", desc) 
        desc = re.sub(r"\s+", " ", desc).strip()

        lower_desc = desc.lower()
        if (
            "amount amortization" in lower_desc
            or "transaction/ loantype" in lower_desc
            or "outstanding amount" in lower_desc
        ):
            continue
        
        t['description'] = desc
        t['category'] = get_category(desc)
        cleaned_transactions.append(t)

    return cleaned_transactions
