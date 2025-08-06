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
  "income": ["paychecks", "interest_income", "business_income", "investment income"],
  "benevolence": ["charity", "gifts"],
  "transportation": ["auto_payment", "public_transit", "gas", "auto_maintenance", "parking_or_tolls", "taxi_or_ride_shares"],
  "housing": ["mortgage", "rent", "furniture", "home_maintenance", "remodel"],
  "utilities": ["garbage", "water", "gas_and_electric", "internet", "phone", "software_subscriptions"],
  "food": ["groceries", "restaurants_or_bars", "coffee_shops"],
  "travel": ["travel_general", "airfare", "accommodation"],
  "shopping": ["shopping", "clothing", "housewares", "electronics"],
  "lifestyle": ["personal_grooming", "hobbies", "education", "entertainment_or_recreation"],
  "health_wellness": ["medical", "dental", "fitness"],
  "financial": ["loan_repayment", "financial_legal_services", "atm_cash_withdrawal", "insurance", "taxes", "penalties", "hand loans", "invest"],
  "other": ["uncategorized", "miscellaneous", "maaji bauji", "mummy-g, daddy-g", "loss", "reimburse"],
  "transfers": ["transfer", "credit_card_payment", "to_india"]
}

    