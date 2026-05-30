import pdfplumber
import re
from utils import get_category


def standardize_date(raw_date):
    """Converts DD/MM/YY or DD/MM/YYYY into database-friendly YYYY-MM-DD"""
    parts = raw_date.split('/')
    year = parts[2]
    # If the year is only 2 digits (e.g., '25'), make it '2025'
    if len(year) == 2:
        year = "20" + year

    return f"{year}-{parts[1]}-{parts[0]}"


def parse_amount(amount_text):
    return float(amount_text.replace(",", ""))


def compact_statement_text(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def is_savings_table_header(line):
    compact_line = compact_statement_text(line)
    return compact_line.startswith("datenarration")


def is_savings_summary_line(line):
    return compact_statement_text(line).startswith("statementsummary")


def is_savings_noise_line(line):
    line = line.strip()
    if not line:
        return True
    if re.match(r"^\d{2}/\d{2}/\d{2,4}\b", line):
        return False

    lower_line = line.lower()
    compact_line = compact_statement_text(line)

    noise_prefixes = (
        "pageno.:",
        "accountbranch",
        "address :",
        "city :",
        "state :",
        "phoneno.",
        "currency :",
        "email :",
        "custid :",
        "a/copendate",
        "jointholders",
        "rtgs/neftifsc",
        "branchcode",
        "nomination:",
        "from :",
        "date narration",
        "hdfcbanklimited",
        "*closingbalance",
        "contentsofthisstatement",
        "thisstatement.",
        "stateaccountbranchgstn",
        "hdfcbankgstinnumberdetails",
        "registeredofficeaddress",
        "thisisacomputergeneratedstatement",
        "notrequiresignature",
    )
    if lower_line.startswith(noise_prefixes):
        return True

    noise_markers = (
        "accountno",
        "accountbranch",
        "address",
        "city",
        "state",
        "phoneno",
        "odlimit",
        "currency",
        "email",
        "custid",
        "acopendate",
        "jointholders",
        "rtgsneftifsc",
        "branchcode",
        "nomination",
        "hdfcbanklimited",
        "closingbalance",
        "contentsofthisstatement",
        "hdfcbankgstinnumberdetails",
        "registeredofficeaddress",
        "thisisacomputergeneratedstatement",
        "notrequiresignature",
    )
    if any(marker in compact_line for marker in noise_markers):
        return True

    return bool(
        re.match(r"^(mr|mrs|ms|miss|dr|m/s)\.?\s+[a-z][a-z .'-]{1,80}$", lower_line)
        and not re.search(r"\d", lower_line)
    )


def infer_first_savings_txn_type(description):
    desc = description.lower()
    credit_markers = (
        "salary",
        "neftcr",
        "impscr",
        "rtgscr",
        "upi-cr",
        "interest paid",
        "cashback",
        "refund",
    )
    return "CREDIT" if any(marker in desc for marker in credit_markers) else "DEBIT"


def clean_savings_description(description):
    description = re.sub(r"\s+", " ", description).strip()
    description = re.sub(r"PAIDVIACR\s+ED", "PAIDVIACRED", description, flags=re.IGNORECASE)
    description = re.sub(r"UPIS\s+CANQR", "UPISCANQR", description, flags=re.IGNORECASE)
    return description


def parse(pdf_path, password=None):
    print(f"Parsing HDFC statement: {pdf_path}...")
    with pdfplumber.open(pdf_path, password=password) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        
        # Strict routing to prevent "PAID VIA CRED" from triggering the credit card parser
        if any(card in first_page_text for card in ["Tata Neu", "Millennia", "Credit Card", "CREDIT CARD"]):
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
            
            amount_matches = list(re.finditer(r"([+₹-]?)\s*([\d,]+\.\d{2})\s*(Cr)?", line, flags=re.IGNORECASE))
            if not amount_matches: continue
            
            date = date_match.group(1)
            last_match = amount_matches[-1]
            
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
            
            desc = line.replace(date, "")
            for match in amount_matches:
                desc = desc.replace(match.group(0), "") 
                
            desc = re.sub(r"\d{2}:\d{2}(?::\d{2})?", "", desc) 
            desc = re.sub(r"\bEMI\b", "", desc, flags=re.IGNORECASE) 
            desc = re.sub(r"\+\d+\s*$", "", desc.strip())
            desc = re.sub(r"\bCr\b\s*$", "", desc, flags=re.IGNORECASE)
            desc = re.sub(r"\b\d{1,5}\s*$", "", desc.strip())
            desc = re.sub(r"\+\s*$", "", desc.strip())
            desc = re.sub(r"\s+", " ", desc).strip()
            
            transactions.append({
                # Standardize the credit card dates to YYYY-MM-DD as well
                "datetime": standardize_date(date),
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
    Parser for HDFC Savings Accounts using text lines and closing-balance deltas.

    pdfplumber table extraction merges many HDFC rows into multi-line cells, which
    misaligns dates, narrations, withdrawal amounts, deposits, and balances. The
    visible text keeps each transaction line intact, so parse those transaction
    anchors and attach following narration continuation lines.
    """
    transactions = []
    previous_balance = None
    txn_line_pattern = re.compile(
        r"^(?P<date>\d{2}/\d{2}/\d{2,4})\s+"
        r"(?P<description>.+?)\s+"
        r"(?P<ref>[A-Z0-9]{8,})\s+"
        r"(?P<value_date>\d{2}/\d{2}/\d{2,4})\s+"
        r"(?P<amount>-?[\d,]+\.\d{2})\s+"
        r"(?P<balance>-?[\d,]+\.\d{2})$",
        flags=re.IGNORECASE,
    )
    
    for page in pdf.pages:
        text = page.extract_text() or ""
        if not text:
            continue

        in_statement_body = False
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if is_savings_summary_line(line):
                break
            if is_savings_table_header(line):
                in_statement_body = True
                continue

            txn_match = txn_line_pattern.match(line)
            if not in_statement_body and not txn_match:
                continue
            if not txn_match and is_savings_noise_line(line):
                continue

            if txn_match:
                in_statement_body = True
                amount = abs(parse_amount(txn_match.group("amount")))
                closing_balance = parse_amount(txn_match.group("balance"))
                description = clean_savings_description(txn_match.group("description"))

                if previous_balance is None:
                    txn_type = infer_first_savings_txn_type(description)
                else:
                    txn_type = "CREDIT" if closing_balance > previous_balance else "DEBIT"

                transactions.append({
                    "datetime": standardize_date(txn_match.group("date")),
                    "description": description,
                    "amount": amount,
                    "type": txn_type,
                    "bank": "HDFC",
                    "card": "Savings Account",
                    "category": get_category(
                        description,
                        bank="HDFC",
                        card="Savings Account",
                        txn_type=txn_type,
                        amount=amount,
                    ),
                })
                previous_balance = closing_balance
                continue

            if transactions:
                transactions[-1]["description"] = clean_savings_description(
                    f"{transactions[-1]['description']} {line}"
                )

    for transaction in transactions:
        transaction["description"] = clean_savings_description(transaction["description"])
        transaction["category"] = get_category(
            transaction["description"],
            bank=transaction["bank"],
            card=transaction["card"],
            txn_type=transaction["type"],
            amount=transaction["amount"],
        )

    return transactions
