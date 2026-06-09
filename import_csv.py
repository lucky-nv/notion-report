#!/usr/bin/env python3
"""
Import CSV data into Notion database
"""

import os
import sys
import csv
import json
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# Try to import dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Manual .env loading
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

# Configuration
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

# Notion API base URL
NOTION_API_URL = "https://api.notion.com/v1"

def get_headers():
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def validate_config():
    """Validate required environment variables"""
    required = ["NOTION_API_KEY", "NOTION_DATABASE_ID"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        sys.exit(1)


def parse_currency(amount_str):
    """Convert Vietnamese currency string to float"""
    if not amount_str:
        return 0
    # Remove ₫ symbol and commas
    cleaned = amount_str.replace("₫", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0


def make_notion_request(method, endpoint, data=None):
    """Make HTTP request to Notion API"""
    url = f"{NOTION_API_URL}{endpoint}"
    headers = get_headers()

    if data:
        data = json.dumps(data).encode('utf-8')

    request = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        return e.code, {"error": error_body}
    except Exception as e:
        return 500, {"error": str(e)}


def transaction_exists(date_str, amount):
    """Check if a transaction with the same date and amount already exists"""
    try:
        payload = {
            "filter": {
                "and": [
                    {
                        "property": "Ngày",
                        "date": {
                            "equals": date_str
                        }
                    },
                    {
                        "property": "Số tiền",
                        "number": {
                            "equals": amount
                        }
                    }
                ]
            },
            "page_size": 1
        }

        status, response = make_notion_request("POST", f"/databases/{NOTION_DATABASE_ID}/query", payload)

        if status == 200:
            return len(response.get("results", [])) > 0
        return False
    except Exception as e:
        print(f"  ⚠️  Error checking if transaction exists: {e}")
        return False


def create_notion_entry(row):
    """Create a new entry in Notion database from CSV row"""
    try:
        # Parse date - format is DD/MM/YYYY in CSV
        date_str = row.get("Ngày", "").strip()
        amount_str = row.get("Số tiền", "").strip()

        if not date_str or not amount_str:
            print(f"  ⏭️  Skipped: Missing date or amount")
            return False

        # Convert DD/MM/YYYY to YYYY-MM-DD
        try:
            date_obj = datetime.strptime(date_str, "%d/%m/%Y")
            date_iso = date_obj.strftime("%Y-%m-%d")
        except ValueError as e:
            print(f"  ⏭️  Skipped: Invalid date format '{date_str}': {e}")
            return False

        # Parse amount
        amount = parse_currency(amount_str)
        if amount <= 0:
            print(f"  ⏭️  Skipped: Invalid amount '{amount_str}'")
            return False

        # Check if already exists
        if transaction_exists(date_iso, amount):
            print(f"  ⏭️  Skipped: Transaction already exists ({date_iso}, ₫{amount:,.0f})")
            return False

        # Extract other fields
        category = row.get("Hạng mục", "Khác").strip()
        loai = row.get("Loại", "Chi tiêu").strip()
        person = row.get("Người nhập", "Unknown").strip()
        note = row.get("Note", "").strip()

        # Build payload
        payload = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": {
                "Tên (tuỳ chọn)": {
                    "title": [
                        {
                            "text": {
                                "content": note[:100] if note else category[:100]
                            }
                        }
                    ]
                },
                "Ngày": {
                    "date": {
                        "start": date_iso
                    }
                },
                "Số tiền": {
                    "number": amount
                },
                "Hạng mục": {
                    "select": {
                        "name": category
                    }
                },
                "Loại": {
                    "select": {
                        "name": loai
                    }
                },
                "Người nhập": {
                    "select": {
                        "name": person
                    }
                },
            }
        }

        # Add note if present
        if note:
            payload["properties"]["Note"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": note
                        }
                    }
                ]
            }

        # Create the entry
        status, response = make_notion_request("POST", "/pages", payload)

        if status == 200:
            print(f"  ✅ Created: {date_iso} - ₫{amount:,.0f} - {category}")
            return True
        else:
            print(f"  ❌ Failed to create: {status}")
            if "error" in response:
                print(f"     Error: {str(response['error'])[:100]}")
            return False

    except Exception as e:
        print(f"  ❌ Error creating entry: {e}")
        return False


def load_and_import_csv(filepath):
    """Load CSV file and import data into Notion"""
    print(f"📥 Loading data from {filepath}...")

    if not Path(filepath).exists():
        print(f"❌ File not found: {filepath}")
        sys.exit(1)

    try:
        success_count = 0
        skip_count = 0
        error_count = 0

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=',')

            for idx, row in enumerate(reader, 1):
                print(f"\n{idx}. Processing row...")
                if create_notion_entry(row):
                    success_count += 1
                else:
                    skip_count += 1

        print("\n" + "="*50)
        print(f"📊 Import Summary:")
        print(f"  ✅ Created: {success_count}")
        print(f"  ⏭️  Skipped: {skip_count}")
        print(f"  ❌ Errors: {error_count}")
        print("="*50)

        return success_count > 0

    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        sys.exit(1)


def main():
    """Main execution"""
    print("="*50)
    print("🚀 CSV to Notion Importer")
    print("="*50)

    validate_config()

    # Import from import_data.csv
    success = load_and_import_csv("import_data.csv")

    if success:
        print("\n✅ Import completed successfully!")
    else:
        print("\n⚠️  No entries were imported")


if __name__ == "__main__":
    main()
