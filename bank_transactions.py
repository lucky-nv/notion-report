#!/usr/bin/env python3
"""
Daily Bank Transaction Importer
Reads bank transaction emails and imports them to Notion database
"""

import os
import sys
import imaplib
import email
import re
import json
from datetime import datetime, timedelta
from email.header import decode_header
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration - Reuse same env vars as expense_report.py
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")  # Use same database as expense report
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh")

# Notion API base URL
NOTION_API_URL = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# Create logs directory
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)


def validate_config():
    """Validate required environment variables"""
    required = [
        "NOTION_API_KEY",
        "NOTION_DATABASE_ID",
        "GMAIL_EMAIL",
        "GMAIL_APP_PASSWORD",
    ]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        sys.exit(1)


def decode_email_header(header_value):
    """Decode email header (handles encoded subjects)"""
    if not header_value:
        return ""
    decoded_parts = decode_header(header_value)
    decoded_str = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            decoded_str += part.decode(encoding or "utf-8", errors="ignore")
        else:
            decoded_str += str(part)
    return decoded_str


def get_email_body(msg):
    """Extract email body text"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="ignore"
                    )
                    break
                except Exception:
                    continue
    else:
        try:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="ignore"
            )
        except Exception:
            body = msg.get_payload()
    return body


def parse_hsbc_email(subject, body):
    """Parse HSBC bank transaction email"""
    transaction = {}

    # Extract amount (looking for amount before VND)
    amount_match = re.search(
        r"số tiền\s+(\d{1,3}(?:,\d{3})*|\d+)\s*(?:VND|₫)?", body, re.IGNORECASE
    )
    if amount_match:
        amount_str = amount_match.group(1).replace(",", "")
        try:
            transaction["amount"] = float(amount_str)
        except ValueError:
            transaction["amount"] = 0

    # Extract date (pattern: "ngày 07/06/2026" or similar)
    date_match = re.search(r"ngày\s+(\d{1,2})/(\d{1,2})/(\d{4})", body, re.IGNORECASE)
    if date_match:
        try:
            day, month, year = date_match.groups()
            transaction["date"] = f"{year}-{month:0>2}-{day:0>2}"
        except Exception:
            transaction["date"] = datetime.now().strftime("%Y-%m-%d")
    else:
        transaction["date"] = datetime.now().strftime("%Y-%m-%d")

    # Extract merchant/location (pattern: "tại MERCHANT_NAME vào ngày")
    merchant_match = re.search(r"tại\s+([A-Z\s]+?)\s+vào\s+ngày", body, re.IGNORECASE)
    if merchant_match:
        transaction["merchant"] = merchant_match.group(1).strip()
    else:
        # Try to find all-caps words as fallback
        caps_match = re.search(r"[A-Z\s]{5,}", body)
        if caps_match:
            transaction["merchant"] = caps_match.group(0).strip()[:50]

    # Determine transaction type from subject
    transaction["type"] = "Chi tiêu"  # Default to expense
    if "hoàn tiền" in subject.lower() or "refund" in subject.lower():
        transaction["type"] = "Hoàn tiền"

    # Category mapping based on merchant name
    merchant_name = transaction.get("merchant", "").lower()
    category = "💳 Khác"  # Default category
    if any(word in merchant_name for word in ["mall", "store", "shop", "aeon", "vinmart"]):
        category = "🛒 Mua sắm"
    elif any(word in merchant_name for word in ["restaurant", "cafe", "quán", "nhà hàng", "ăn"]):
        category = "🍽️ Ăn uống"
    elif any(word in merchant_name for word in ["fuel", "gas", "petrol", "xăng", "dầu"]):
        category = "⛽ Xăng dầu"
    elif any(word in merchant_name for word in ["hospital", "clinic", "pharmacy", "bệnh viện", "nhà thuốc"]):
        category = "⚕️ Y tế"

    transaction["category"] = category
    transaction["person"] = "Chồng"  # Default person (can be extended based on rules)
    transaction["description"] = subject.replace("[TB/Alert]", "").strip()
    transaction["notes"] = f"HSBC Merchant: {transaction.get('merchant', 'Unknown')}"

    return transaction


def _extract_vietcombank_amount(body):
    """Extract transaction amount from Vietcombank email"""
    amount_match = re.search(
        r"Số tiền\s*(?:Amount|Transaction\s*Amount)?\s*[:\s]*\n?\s*(\d+(?:[.,]\d{2})?|\d{1,3}(?:,\d{3})*)\s*(?:VND|₫|USD)?",
        body, re.IGNORECASE
    )
    if amount_match:
        amount_str = amount_match.group(1).replace(",", ".")
        try:
            amount = float(amount_str)
            if amount > 0:
                print(f"        Amount: {amount:,.0f}")
                return amount
        except ValueError:
            print(f"        ⚠️  Failed to parse amount: {amount_str}")

    # Fallback: Look for any formatted number with VND
    amount_match2 = re.search(r"(\d{1,3}(?:,\d{3})+)\s*(?:VND|₫)", body)
    if amount_match2:
        amount_str = amount_match2.group(1).replace(",", "")
        try:
            amount = float(amount_str)
            if amount > 0:
                print(f"        Amount (fallback): {amount:,.0f}")
                return amount
        except ValueError:
            pass

    print("        ⚠️  No amount found in email")
    return 0


def _extract_vietcombank_date(body):
    """Extract transaction date from Vietcombank email"""
    date_match = re.search(
        r"(?:Ngày|Trans\.\s*Date)[\s\S]*?(\d{1,2})[-/](\d{1,2})[-/](\d{4})",
        body, re.IGNORECASE
    )
    if date_match:
        try:
            day, month, year = date_match.groups()
            date = f"{year}-{month:0>2}-{day:0>2}"
            print(f"        Date: {date}")
            return date
        except Exception as e:
            print(f"        ⚠️  Failed to parse date: {e}")

    print("        ⚠️  No date found, using today's date")
    return datetime.now().strftime("%Y-%m-%d")


def _extract_vietcombank_merchant(body, transaction_type="transfer"):
    """Extract merchant/beneficiary from Vietcombank email"""
    if transaction_type == "card":
        merchant_match = re.search(
            r"(?:Sử dụng tại|At)[^\n]*\n\s*([^\n]+)", body, re.IGNORECASE
        )
        if merchant_match:
            merchant = merchant_match.group(1).strip()
            print(f"        Merchant: {merchant}")
            return merchant
    else:
        # Extract account number from "Tài khoản người hưởng"
        account_match = re.search(
            r"Tài khoản người hưởng.*?<td[^>]*>\s*([A-Z0-9]{6,})", body, re.IGNORECASE | re.DOTALL
        )
        account = account_match.group(1).strip() if account_match else ""

        # Extract beneficiary name from "Tên người hưởng"
        name_match = re.search(
            r"Tên người hưởng.*?<td[^>]*>\s*([A-Z][A-Z\s()]+)", body, re.IGNORECASE | re.DOTALL
        )
        name = name_match.group(1).strip() if name_match else ""

        if account or name:
            result = f"{account} | {name}".strip(" |")
            print(f"        Merchant: {result}")
            return result

    print("        ⚠️  No merchant found")
    return ""


def _get_vietcombank_category(merchant_name):
    """Determine transaction category based on merchant name"""
    merchant_lower = merchant_name.lower()

    # Shopping & online
    if any(word in merchant_lower for word in ["shop", "store", "mall", "aeon", "vinmart", "amazon", "digitalocean", "apple"]):
        return "🛒 Mua sắm"
    # Dining
    elif any(word in merchant_lower for word in ["restaurant", "cafe", "food", "quán", "nhà hàng", "ăn"]):
        return "🍽️ Ăn uống"
    # Fuel
    elif any(word in merchant_lower for word in ["fuel", "gas", "petrol", "xăng", "dầu"]):
        return "⛽ Xăng dầu"
    # Travel
    elif any(word in merchant_lower for word in ["hotel", "airline", "flight", "khách sạn", "bay"]):
        return "✈️ Du lịch"
    # Healthcare
    elif any(word in merchant_lower for word in ["hospital", "clinic", "pharmacy", "bệnh viện", "nhà thuốc"]):
        return "⚕️ Y tế"
    # E-wallet
    elif any(word in merchant_lower for word in ["momo", "zalopay", "apple pay", "google pay"]):
        return "📱 Ví điện tử"
    # Housing
    elif any(word in merchant_lower for word in ["rent", "nhà", "cho thuê", "tiền nhà"]):
        return "🏠 Thuê nhà"
    # Debt
    elif any(word in merchant_lower for word in ["loan", "vay", "nợ"]):
        return "💰 Trả nợ"
    # Insurance
    elif any(word in merchant_lower for word in ["insurance", "bảo hiểm"]):
        return "🛡️ Bảo hiểm"

    return "💳 Khác"


def parse_vietcombank_email(subject, body):
    """Parse Vietcombank email (handles both card transactions and payment receipts)"""
    transaction = {}

    # Determine transaction type
    is_card_transaction = "giao dịch thẻ" in subject.lower() or "card transaction" in subject.lower()

    # Extract common fields
    merchant = _extract_vietcombank_merchant(body, transaction_type="card" if is_card_transaction else "transfer")
    if merchant is None:  # Self-transfer, skip
        return None

    transaction["merchant"] = merchant
    transaction["amount"] = _extract_vietcombank_amount(body)
    transaction["date"] = _extract_vietcombank_date(body)

    # Skip if no valid amount
    if transaction.get("amount", 0) <= 0:
        print(f"        ⏭️  Skipped: Amount is {transaction.get('amount', 0)}")
        return None

    # Set common fields
    transaction["type"] = "Chi tiêu"
    transaction["category"] = _get_vietcombank_category(merchant)
    transaction["person"] = "Chồng"
    transaction["notes"] = f"VCB - {merchant}"


    print(f"        Parsed Vietcombank transaction - Merchant: {merchant} | Amount: {transaction['amount']:,.0f} | Date: {transaction['date']} | Category: {transaction['category']}")

    return transaction


def parse_bank_email(subject, body):
    """Parse bank transaction email based on subject"""
    # Detect bank type from subject or content
    subject_lower = subject.lower()

    if 'hsbc' in subject_lower:
        return parse_hsbc_email(subject, body)

    # Check for Vietcombank (handles both card transactions and payment receipts)
    if any(keyword in subject_lower for keyword in ["giao dịch thẻ", "card transaction", "vietcombank", "biên lai chuyển tiền", "payment receipt"]):
        return parse_vietcombank_email(subject, body)

    # Add more bank parsers here as needed
    return None


def fetch_emails(days=1):
    """Fetch bank transaction emails from Gmail"""
    print("📧 Connecting to Gmail...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        gmail_email = GMAIL_EMAIL or ""
        gmail_password = GMAIL_APP_PASSWORD or ""
        mail.login(gmail_email, gmail_password)
        print("✅ Connected to Gmail")
    except Exception as e:
        print(f"❌ Failed to connect to Gmail: {e}")
        sys.exit(1)

    # Enable UTF8 mode for non-ASCII search terms
    try:
        mail.enable("UTF8=ACCEPT")
    except Exception:
        pass  # Some servers don't support UTF8

    transactions = []

    # Search for transaction emails from the last N days
    mail.select("INBOX")
    since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")

    # Search for emails from specific bank senders only
    try:
        # Search for emails from Vietcombank and HSBC
        _, vietcombank_messages = mail.search(None, 'FROM', 'VCBDigibank@info.vietcombank.com.vn', 'SINCE', since_date)
        _, hsbc_messages = mail.search(None, 'FROM', 'HSBC@notification.hsbc.com.hk', 'SINCE', since_date)

        # Combine message IDs from both banks
        vietcombank_ids = vietcombank_messages[0].split() if vietcombank_messages[0] else []
        hsbc_ids = hsbc_messages[0].split() if hsbc_messages[0] else []
        message_ids = vietcombank_ids + hsbc_ids

        print(f"📨 Found {len(message_ids)} bank emails from last {days} day(s)")

        if not message_ids:
            print("ℹ️  No emails from bank senders found")
        else:
            print(f"🔍 Processing {len(message_ids)} emails...")

            for idx, message_id in enumerate(message_ids, 1):
                try:
                    _, msg_data = mail.fetch(message_id, "(RFC822)")
                    msg_bytes = msg_data[0][1]  # type: ignore
                    msg = email.message_from_bytes(msg_bytes)  # type: ignore

                    subject = decode_email_header(msg.get("Subject", ""))
                    body = get_email_body(msg)
                    sender = msg.get("From", "")

                    transaction = parse_bank_email(subject, body)

                    if transaction is None:
                        print("        ⏭️  Skipped by parser")
                    elif transaction.get("amount", 0) <= 0:
                        print(f"        ⏭️  Skipped: Amount is {transaction.get('amount', 0)}")
                    else:
                        transaction["sender"] = sender
                        transaction["subject"] = subject
                        transactions.append(transaction)
                        print(f"        ✅ Parsed successfully - Category: {transaction.get('category', 'N/A')} | Date: {transaction.get('date', 'N/A')}")
                        print(f"        📋 {json.dumps(transaction, ensure_ascii=False, indent=2)}")

                except Exception as e:
                    print(f"  ⚠️  Error parsing email: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

            print(f"\n📊 Parsed {len(transactions)} valid transactions")

    finally:
        mail.close()

    return transactions


def transaction_exists(transaction_date, merchant, amount):
    """Check if transaction already exists in Notion"""
    try:
        payload = {
            "filter": {
                "and": [
                    {
                        "property": "Ngày",
                        "date": {"equals": transaction_date}
                    },
                    {
                        "property": "Số tiền",
                        "number": {"equals": amount}
                    }
                ]
            }
        }

        response = requests.post(
            f"{NOTION_API_URL}/databases/{NOTION_DATABASE_ID}/query",
            headers=HEADERS,
            json=payload,
        )

        if response.status_code == 200:
            data = response.json()
            exists = len(data.get("results", [])) > 0
            if exists:
                print("        ℹ️  Already exists in Notion")
            return exists
        else:
            print(f"        ⚠️  Failed to check Notion: {response.status_code}")
            return False
    except Exception as e:
        print(f"        ⚠️  Error checking if transaction exists: {e}")
        return False


def create_notion_transaction(transaction):
    """Create a new transaction in Notion database"""
    try:
        # Skip if transaction already exists
        print(f"      🔍 Checking if exists: {transaction['date']} - ₫{transaction.get('amount', 0):,.0f}")
        if transaction_exists(transaction["date"], transaction.get("merchant", ""), transaction.get("amount", 0)):
            return False

        # Build title and note
        title = transaction.get("description", "Bank Transaction")[:100]
        notes = transaction.get("notes", "")

        

        payload = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": {
                "Tên (tuỳ chọn)": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                },
                "Ngày": {
                    "date": {
                        "start": transaction["date"]
                    }
                },
                "Số tiền": {
                    "number": transaction.get("amount", 0)
                },
                "Hạng mục": {
                    "select": {
                        "name": transaction.get("category", "💳 Khác")
                    }
                },
                "Loại": {
                    "select": {
                        "name": transaction.get("type", "Chi tiêu")
                    }
                },
                "Người nhập": {
                    "select": {
                        "name": transaction.get("person", "Chồng")
                    }
                },
            }
        }

        # Add note if we have merchant info
        if notes:
            payload["properties"]["Note"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": notes
                        }
                    }
                ]
            }

        print(f"      📤 Creating transaction: {transaction.get('description', 'N/A')[:40]}")
        response = requests.post(
            f"{NOTION_API_URL}/pages",
            headers=HEADERS,
            json=payload,
        )

        if response.status_code == 200:
            print(f"      ✅ Created: {transaction['date']} - ₫{transaction.get('amount', 0):,.0f} - {transaction.get('merchant', 'Unknown')[:30]}")
            return True
        else:
            print(f"      ❌ Failed to create transaction: {response.status_code}")
            print(f"         Response: {response.text[:300]}")
            return False

    except Exception as e:
        print(f"  ❌ Error creating transaction: {e}")
        return False


def main():
    """Main execution"""
    print("=" * 60)
    print("🏦 Daily Bank Transaction Importer")
    print("=" * 60)

    validate_config()

    # Fetch emails from last 1 day
    transactions = fetch_emails(days=30)

    if not transactions:
        print("ℹ️  No new transactions found")
        print("=" * 60)
        return
    
    

    print(f"\n💾 Importing {len(transactions)} transactions to Notion...")
    created = 0
    for i, transaction in enumerate(transactions, 1):
        print(f"\n  Transaction {i}/{len(transactions)}:")
        if create_notion_transaction(transaction):
            created += 1

    print("\n" + "=" * 60)
    print(f"✅ Import complete! Created {created}/{len(transactions)} transactions")
    print("=" * 60)


if __name__ == "__main__":
    main()
