import argparse
import os
from dotenv import load_dotenv

# Import your database saver (adjust this import to match your actual database script!)
from database import save_transactions 

# Import all your custom parsers
from parsers import hdfc, icici, axis, sbi, idfc, au, hsbc

# Silence pdfminer warnings
import logging
logging.getLogger("pdfminer").setLevel(logging.ERROR)

load_dotenv()

BANK_PARSERS = {
    "hdfc": hdfc,
    "icici": icici,
    "axis": axis,
    "sbi": sbi,
    "idfc": idfc,
    "au": au,
    "hsbc": hsbc
}

BANK_FOLDER_HINTS = {
    "hdfc": "hdfc",
    "icici": "icici",
    "axis": "axis",
    "sbi": "sbi",
    "idfc": "idfc",
    "au": "au",
    "hsbc": "hsbc",
}

def detect_bank_from_path(pdf_path):
    """Detect the parser from the PDF's folder path."""
    parts = [part.lower() for part in os.path.normpath(pdf_path).split(os.sep)]
    for hint, bank_id in BANK_FOLDER_HINTS.items():
        if any(hint in part for part in parts):
            return bank_id
    return None

def process_pdf(pdf_path, bank_id):
    """Handles the extraction and saving of a single PDF."""
    parser = BANK_PARSERS.get(bank_id)
    if not parser:
        print(f"Error: No parser found for bank '{bank_id}'")
        return False

    # Dynamically grab the password from .env (e.g., HDFC_PASS, ICICI_PASS)
    env_password_key = f"{bank_id.upper()}_PASS"
    password = os.getenv(env_password_key)

    try:
        transactions = parser.parse(pdf_path, password=password)
        if transactions:
            source_file = os.path.relpath(pdf_path)
            for source_index, transaction in enumerate(transactions):
                transaction["source_file"] = source_file
                transaction["source_index"] = source_index

            # Send the extracted transactions to your SQLite database
            inserted = save_transactions(transactions)
            print(f"Success! Saved {inserted}/{len(transactions)} transactions from {os.path.basename(pdf_path)}.")
        else:
            print(f"No transactions found in {os.path.basename(pdf_path)}.")
        return True
    except Exception as e:
        print(f"FAILED to process {os.path.basename(pdf_path)}: {type(e).__name__}: {e!r}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Parse Bank Statement PDFs into a Database.")
    parser.add_argument("path", help="Path to a single PDF file OR a folder containing PDFs")
    parser.add_argument("--bank", required=True, choices=[*BANK_PARSERS.keys(), "all"], help="Which bank's parser to use")
    
    args = parser.parse_args()
    target_path = args.path
    bank_id = args.bank.lower()
    had_failures = False

    # --- THE FOLDER LOGIC ---
    if os.path.isfile(target_path):
        # User passed a single file
        if target_path.lower().endswith(".pdf"):
            file_bank_id = detect_bank_from_path(target_path) if bank_id == "all" else bank_id
            if not file_bank_id:
                print(f"Error: Could not detect bank for {target_path}")
                had_failures = True
            elif not process_pdf(target_path, file_bank_id):
                had_failures = True
        else:
            print("Error: The provided file is not a PDF.")
            had_failures = True
            
    elif os.path.isdir(target_path):
        # User passed a folder
        print(f"Scanning folder: {target_path} for {bank_id.upper()} statements...")
        
        # Find all PDF files in the directory
        if bank_id == "all":
            pdf_files = []
            for root, _, filenames in os.walk(target_path):
                for filename in filenames:
                    if filename.lower().endswith(".pdf"):
                        pdf_files.append(os.path.join(root, filename))
        else:
            pdf_files = [
                os.path.join(target_path, f)
                for f in os.listdir(target_path)
                if f.lower().endswith('.pdf')
            ]
        
        if not pdf_files:
            print("No PDF files found in this folder.")
            return
            
        # Loop through and process them one by one
        for full_path in sorted(pdf_files):
            file_bank_id = detect_bank_from_path(full_path) if bank_id == "all" else bank_id
            if not file_bank_id:
                print(f"FAILED to process {os.path.basename(full_path)}: could not detect bank from path")
                had_failures = True
                continue
            if not process_pdf(full_path, file_bank_id):
                had_failures = True
            
    else:
        print("Error: The path provided does not exist.")
        had_failures = True

    if had_failures:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
