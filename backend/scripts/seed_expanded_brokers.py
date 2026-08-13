import os
import sys
from pathlib import Path

# Add the project root to sys.path so we can import from app
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.database import SessionLocal
from app.models import BrokerMaster

# Define the brokers to be seeded
indian_brokers = [
    {"canonical_name": "Mirae Asset Sharekhan", "display_name": "Sharekhan"},
    {"canonical_name": "SBI Securities", "display_name": "SBI Securities"},
    {"canonical_name": "Nuvama", "display_name": "Nuvama Wealth"},
    {"canonical_name": "JM Financial", "display_name": "JM Financial"},
    {"canonical_name": "Emkay Global", "display_name": "Emkay Global"},
    {"canonical_name": "Prabhudas Lilladher", "display_name": "Prabhudas Lilladher"},
    {"canonical_name": "Geojit", "display_name": "Geojit"},
    {"canonical_name": "Anand Rathi", "display_name": "Anand Rathi"},
    {"canonical_name": "Antique Stock Broking", "display_name": "Antique"},
    {"canonical_name": "Centrum", "display_name": "Centrum"},
    {"canonical_name": "Choice Broking", "display_name": "Choice Broking"},
    {"canonical_name": "KR Choksey", "display_name": "KR Choksey"},
    {"canonical_name": "Religare", "display_name": "Religare"},
    {"canonical_name": "PhillipCapital India", "display_name": "PhillipCapital"},
    {"canonical_name": "Ventura Securities", "display_name": "Ventura"},
    {"canonical_name": "Monarch Networth", "display_name": "Monarch Networth"},
    {"canonical_name": "Arihant Capital", "display_name": "Arihant Capital"},
    {"canonical_name": "YES Securities", "display_name": "YES Securities"},
    {"canonical_name": "Elara Capital", "display_name": "Elara Capital"},
    {"canonical_name": "InCred Equities", "display_name": "InCred"},
    {"canonical_name": "DAM Capital", "display_name": "DAM Capital"},
    {"canonical_name": "IIFL Securities", "display_name": "IIFL"},
    {"canonical_name": "LKP Securities", "display_name": "LKP"},
    {"canonical_name": "Sushil Finance", "display_name": "Sushil Finance"},
    {"canonical_name": "Systematix", "display_name": "Systematix"}
]

international_brokers = [
    {"canonical_name": "Jefferies", "display_name": "Jefferies"},
    {"canonical_name": "Morgan Stanley", "display_name": "Morgan Stanley"},
    {"canonical_name": "Goldman Sachs", "display_name": "Goldman Sachs"},
    {"canonical_name": "JPMorgan", "display_name": "JPMorgan"},
    {"canonical_name": "Citi", "display_name": "Citi"},
    {"canonical_name": "UBS", "display_name": "UBS"},
    {"canonical_name": "CLSA", "display_name": "CLSA"},
    {"canonical_name": "Bernstein", "display_name": "Bernstein"},
    {"canonical_name": "Macquarie", "display_name": "Macquarie"},
    {"canonical_name": "Nomura", "display_name": "Nomura"},
    {"canonical_name": "HSBC", "display_name": "HSBC"},
    {"canonical_name": "BofA Securities", "display_name": "BofA"},
    {"canonical_name": "Barclays", "display_name": "Barclays"}
]

def seed_brokers():
    db = SessionLocal()
    try:
        all_brokers = indian_brokers + international_brokers
        for b_data in all_brokers:
            normalized = b_data["canonical_name"].strip().lower().replace(" ", "")
            existing = db.query(BrokerMaster).filter(BrokerMaster.normalized_name == normalized).first()
            if not existing:
                broker = BrokerMaster(
                    canonical_name=b_data["canonical_name"],
                    normalized_name=normalized,
                    display_name=b_data["display_name"],
                    is_historical_only=False
                )
                db.add(broker)
        db.commit()
        print("Brokers seeded successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding brokers: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_brokers()
