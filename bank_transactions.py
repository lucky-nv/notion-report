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
    merchant_match = re.search(r"tại\s+(.+?)\s+vào\s+ngày", body, re.IGNORECASE)
    if merchant_match:
        merchant = merchant_match.group(1).strip()
        transaction["merchant"] = merchant if merchant else None

    if not transaction.get("merchant"):
        transaction["merchant"] = None

    # Determine transaction type from subject
    transaction["type"] = "Chi tiêu"  # Default to expense
    if "hoàn tiền" in subject.lower() or "refund" in subject.lower():
        transaction["type"] = "Hoàn tiền"

    # Category mapping using shared function
    transaction["category"] = _get_transaction_category(transaction.get("merchant", ""))
    transaction["person"] = "Chồng"  # Default person (can be extended based on rules)
    transaction["description"] = "HSBC Transaction"  # Default description
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
        # Try to extract beneficiary name from various field names in HTML table format
        # Prioritize Beneficiary Name (cleaner data) over Payment Details
        patterns = [
            # Pattern 1: "Tên người hưởng" (Beneficiary Name) - cleanest data
            r"Tên người hưởng[\s\S]*?</td>\s*<td[^>]*>\s*([\s\S]*?)\s*</td>",
            # Pattern 2: "Beneficiary Name" (English version)
            r"Beneficiary Name[\s\S]*?</td>\s*<td[^>]*>\s*([\s\S]*?)\s*</td>",
            # Pattern 3: "Nội dung chuyển tiền" (Details of Payment) - fallback
            r"Nội dung chuyển tiền[\s\S]*?</td>\s*<td[^>]*>\s*([\s\S]*?)\s*</td>",
            # Pattern 4: "Details of Payment" (English fallback)
            r"Details of Payment[\s\S]*?</td>\s*<td[^>]*>\s*([\s\S]*?)\s*</td>",
        ]

        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                merchant = match.group(1).strip()
                # Remove HTML tags
                merchant = re.sub(r'<[^>]+>', '', merchant)
                # Remove HTML entities
                merchant = merchant.replace('&nbsp;', ' ')
                merchant = merchant.replace('&lt;', '<')
                merchant = merchant.replace('&gt;', '>')
                # Normalize whitespace
                merchant = re.sub(r'\s+', ' ', merchant).strip()

                if merchant and len(merchant) > 2:  # Avoid very short matches
                    print(f"        Merchant: {merchant}")
                    return merchant

    print("        ⚠️  No merchant found")
    return ""


def _get_transaction_category(merchant_name):
    """Smart category detection using keyword scoring and pattern matching"""
    if not merchant_name:
        return "💳 Khác"

    merchant_lower = merchant_name.lower()

    # Category rules with comprehensive keywords from real transaction data
    categories = {
        "🛒 Mua sắm": {
            "keywords": ["shop", "store", "mall", "aeon", "vinmart", "amazon", "digitalocean", "apple",
                        "shopping", "retail", "market", "supermarket", "outlet", "lazada", "shopee",
                        "tiki", "sendo", "fashion", "clothing", "footwear", "electronics", "gadget",
                        "furniture", "wincommerce", "bach hoa", "bách hóa", "tung dat"],
            "score": 10
        },
        "🍽️ Ăn uống": {
            "keywords": ["restaurant", "cafe", "coffee", "food", "quán", "nhà hàng", "ăn", "drink",
                        "pizza", "burger", "noodle", "pho", "bánh", "cơm", "trà", "nước", "beer",
                        "bar", "pub", "bistro", "dining", "ca phe", "dang ca phe", "coffee shop", "fast food"],
            "score": 10
        },
        "⛽ Xăng dầu": {
            "keywords": ["fuel", "gas", "petrol", "xăng", "dầu", "shell", "bp", "esso", "caltex",
                        "petrolimex", "gas station", "filling station"],
            "score": 10
        },
        "✈️ Du lịch": {
            "keywords": ["hotel", "airline", "flight", "khách sạn", "bay", "booking", "agoda",
                        "resort", "motel", "hostel", "airbnb", "travel", "tour", "railway"],
            "score": 10
        },
        "⚕️ Y tế": {
            "keywords": ["hospital", "clinic", "pharmacy", "bệnh viện", "nhà thuốc", "doctor",
                        "medical", "health", "dental", "dentist", "vaccine", "drug store",
                        "phòng khám", "klinik", "thuốc", "y tế"],
            "score": 10
        },
        "📱 Ví điện tử": {
            "keywords": ["momo", "zalopay", "apple pay", "google pay", "paypal", "stripe",
                        "e-wallet", "ewallet", "digital wallet", "topup", "recharge"],
            "score": 10
        },
        "🏠 Thuê nhà": {
            "keywords": ["rent", "nhà", "cho thuê", "tiền nhà", "apartment", "landlord",
                        "real estate", "accommodation", "property"],
            "score": 10
        },
        "💰 Trả nợ": {
            "keywords": ["loan", "vay", "nợ", "credit", "lending", "mortgage", "debt"],
            "score": 10
        },
        "🛡️ Bảo hiểm": {
            "keywords": ["insurance", "bảo hiểm", "policy", "claim", "coverage"],
            "score": 10
        },
        "📚 Sách & Học tập": {
            "keywords": ["book", "sách", "nhà sách", "bookstore", "nhasach", "school", "education",
                        "university", "course", "học"],
            "score": 10
        },
        "🎮 Giải trí & Game": {
            "keywords": ["game", "tro choi", "trò chơi", "gaming", "entertainment", "cinema", "movie",
                        "phuc nguyen", "điện tử"],
            "score": 10
        },
    }

    # Score each category based on keyword matches
    scores = {}
    for category, rules in categories.items():
        score = 0
        for keyword in rules["keywords"]:
            if keyword in merchant_lower:
                # Higher score for exact word match vs substring match
                if f" {keyword} " in f" {merchant_lower} " or merchant_lower.startswith(keyword) or merchant_lower.endswith(keyword):
                    score += rules["score"]
                else:
                    score += rules["score"] // 2

        if score > 0:
            scores[category] = score

    # Return category with highest score
    if scores:
        return max(scores, key=scores.get)

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
    transaction["category"] = _get_transaction_category(merchant)
    transaction["person"] = "Chồng"
    transaction["notes"] = merchant
    transaction["description"] = "Vietcombank Transaction"


    print(f"        Parsed Vietcombank transaction - Merchant: {merchant} | Amount: {transaction['amount']:,.0f} | Date: {transaction['date']} | Category: {transaction['category']}")

    return transaction


