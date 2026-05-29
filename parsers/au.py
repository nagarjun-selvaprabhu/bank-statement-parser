import pdfplumber
import re
from datetime import datetime
from utils import get_category

MONTHS = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"}

def format_modern_date(day, month, year):
    try:
        dt = datetime.strptime(f"{day} {month} {year}", "%d %b %y")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return ""

def same_line(words, text_a, text_b):
    for first in words:
        if first["text"].lower() != text_a:
            continue
        for second in words:
            if second["text"].lower() == text_b and abs(second["top"] - first["top"]) <= 3:
                return first["top"]
    return None

def parse_modern_layout(pdf, card_name):
    transactions = []

    for page in pdf.pages:
        words = page.extract_words(keep_blank_chars=False) or []
        if not words:
            continue

        start_y = same_line(words, "your", "transactions")
        if start_y is None:
            continue
        start_y += 20

        stop_candidates = [
            y for y in (
                same_line(words, "reward", "points"),
                same_line(words, "just", "so"),
            )
            if y is not None and y > start_y
        ]
        end_y = min(stop_candidates) if stop_candidates else 790

        for day_word in sorted(words, key=lambda word: (word["top"], word["x0"])):
            if not re.fullmatch(r"\d{2}", day_word["text"]):
                continue
            if not (start_y <= day_word["top"] <= end_y and 35 <= day_word["x0"] <= 47):
                continue

            lower_row_words = [
                word for word in words
                if day_word["top"] + 10 <= word["top"] <= day_word["top"] + 24
            ]
            month_word = next(
                (
                    word for word in lower_row_words
                    if 28 <= word["x0"] <= 42 and word["text"].lower()[:3] in MONTHS
                ),
                None,
            )
            if not month_word:
                continue
            year_word = next(
                (
                    word for word in lower_row_words
                    if 43 <= word["x0"] <= 60
                    and abs(word["top"] - month_word["top"]) <= 3
                    and re.fullmatch(r"\d{2}", word["text"])
                ),
                None,
            )
            type_word = next(
                (
                    word for word in lower_row_words
                    if 65 <= word["x0"] <= 90
                    and abs(word["top"] - month_word["top"]) <= 3
                    and word["text"].lower() in {"cr", "dr"}
                ),
                None,
            )
            amount_word = next(
                (
                    word for word in words
                    if word["x0"] >= 480
                    and abs(word["top"] - day_word["top"]) <= 5
                    and re.search(r"[\d,]+\.\d{2}", word["text"])
                ),
                None,
            )
            if not (year_word and type_word and amount_word):
                continue

            amount_match = re.search(r"[\d,]+\.\d{2}", amount_word["text"])
            if not amount_match:
                continue
            amount = float(amount_match.group(0).replace(",", ""))

            desc_words = [
                word for word in words
                if 60 <= word["x0"] < amount_word["x0"] - 3
                and day_word["top"] - 8 <= word["top"] <= day_word["top"] + 5
            ]
            desc = " ".join(word["text"] for word in sorted(desc_words, key=lambda word: word["x0"]))
            desc = re.sub(r"\s+", " ", desc).strip()
            if not desc:
                continue

            date = format_modern_date(day_word["text"], month_word["text"], year_word["text"])
            if not date:
                continue

            transactions.append({
                "datetime": date,
                "description": desc,
                "amount": amount,
                "type": "CREDIT" if type_word["text"].lower() == "cr" else "DEBIT",
                "bank": "AU Bank",
                "card": card_name,
                "category": get_category(desc)
            })

    return transactions

def parse(pdf_path, password=None):
    transactions = []
    
    # FIX: Allows optional spaces around the slashes (e.g., "28 / 10 / 2024" or "28/10/2024")
    date_pattern = re.compile(r"(\d{2}\s*/\s*\d{2}\s*/\s*\d{4})")
    
    # Matches AU's squished amount format
    amount_pattern = re.compile(r"([\d,]+\.\d{2})\s*(Cr\.|Dr\.|Cr|Dr)", re.IGNORECASE)

    with pdfplumber.open(pdf_path, password=password) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        
        card_name = "AU Bank Credit Card"
        if "ixigo" in first_page_text.lower() or "ixigo" in pdf_path.lower():
            card_name = "ixigo AU Credit Card"
        elif "zenith" in first_page_text.lower():
            card_name = "AU Zenith Credit Card"
        elif "vetta" in first_page_text.lower():
            card_name = "AU Vetta Credit Card"
            
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if not text: continue
            
            lines = text.split('\n')
            current_txn = None
            
            for line in lines:
                if not line.strip(): continue
                
                date_match = date_pattern.search(line)
                
                # 1. Start a New Transaction
                if date_match:
                    if current_txn and current_txn['amount'] is not None:
                        transactions.append(current_txn)
                        
                    raw_date_with_spaces = date_match.group(1)
                    # Standardize the date back to DD/MM/YYYY
                    clean_date = raw_date_with_spaces.replace(" ", "")
                    
                    current_txn = {
                        "datetime": clean_date,
                        "description": "",
                        "amount": None,
                        "type": "DEBIT",
                        "bank": "AU Bank",
                        "card": card_name,
                        "category": "Uncategorized"
                    }
                    
                    amount_match = amount_pattern.search(line)
                    
                    if amount_match:
                        full_amount_str = amount_match.group(0) 
                        raw_amount_str = amount_match.group(1)  
                        cr_dr_tag = amount_match.group(2).upper()
                        
                        chop_index = line.find(full_amount_str) + len(full_amount_str)
                        clean_line = line[:chop_index]
                        
                        desc = clean_line.replace(raw_date_with_spaces, "").replace(full_amount_str, "")
                        
                        clean_amt = float(re.sub(r'[^\d.]', '', raw_amount_str))
                        current_txn['amount'] = clean_amt
                        current_txn['type'] = "CREDIT" if "CR" in cr_dr_tag else "DEBIT"
                        
                    else:
                        desc = line.replace(raw_date_with_spaces, "")
                        
                    current_txn['description'] += " " + desc.strip()
                    
                # 2. Continue Transaction (Multi-line wrap)
                elif current_txn:
                    amount_match = amount_pattern.search(line)
                    if amount_match and current_txn['amount'] is None:
                        full_amount_str = amount_match.group(0)
                        raw_amount_str = amount_match.group(1)
                        cr_dr_tag = amount_match.group(2).upper()
                        
                        chop_index = line.find(full_amount_str) + len(full_amount_str)
                        clean_line = line[:chop_index]
                        
                        desc = clean_line.replace(full_amount_str, "")
                        
                        clean_amt = float(re.sub(r'[^\d.]', '', raw_amount_str))
                        current_txn['amount'] = clean_amt
                        current_txn['type'] = "CREDIT" if "CR" in cr_dr_tag else "DEBIT"
                        
                        current_txn['description'] += " " + desc.strip()
                    else:
                        if "Transaction Summary" in line or "Reward Point" in line or "Total Amount Due" in line:
                            transactions.append(current_txn)
                            current_txn = None
                        else:
                            current_txn['description'] += " " + line.strip()
                        
            # Save the last transaction
            if current_txn and current_txn['amount'] is not None:
                transactions.append(current_txn)

        if not transactions:
            transactions = parse_modern_layout(pdf, card_name)
                
    # 3. Final Cleanup Pass
    for t in transactions:
        desc = t['description']
        desc = re.sub(r"\bConvert to EMI\b", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\bDr\.\b|\bCr\.\b", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\s+", " ", desc).strip()
        
        t['description'] = desc
        t['category'] = get_category(desc)

    return transactions
