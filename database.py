import sqlite3
import logging
from datetime import datetime
from utils import get_category, normalize_date

DB_FILE = "expenses.db"

def init_db(db_name=DB_FILE):
    """Initializes the database and creates the table if it doesn't exist."""
    # Using 'with' automatically handles closing the connection when done
    with sqlite3.connect(db_name) as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_name TEXT,
                card_name TEXT,
                txn_datetime TEXT,
                description TEXT,
                amount REAL,
                txn_type TEXT,
                category TEXT,
                source_file TEXT,
                source_index INTEGER,
                UNIQUE(source_file, source_index)
            )
        ''')
        conn.commit()

def save_transactions(transactions, db_name=DB_FILE):
    """Saves a list of transactions to the database safely."""
    if not transactions:
        return 0
        
    # Ensure the DB exists before trying to save (acts as a safety net)
    init_db(db_name)
    
    inserted = 0
    
    try:
        # Opens a fresh connection for this specific file, then closes it when done
        with sqlite3.connect(db_name) as conn:
            cursor = conn.cursor()
            
            for txn in transactions:
                try:
                    description = txn.get('description', '').strip()
                    amount = txn.get('amount', 0.0)
                    txn_datetime = normalize_date(txn.get('datetime', ''))

                    if not description or amount is None:
                        continue

                    try:
                        amount = float(amount)
                    except (TypeError, ValueError):
                        continue

                    if amount <= 0:
                        continue

                    try:
                        datetime.strptime(txn_datetime, "%Y-%m-%d")
                    except ValueError:
                        logging.warning(f"Skipping row with invalid date: {txn_datetime}")
                        continue

                    cursor.execute('''
                        INSERT OR IGNORE INTO transactions 
                        (bank_name, card_name, txn_datetime, description, amount, txn_type, category, source_file, source_index)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        txn.get('bank', 'Unknown'), 
                        txn.get('card', 'N/A'), 
                        txn_datetime, 
                        description, 
                        amount, 
                        txn.get('type', 'DEBIT'), 
                        get_category(
                            description,
                            bank=txn.get('bank', 'Unknown'),
                            card=txn.get('card', 'N/A'),
                            txn_type=txn.get('type', 'DEBIT'),
                            amount=amount,
                        ),
                        txn.get('source_file'),
                        txn.get('source_index')
                    ))
                    
                    if cursor.rowcount > 0: 
                        inserted += 1
                        
                except sqlite3.Error as e:
                    logging.error(f"Failed to insert row: {e}")
                    continue
                    
            conn.commit()
            
    except sqlite3.Error as e:
        logging.error(f"Database connection error: {e}")
        
    return inserted