def parse_bank_email(subject, body):
    """Parse bank transaction email based on subject"""
    # Detect bank type from subject or content
    subject_lower = subject.lower()

    if 'hsbc' in subject_lower:
        return parse_hsbc_email(subject, body)

    # Check for Vietcombank (handles both card transactions and payment receipts)
    if any(keyword in subject_lower for keyword in ["giao dịch thẻ", "card transaction", "vietcombank", "biên lai chuyển tiền", "biên lai thanh toán", "payment receipt"]):
        return parse_vietcombank_email(subject, body)

    # Add more bank parsers here as needed
    return None


def save_raw_emails_cache(raw_emails):
    """Save raw email data (subject + body) to local cache"""
    cache_file = LOGS_DIR / "raw_emails_cache.json"
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(raw_emails, f, ensure_ascii=False, indent=2)
        print(f"💾 Cached {len(raw_emails)} raw emails to {cache_file}")
    except Exception as e:
        print(f"⚠️  Failed to save raw email cache: {e}")


def load_raw_emails_cache():
    """Load previously cached raw email data"""
    cache_file = LOGS_DIR / "raw_emails_cache.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                emails = json.load(f)
                print(f"📂 Loaded {len(emails)} cached raw emails from {cache_file}")
                return emails
        except Exception as e:
            print(f"⚠️  Failed to load raw email cache: {e}")
    return None


def process_raw_emails(raw_emails):
    """Process cached raw emails and extract transactions"""
    transactions = []
    for idx, email_data in enumerate(raw_emails, 1):
        subject = email_data.get("subject", "")
        body = email_data.get("body", "")
        sender = email_data.get("sender", "")

        print(f"\n{idx}. {subject[:60]}...")
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

    return transactions


def fetch_emails(days=1, use_cache=True, save_cache=True):
    """Fetch bank transaction emails from Gmail or cache"""
    # Check for cached raw emails first
    if use_cache:
        cached_raw_emails = load_raw_emails_cache()
        if cached_raw_emails:
            return process_raw_emails(cached_raw_emails)

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
            print(f"🔍 Fetching {len(message_ids)} emails...")

            raw_emails = []
            for idx, message_id in enumerate(message_ids, 1):
                try:
                    _, msg_data = mail.fetch(message_id, "(RFC822)")
                    msg_bytes = msg_data[0][1]  # type: ignore
                    msg = email.message_from_bytes(msg_bytes)  # type: ignore

                    subject = decode_email_header(msg.get("Subject", ""))
                    body = get_email_body(msg)
                    sender = msg.get("From", "")

                    # Store raw email data
                    raw_emails.append({
                        "subject": subject,
                        "body": body,
                        "sender": sender
                    })
                    print(f"  {idx}. {subject[:60]}...")

                except Exception as e:
                    print(f"  ⚠️  Error fetching email: {e}")
                    continue

            if raw_emails:
                if save_cache:
                    print(f"\n💾 Saving {len(raw_emails)} raw emails to cache...")
                    save_raw_emails_cache(raw_emails)
                print(f"\n🔍 Processing {len(raw_emails)} emails...")
                transactions = process_raw_emails(raw_emails)
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
                    },
                    {
                        "property": "Merchant",
                        "rich_text": {"equals": merchant}
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
        # Skip if merchantis "BUI VAN ANH" or "NGUYEN VAN QUANG" (self-transfers)
        if transaction.get("merchant", "").upper() in ["BUI VAN ANH", "NGUYEN VAN QUANG", "MOMO_NGUYEN VAN QUANG"]:
            print(f"      ⏭️  Skipped self-transfer transaction: {transaction['date']} - ₫{transaction.get('amount', 0):,.0f}")
            return False
        
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
    transactions = fetch_emails(days=2, use_cache=False, save_cache=False)

    if not transactions:
        print("ℹ️  No new transactions found")
        print("=" * 60)
        return
    
    print("\n📋 Transactions to import:")
    for t in transactions:
        print(json.dumps(t, ensure_ascii=False, indent=2))
    
    

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
