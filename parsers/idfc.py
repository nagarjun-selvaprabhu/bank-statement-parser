import pdfplumber
import re
from datetime import datetime
from utils import get_category

def format_idfc_date(date_str):
    """Converts IDFC's '18 Apr 26' into standard '18/04/2026'"""
    date_str = date_str.strip().title()
    try:
        dt = datetime.strptime(date_str, "%d %b %y")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return date_str

def parse(pdf_path, password=None):
    transactions = []
    
    # IDFC statements use both "18 Apr 26" and "18/04/2026" date formats.
    date_pattern = re.compile(r"^\s*(\d{2}\s[a-zA-Z]{3}\s\d{2}|\d{2}/\d{2}/\d{2,4})")
    
    # Matches amounts ending in CR or DR (e.g., '11,361.00 DR')
    amount_pattern = re.compile(r"([\d,]+\.\d{2})\s*(CR|DR|Cr|Dr)")

    with pdfplumber.open(pdf_path, password=password) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        
        card_name = "IDFC Credit Card"
        if "Select" in first_page_text or "SELECT" in first_page_text:
            card_name = "IDFC FIRST Select"
        elif "Millennia" in first_page_text or "MILLENNIA" in first_page_text:
            card_name = "IDFC FIRST Millennia"
            
        in_transactions_section = False
            
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False)
            if not words: continue
            
            # Group words by Y-axis to prevent columns from blurring together
            lines_dict = {}
            for word in words:
                matched_y = None
                for y in lines_dict.keys():
                    if abs(y - word['top']) <= 4:
                        matched_y = y
                        break
                if matched_y is None:
                    lines_dict[word['top']] = [word]
                else:
                    lines_dict[matched_y].append(word)
                    
            for y in sorted(lines_dict.keys()):
                line_words = sorted(lines_dict[y], key=lambda w: w['x0'])
                line = " ".join([w['text'] for w in line_words])
                
                # --- SECTION TRIGGERS ---
                if "YOUR TRANSACTIONS" in line or "Transaction Details" in line:
                    in_transactions_section = True
                    continue
                if "REWARD POINTS SUMMARY" in line or "IMPORTANT INFORMATION" in line:
                    in_transactions_section = False
                    
                if not in_transactions_section:
                    continue
                    
                # Skip internal table headers that get merged into descriptions
                if "Purchases, EMIS & Other" in line or "Payments & Other Credits" in line:
                    continue

                date_match = date_pattern.search(line)
                
                if date_match:
                    amount_match = amount_pattern.search(line)
                    if not amount_match: continue
                        
                    raw_date = date_match.group(1)
                    full_amount_str = amount_match.group(0) # e.g., "1,181.89 CR"
                    raw_amount_str = amount_match.group(1) # e.g., "1,181.89"
                    cr_dr_tag = amount_match.group(2).upper()
                    
                    # --- CHOP OFF AD TEXT ---
                    # Delete any text that appears after the CR/DR tag
                    chop_index = line.find(full_amount_str) + len(full_amount_str)
                    clean_line = line[:chop_index]
                    
                    desc = clean_line.replace(raw_date, "").replace(full_amount_str, "")
                    amount_x = next(
                        (word["x0"] for word in line_words if word["text"] == raw_amount_str),
                        500,
                    )
                    nearby_desc_words = [
                        word
                        for word in words
                        if abs(word["top"] - y) <= 6
                        and 75 < word["x0"] < amount_x - 3
                    ]
                    nearby_desc = " ".join(
                        word["text"]
                        for word in sorted(
                            nearby_desc_words,
                            key=lambda word: (word["top"], word["x0"]),
                        )
                    )
                    if nearby_desc.strip():
                        desc = nearby_desc
                    
                    is_credit = "CR" in cr_dr_tag
                    clean_amt = float(re.sub(r'[^\d.]', '', raw_amount_str))
                    
                    # Clean up description
                    desc = re.sub(r"\bConvert\b", "", desc, flags=re.IGNORECASE)
                    desc = re.sub(r"\b\d{10,}\b", "", desc) # Remove long UPI reference numbers
                    desc = re.sub(r"\s+", " ", desc).strip()

                    if not desc:
                        continue
                    
                    transactions.append({
                        "datetime": format_idfc_date(raw_date),
                        "description": desc,
                        "amount": clean_amt,
                        "type": "CREDIT" if is_credit else "DEBIT",
                        "bank": "IDFC",
                        "card": card_name,
                        "category": get_category(desc)
                    })

    return transactions
