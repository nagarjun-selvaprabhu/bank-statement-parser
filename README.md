# Personal Finance Statement Pipeline

A local Python pipeline for extracting credit card transactions from PDF statements, storing them in SQLite, categorizing spends, and exploring the results in a Streamlit dashboard.

The project is designed for private local use. Statement PDFs, passwords, virtual environments, and generated database files are ignored by Git.

## What It Does

- Parses statement PDFs with bank-specific `pdfplumber` parsers.
- Saves clean transactions into `expenses.db`.
- De-duplicates rows by `source_file` and `source_index`.
- Normalizes dates into `YYYY-MM-DD`.
- Auto-categorizes transactions using merchant keywords and card context.
- Provides a Streamlit dashboard with monthly, yearly, category, card, merchant, trend, heatmap, and transaction views.

## Supported Banks

- HDFC
- ICICI
- Axis
- SBI
- IDFC
- AU Bank
- HSBC

## Project Layout

```text
.
├── main.py              # CLI entry point for PDF ingestion
├── database.py          # SQLite table creation and inserts
├── utils.py             # Date normalization and category rules/updater
├── dashboard.py         # Streamlit analytics dashboard
├── parsers/             # Bank-specific PDF parsers
├── statements/          # Private local PDFs, ignored by Git
└── expenses.db          # Generated SQLite database, ignored by Git
```

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install pdfplumber python-dotenv pandas plotly streamlit
```

Create a `.env` file with statement passwords as needed:

```bash
HDFC_PASS=your_password
ICICI_PASS=your_password
AXIS_PASS=your_password
SBI_PASS=your_password
IDFC_PASS=your_password
AU_PASS=your_password
HSBC_PASS=your_password
```

Optional local-only category regexes can be added to `.env`. These patterns are matched against normalized lowercase transaction descriptions and can be separated with semicolons:

```bash
SELF_TRANSFER_PATTERNS="upi.*my own vpa"
PERSONAL_TRANSFER_PATTERNS="family transfer marker"
```

## Statement Folder Layout

For automatic bank detection, place PDFs under bank-named folders:

```text
statements/
├── hdfc/
├── icici/
├── axis/
├── sbi/
├── idfc/
├── au/
└── hsbc/
```

The folder name is used to route each PDF to the correct parser when running with `--bank all`.

## Ingest PDFs

Process all supported statements:

```bash
python main.py statements --bank all
```

Process one bank folder:

```bash
python main.py statements/hdfc --bank hdfc
```

Process one PDF:

```bash
python main.py statements/hdfc/example.pdf --bank hdfc
```

To rebuild from scratch:

```bash
rm expenses.db
python main.py statements --bank all
```

## Update Categories

Preview category changes without writing to the database:

```bash
python utils.py --dry-run
```

Apply categories to every transaction:

```bash
python utils.py
```

Categories are assigned from merchant keywords, transaction type, and card context. For example, BPCL SBI card debit transactions default to `Fuel` after more specific rules have had a chance to match.

## Run Dashboard

```bash
streamlit run dashboard.py
```

The dashboard reads from `expenses.db` and includes:

- Overall spend and credit metrics
- Month snapshot and month drilldown
- Yearly spend, credit, net outflow, and summary views
- Spend by category and credit card
- Monthly and year-over-year trends
- Category/card mix charts
- Heatmaps with INR-formatted scales
- Top merchant and frequent merchant analysis
- Largest transaction and selected-month transaction tables

## Database

Transactions are stored in the `transactions` table:

```text
id INTEGER PRIMARY KEY
bank_name TEXT
card_name TEXT
txn_datetime TEXT
description TEXT
amount REAL
txn_type TEXT
category TEXT
source_file TEXT
source_index INTEGER
```

`source_file` and `source_index` are unique together, so re-running ingestion does not duplicate already-saved transactions.

## Useful Integrity Checks

Run quick checks with SQLite:

```bash
sqlite3 expenses.db "SELECT bank_name, COUNT(*) FROM transactions GROUP BY bank_name ORDER BY bank_name;"
```

```bash
sqlite3 expenses.db "SELECT * FROM transactions WHERE amount IS NULL OR amount <= 0 OR amount > 1000000;"
```

```bash
sqlite3 expenses.db "SELECT * FROM transactions WHERE txn_datetime NOT GLOB '????-??-??';"
```

```bash
sqlite3 expenses.db "SELECT id, bank_name, card_name, description FROM transactions WHERE description IS NULL OR TRIM(description) = '';"
```

## Notes

- Keep `statements/`, `.env`, and `expenses.db` private.
- Parser fixes should be made in the relevant file under `parsers/`.
- Category fixes should usually be made in `utils.py`, then applied with `python utils.py`.
- If parser logic changes significantly, rebuild the database from scratch so every transaction is extracted consistently.
