import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
}

response = requests.get(
    f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}",
    headers=HEADERS
)

if response.status_code == 200:
    data = response.json()
    print("📊 Database Fields:")
    print("=" * 60)
    for prop_name, prop_data in data.get("properties", {}).items():
        print(f"  • {prop_name:20} ({prop_data.get('type', 'unknown')})")
    print("=" * 60)
else:
    print(f"Error: {response.status_code}")
    print(response.text)
