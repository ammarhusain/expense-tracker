import os
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Dict, List

load_dotenv()

@dataclass
class Config:
    plaid_client_id: str = os.getenv("PLAID_CLIENT_ID", "")
    plaid_secret: str = os.getenv("PLAID_SECRET", "")
    plaid_env: str = os.getenv("PLAID_ENV", "sandbox")
    csv_file_path: str = os.getenv("CSV_FILE_PATH", "./transactions.csv")
    sync_interval_hours: int = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))

config = Config()

CATEGORY_MAPPING = {
    "Food and Drink": ["restaurant", "food", "grocery", "coffee", "bar"],
    "Transportation": ["gas", "uber", "lyft", "parking", "transit"],
    "Shopping": ["amazon", "target", "walmart", "clothing", "retail"],
    "Bills": ["electric", "gas", "water", "internet", "phone", "insurance"],
    "Entertainment": ["netflix", "spotify", "movie", "game", "concert"],
    "Healthcare": ["doctor", "pharmacy", "hospital", "medical", "dental"],
    "Income": ["payroll", "salary", "deposit", "refund"],
    "Other": []
}