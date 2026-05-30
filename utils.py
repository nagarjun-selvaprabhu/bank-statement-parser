import argparse
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

DB_FILE = "expenses.db"


def normalize_date(date_text):
    """Return an ISO YYYY-MM-DD date string for known statement date formats."""
    if not date_text:
        return ""

    date_text = str(date_text).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d %b %Y", "%d %b %y"):
        try:
            return datetime.strptime(date_text.title(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return date_text


def normalize_merchant_text(text):
    """Normalize noisy PDF merchant strings for keyword matching."""
    text = (text or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def has_regex(text, patterns):
    for pattern in patterns:
        try:
            if re.search(pattern, text):
                return True
        except re.error:
            continue
    return False


def env_regex_patterns(name):
    """Return optional local-only regexes from a semicolon or newline separated env var."""
    raw_patterns = os.getenv(name, "")
    return [
        pattern.strip()
        for pattern in re.split(r"[;\n]+", raw_patterns)
        if pattern.strip() and not pattern.strip().startswith("#")
    ]


PAYMENT_KEYWORDS = [
    "autopay thank you", "autopay returned", "payment received", "payment recieved",
    "credit card payment", "bbps payment", "bbps pmt", "billdesk bbps cc payment",
    "pymnt rcv", "online pymt", "netbanking transfer", "imps pmt", "mb ib payment",
    "upi payment received", "cred visa direct", "billdesk cc payment",
]

CREDIT_CARD_PAYMENT_KEYWORDS = [
    "autopay thank you", "autopay returned", "payment received", "payment recieved",
    "credit card payment", "bbps payment", "bbps pmt", "billdesk bbps cc payment",
    "pymnt rcv", "online pymt", "mb ib payment", "cred visa direct",
    "billdesk cc payment", "paymentoncred", "cred club", "credclub",
    "cred club axisb", "cred club cred", "autopaysi", "cc0000",
]

INTERNAL_TRANSFER_KEYWORDS = [
    "netbanking transfer", "imps pmt", "upi payment received",
]

SELF_TRANSFER_PATTERNS = [
    r"\b(neft|neftcr|imps|impscr|rtgs|rtgscr|upi)\b.*\bself\b",
    r"\bself\b.*\b(neft|neftcr|imps|impscr|rtgs|rtgscr|upi)\b",
    r"\bown\s+account\b",
]

PERSONAL_TRANSFER_PATTERNS = []

PF_WITHDRAWAL_KEYWORDS = [
    "employeeprovident", "provident fund", "providentf und", "epfo",
]

TAX_REFUND_KEYWORDS = [
    "itdtaxrefund", "tax refund", "income tax refund",
]

INCOME_KEYWORDS = [
    "salary", "neftcr", "impscr", "rtgscr", "interest paid",
]

INTERNAL_CATEGORIES = {
    "Credit Card Payments",
    "Internal Transfers",
    "Personal Transfers",
    "Payments",
}

EARNING_CATEGORIES = {
    "Income",
    "PF Withdrawals",
    "Tax Refunds",
}

REWARD_KEYWORDS = [
    "cashback", "surcharge waiver", "reward redemption", "reward points",
]

REFUND_KEYWORDS = [
    "refund", "reversal", "reversed", "return",
]

FEE_KEYWORDS = [
    "igst", "gst charges", "interest on emi", "late payment", "fee", "charges",
    "merchant emi", "emi interest", "emi debit", "finance charge",
    "cgst", "sgst", "gst",
]

FUEL_KEYWORDS = [
    "fuel", "petro", "bpcl", "hpcl", "iocl", "indian oil", "shell", "bharat petroleum",
    "agency", "agencies", "agencie", "rvs fuel", "sarath fuels", "sreeram agency",
    "sri balaji agency", "radha agencies", "essar", "rammohan kaliappan sub",
    "n rangarajan and co", "subash rakesh", "babu chennai", "babu kanchipuram",
    "murugan energy", "ashok service station",
]

EDUCATION_KEYWORDS = [
    "educational", "academy", "physicswallah", "cerebellum", "university",
    "college", "school", "course", "madras university", "jaya educational",
]

HEALTH_KEYWORDS = [
    "hospital", "medical", "medicals", "pharmacy", "pharma", "nursing",
    "clinic", "doctor", "tata1mg", "1mghealth", "apollo", "aakash",
    "stanley medical", "ent research", "dr kamakshi", "sujatha medicals",
    "tamilnadu medicals", "optival health", "apoo hospitas", "apoo main hospita", "ahel hbp",
    "med store", "sugah healthcorp", "dr agarwal", "health glow", "tata 1mg", "medplus",
]

PETS_KEYWORDS = [
    "pet clinic", "pet shop", "heads up for tails", "tails", "bruno s wild",
]

HOUSING_KEYWORDS = [
    "pzrent", " rent ", "casagrand", "danub homes", "damro furniture",
    "wakefit", "urbanclap", "urbancap", "urban company", "urban clap",
    "nobroker", "furniture", "ikea", "realty", "properties",
]

JEWELRY_KEYWORDS = [
    "titan company", "thangamaligai", "jewelry", "jewellery", "jewel", "nageen",
    "bangels", "bangles",
]

INSURANCE_KEYWORDS = [
    "insurance", "oriental insurance",
]

FOOD_KEYWORDS = [
    "zomato", "swiggy", "eatsure", "dineout", "restaurant", "restaurants",
    "cafe", "bakery", "biryani", "buhari", "kfc", "mcdonald", "mc donald",
    "starbucks", "pizza", "taco bell", "nandhana", "geetham", "old mirchi",
    "hot chips", "brundhavan", "kora cafe", "mirudulas", "saravana bhavan",
    "nithya amirtham", "moddys", "district dining", "mr mc mart and cafe",
    "queen cafe", "irani tea", "alif biriyani", "veg bhavan", "biskoth",
    "freshbuyseafoods", "pwc eatsure", "thindal cafe", "food", "dining",
    "popeyes", "krispy", "bilal", "thalappakatti", "gourmet", "crescent",
    "hotel prayag", "turban", "adyar ananda", "junior kuppanna", "rb bakes",
    "andhra annam", "kakada", "chaayos", "hot breads", "durga bhavan",
    "ruchi classic", "national durbar", "leather bar", "toscano", "faruuzi",
    "pulusu", "anjappar", "rangis chinese", "venu biriyani", "abids",
    "nizam", "ibaco", "spicy paradise", "the paradise", "bhojohori",
    "vasanta bhavan", "pandias", "old madras baking", "french loaf",
    "pallavaram yaa", "hotel sangam", "banana leaf", "hotel amutha",
    "shree mithai", "sunrise beverages", "five five shack", "silver peppers",
    "rebe marketplace", "rebel marketplace", "comrades kitchen", "cha republic",
    "doddabetta teea", "manoj bhavan", "hotel sea emperor", "picaroons",
    "rebe marketpace", "fb cakes", "california burrito", "murugan idli",
    "sangeetha veg", "costa", "veetu suvai", "vidyarthi bhavan",
    "sri krishna sweets", "fig and focaccia", "ovenstory", "sardar refreshment",
    "atho ", "milkyway", "hotel parijatha", "ambur star", "bread basket",
    "tirunelveli parotta", "london waffle", "fruitbae", "eversub",
    "shah ghouse", "al arabian", "biriyani", "wallajah", "sree saravan",
    "liu s waldrof", "srinivasa dairy", "nahdi",
]

GROCERY_KEYWORDS = [
    "bigbasket", "blinkit", "instamart", "zepto", "dmart", "avenue supermarts",
    "super market", "supermarket", "reliance retail", "reliance smart",
    "family mart", "fruits", "vegetab", "grocery", "groceries",
    "dhanaakshmi stores", "freshbuy", "nilgiris", "lakshmirams",
    "innovative retail", "smart bazaar", "dhanalakshmi stores",
    "kodai spices", "7 11", "reliance retai", "reiance retai",
    "retai cc", "innovativeretai", "5starssuper", "max hypermarket",
    "reliance fresh", "santhisuperstore", "kanan devan", "kdhp",
    "blink commerce", "hd proteins", "hd protiens", "proteins",
]

TRAVEL_KEYWORDS = [
    "irctc", "railway", "ixigo", "yatra", "ease my trip", "easemytrip",
    "agoda", "airasia", "scoot", "ctrip", "makemytrip", "indigo",
    "uber", "ola", "rapido", "tnstc", "adani one", "le travenues",
    "hotel narmada", "aeseo hotels", "jpri hotels", "metro rail", "cmrl",
    "chennai metro", "parking", "airport", "bus terminal",
    "abhibus", "adani one", "zoomcar", "national highways", "fastag",
    "trave cub lounge", "phuket", "bangkok", "safari world", "sunflower phuket",
    "dnc holidays", "tourism", "ibibo", "zostel", "raj residency",
    "narmada group of hotel", "opdss hotels", "hotel resort", "golden tree",
    "adanione", "travel retail", "trv ", "motel highway", "avenues national highwa",
    "travel club lounge", "domestic lounge", "internationa loun", "lounge",
    "hotel shirose", "savera industries", "la hospin hotels",
    "raiway", "discovery mumbai",
]

ENTERTAINMENT_KEYWORDS = [
    "pvr", "inox", "bookmyshow", "book my show", "district movie",
    "wasteland entertainment", "paystationnetwork", "tiger kingdom",
    "epic 7", "youtube", "spotify", "playstation", "gamenation",
    "timezone", "marine kingdom", "cinema", "cinemas", "entertainment",
    "kg entertainment", "sangam cinemas", "mvr cinemas", "raintree recreation",
    "funcity", "vettri theatres", "google play", "times prime",
]

UTILITY_KEYWORDS = [
    "airtel", "reliance jio", "myjio", "jio", "hathway", "electricity",
    "bescom", "act fibernet", "broadband", "mobile bill", "utilities",
    "tata sky", "tata play", "tataplay", "tangedco", "atria convergence",
    "pay thamizhaga interne",
]

WALLET_KEYWORDS = [
    "paytm", "tatapayments", "tata payments", "qwikcilver", "qwickcilver",
    "gyftr", "gift card", "billdesk", "payu payments", "payu ",
    "autopepaymentsolutions", "atom technologies", "nbesbiepay",
    "one97 communications",
]

BEAUTY_KEYWORDS = [
    "naturals", "salon", "spa", "toni guy", "nykaa", "fsn brands",
    "fsnecommerce", "cosmetic", "lenskart", "envi", "sri rameshwar cosmetic",
    "sephora", "toni and guy",
]

APPAREL_KEYWORDS = [
    "myntra", "zudio", "life style", "lifestyle", "chennai silks", "pothys",
    "sarees", "saree", "kings", "indivinity", "metro brands", "westside",
    "snitch", "marks and spencer", "trent", "clothing", "apparel",
    "textile", "babu sarees", "max retail", "hennes", "mauritz",
    "posh boutique", "landmark online", "mini sou", "miniso", "daiso",
    "fashnear", "meesho", "forever 21", "aditya birla fashion",
    "sri a l kandasami", "ssapl chennai express", "i walk",
    "fashion factory", "mens wear", "accessories", "kmk accessories",
    "bangles", "mahee and co",
]

ELECTRONICS_KEYWORDS = [
    "croma", "electronics", "tata digital", "tata digita", "rel retail ltd digital",
    "mobile one studio", "bohara mobiles", "appliances",
]

DELIVERY_KEYWORDS = [
    "delhivery", "smartshift logistic",
]

GOVERNMENT_KEYWORDS = [
    "uidai", "gov in",
]

AUTOMOTIVE_KEYWORDS = [
    "motor", "motors", "automobile", "auto ", "sun motor parts", "abt limited",
    "a b t limited", "car service", "3m car care", "washify",
]

SHOPPING_KEYWORDS = [
    "amazon", "flipkart", "fipkart", "saravana", "decathlon", "mr diy",
    "reliance trends", "reliance digital", "primas enterprises", "classic mall",
    "sri veeras creations", "rathina sabapathi", "lkst", "orbgen technologies",
    "m s kurinji metro baza", "mars enterprises", "grand square mall",
    "sri raghavendra venture", "hindustan trading", "pandian fancy",
    "vani enterprises", "ventota retail", "dsi brigade", "thilak enterprises",
    "vinayaka associates", "letspropstore", "sale domestic", "nippon enterprises",
    "daiso", "vvv enterprises", "sheeba", "smart associates", "seoul store",
    "m s shashvat retail", "blooming enterprises", "bloombay enterprises",
    "sree akshayam", "kia enterprises", "hot touch", "cw express avenue",
    "kurinji metro bazaar", "vr dakshin", "omr mall", "cw trades",
    "archies", "ps4", "plaa", "pengun xerox", "m s karisma",
]

ALCOHOL_KEYWORDS = [
    "tasmac",
]


def get_category(description, bank=None, card=None, txn_type=None, amount=None):
    """Categorize a transaction using merchant text plus optional bank/card context."""
    desc = normalize_merchant_text(description)
    raw_desc = f" {(description or '').lower()} "
    card_text = normalize_merchant_text(card)
    txn_type = (txn_type or "").upper()

    if not desc:
        return "Uncategorized"

    if has_any(desc, CREDIT_CARD_PAYMENT_KEYWORDS):
        return "Credit Card Payments"
    self_transfer_patterns = [
        *SELF_TRANSFER_PATTERNS,
        *env_regex_patterns("SELF_TRANSFER_PATTERNS"),
    ]
    personal_transfer_patterns = [
        *PERSONAL_TRANSFER_PATTERNS,
        *env_regex_patterns("PERSONAL_TRANSFER_PATTERNS"),
    ]

    if has_regex(desc, self_transfer_patterns):
        return "Internal Transfers"
    if txn_type == "CREDIT" and has_regex(desc, personal_transfer_patterns):
        return "Personal Transfers"
    if txn_type == "CREDIT" and has_any(desc, PF_WITHDRAWAL_KEYWORDS):
        return "PF Withdrawals"
    if txn_type == "CREDIT" and has_any(desc, TAX_REFUND_KEYWORDS):
        return "Tax Refunds"
    if txn_type == "CREDIT" and has_any(desc, INCOME_KEYWORDS):
        return "Income"
    if has_any(desc, INTERNAL_TRANSFER_KEYWORDS):
        return "Internal Transfers"
    if has_any(desc, PAYMENT_KEYWORDS):
        return "Payments"
    if txn_type == "CREDIT" and has_any(desc, REWARD_KEYWORDS):
        return "Rewards & Cashback"
    if txn_type == "CREDIT" and has_any(desc, REFUND_KEYWORDS):
        return "Refunds & Reversals"
    if has_any(desc, FEE_KEYWORDS):
        return "Fees & Charges"

    if has_any(desc, FUEL_KEYWORDS):
        return "Fuel"
    if "bpcl sbi card" in card_text and has_regex(desc, [r"\bagenc(y|ies|ie)\b"]):
        return "Fuel"

    ordered_rules = [
        ("Education", EDUCATION_KEYWORDS),
        ("Health", HEALTH_KEYWORDS),
        ("Pets", PETS_KEYWORDS),
        ("Rent & Housing", HOUSING_KEYWORDS),
        ("Jewelry", JEWELRY_KEYWORDS),
        ("Insurance", INSURANCE_KEYWORDS),
        ("Food & Dining", FOOD_KEYWORDS),
        ("Groceries", GROCERY_KEYWORDS),
        ("Travel & Transit", TRAVEL_KEYWORDS),
        ("Entertainment", ENTERTAINMENT_KEYWORDS),
        ("Utilities", UTILITY_KEYWORDS),
        ("Wallets & Gift Cards", WALLET_KEYWORDS),
        ("Beauty & Personal Care", BEAUTY_KEYWORDS),
        ("Clothing & Apparel", APPAREL_KEYWORDS),
        ("Electronics", ELECTRONICS_KEYWORDS),
        ("Delivery & Logistics", DELIVERY_KEYWORDS),
        ("Government", GOVERNMENT_KEYWORDS),
        ("Automotive", AUTOMOTIVE_KEYWORDS),
        ("Alcohol", ALCOHOL_KEYWORDS),
        ("Shopping", SHOPPING_KEYWORDS),
    ]

    for category, keywords in ordered_rules:
        if has_any(desc, keywords):
            return category

    if desc.startswith("upi "):
        return "UPI / Misc"

    # The BPCL SBI card is mostly used for fuel. Use this only after explicit
    # merchant rules above so subscriptions, fees, shopping, and payments win.
    if "bpcl sbi card" in card_text and txn_type == "DEBIT":
        return "Fuel"

    if txn_type == "CREDIT":
        return "Refunds & Reversals"

    return "Miscellaneous"


def is_internal_category(category):
    return category in INTERNAL_CATEGORIES


def update_transaction_categories(db_name=DB_FILE, dry_run=False):
    """Recompute and update category for every transaction row in the database."""
    with sqlite3.connect(db_name) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT id, bank_name, card_name, txn_type, description, amount, category
            FROM transactions
            ORDER BY id
        """).fetchall()

        changes = []
        new_category_counts = Counter()
        for row in rows:
            new_category = get_category(
                row["description"],
                bank=row["bank_name"],
                card=row["card_name"],
                txn_type=row["txn_type"],
                amount=row["amount"],
            )
            new_category_counts[new_category] += 1
            if new_category != row["category"]:
                changes.append((new_category, row["id"], row["category"]))

        if not dry_run:
            conn.executemany(
                "UPDATE transactions SET category = ? WHERE id = ?",
                [(category, row_id) for category, row_id, _ in changes],
            )
            conn.commit()

    return len(rows), changes, new_category_counts


def main():
    parser = argparse.ArgumentParser(description="Recompute transaction categories in expenses.db.")
    parser.add_argument("--db", default=DB_FILE, help="SQLite database path")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without updating rows")
    args = parser.parse_args()

    total_rows, changes, category_counts = update_transaction_categories(args.db, dry_run=args.dry_run)
    action = "Would update" if args.dry_run else "Updated"
    print(f"{action} {len(changes)} of {total_rows} transactions.")
    for category, count in category_counts.most_common():
        print(f"{category}: {count}")


if __name__ == "__main__":
    main()
