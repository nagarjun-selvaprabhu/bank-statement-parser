import pdfplumber
import re
from utils import get_category

def parse(pdf_path, password=None):
    print(f"Parsing HDFC statement: {pdf_path}...")
    with pdfplumber.open(pdf_path, password=password) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        
        # Route to the correct parser based on document keywords
        if any(card in first_page_text for card in ["Tata Neu", "Millennia", "Credit Card", "CREDIT"]):
            print("Detected HDFC Credit Card format...")
            return parse_hdfc_credit(pdf, first_page_text)
        else:
            print("Detected HDFC Savings Account format...")
            return parse_hdfc_savings(pdf)

def parse_hdfc_credit(pdf, first_page_text=""):
    transactions = []
    date_pattern = re.compile(r"(\d{2}/\d{2}/\d{4})")
    
    card_name = "HDFC Credit Card"
    if "Tata Neu" in first_page_text:
        card_name = "Tata Neu Infinity"
    elif "Millennia" in first_page_text:
        card_name = "Millennia"

    for page in pdf.pages:
        words = page.extract_words(keep_blank_chars=False)
        if not words: continue
        
        lines_dict = {}
        for word in words:
            matched_y = None
            for y in lines_dict.keys():
                if abs(y - word['top']) <= 6:
                    matched_y = y
                    break
            if matched_y is None:
                lines_dict[word['top']] = [word]
            else:
                lines_dict[matched_y].append(word)
                
        for y in sorted(lines_dict.keys()):
            line_words = sorted(lines_dict[y], key=lambda w: w['x0'])
            line = " ".join([w['text'] for w in line_words])
            
            # Clean out stray PDF artifacts before looking for amounts
            line = re.sub(r"[|l]", "", line)
            line = re.sub(r"\bC\b", " ", line) 
            line = re.sub(r"ווייון", "", line) 
            line = re.sub(r"\s+", " ", line).strip()

            lower_line = line.lower()
            if (
                "in case you wish" in lower_line
                or "persona detais" in lower_line
                or "personal details" in lower_line
                or "write a etter" in lower_line
                or "write a letter" in lower_line
            ):
                continue
            
            if len(line) < 10 or not re.search(r"\d", line): continue
            
            date_match = date_pattern.search(line)
            if not date_match: continue
            
            # Split the sign / CR suffix from the amount.
            # E.g., "+ 18,502.00" or "18,502.00Cr" are both credits.
            amount_matches = list(re.finditer(r"([+₹-]?)\s*([\d,]+\.\d{2})\s*(Cr)?", line, flags=re.IGNORECASE))
            if not amount_matches: continue
            
            date = date_match.group(1)
            last_match = amount_matches[-1] # The actual transaction is the last amount on the line
            
            sign = last_match.group(1)
            raw_amount_str = last_match.group(2)
            credit_suffix = last_match.group(3)
            
            clean_amount = raw_amount_str.replace(',', '')
            try:
                amount = float(clean_amount)
            except ValueError:
                continue

            if amount <= 0:
                continue
                
            txn_type = "CREDIT" if sign == "+" or credit_suffix else "DEBIT"
            
            # Clean up the description
            desc = line.replace(date, "")
            # Remove all amounts from description
            for match in amount_matches:
                desc = desc.replace(match.group(0), "") 
                
            desc = re.sub(r"\d{2}:\d{2}(?::\d{2})?", "", desc) 
            desc = re.sub(r"\bEMI\b", "", desc, flags=re.IGNORECASE) 
            desc = re.sub(r"\+\d+\s*$", "", desc.strip()) # Remove trailing NeuCoins like "+45"
            desc = re.sub(r"\bCr\b\s*$", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"\b\d{1,5}\s*$", "", desc.strip()) # Remove trailing reward/cashback counts
            desc = re.sub(r"\+\s*$", "", desc.strip())
            desc = re.sub(r"\s+", " ", desc).strip()
            
            transactions.append({
                "datetime": date,
                "description": desc,
                "amount": amount,
                "type": txn_type,
                "bank": "HDFC",
                "card": card_name,
                "category": get_category(desc)
            })
            
    return transactions

def parse_hdfc_savings(pdf):
    """
    Parser for HDFC Savings Accounts using Balance Tracking to detect Credit vs Debit.
    """
    transactions = []
    date_pattern = re.compile(r"^(\d{2}/\d{2}/\d{2,4})\s+(.+)")
    previous_balance = None
    
    for page in pdf.pages:
        text = page.extract_text()
        if not text: continue
        
        for line in text.split('\n'):
            match = date_pattern.match(line)
            if match:
                date = match.group(1)
                rest_of_line = match.group(2)
                amounts = re.findall(r"([\d,]+\.\d{2})", rest_of_line)
                
                if len(amounts) >= 2:
                    balance = float(amounts[-1].replace(',', ''))
                    txn_amount = float(amounts[-2].replace(',', ''))
                    
                    if previous_balance is not None:
                        txn_type = "CREDIT" if balance > previous_balance else "DEBIT"
                    else:
                        txn_type = "CREDIT" if "CREDIT" in line.upper() or "NEFT" in line.upper() else "DEBIT"
                        
                    previous_balance = balance
                    
                    # Clean up description
                    desc = rest_of_line
                    for amt in amounts:
                        desc = desc.replace(amt, "")
                    desc = re.sub(r"\d{2}/\d{2}/\d{2,4}", "", desc)
                    
                    transactions.append({
                        "datetime": date,
                        "description": desc.strip(),
                        "amount": txn_amount,
                        "type": txn_type,
                        "bank": "HDFC",
                        "card": "Savings Account",
                        "category": get_category(desc.strip())
                    })
                    
    return transactions
