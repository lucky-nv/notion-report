#!/usr/bin/env python3
"""
Monthly Expense Report Generator
Fetches data from Notion, generates charts, and sends via email
"""

import os
import sys
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_RECIPIENTS = os.getenv("EMAIL_RECIPIENTS", "").split(",")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh")

# Create reports directory
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

# Notion API base URL
NOTION_API_URL = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2024-02-15",
    "Content-Type": "application/json",
}

matplotlib.use("Agg")  # Use non-interactive backend


def validate_config(demo_mode=False):
    """Validate required environment variables"""
    if demo_mode:
        print("🎬 Running in DEMO MODE (no email will be sent)")
        return

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
    if not EMAIL_RECIPIENTS or not EMAIL_RECIPIENTS[0]:
        print("❌ EMAIL_RECIPIENTS not set")
        sys.exit(1)

    # Type assertions for mypy
    assert NOTION_API_KEY is not None
    assert NOTION_DATABASE_ID is not None
    assert GMAIL_EMAIL is not None
    assert GMAIL_APP_PASSWORD is not None


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


def load_csv_data(filepath="sample_data.csv"):
    """Load expense and income data from CSV file"""
    print(f"📥 Loading data from {filepath}...")
    try:
        df_csv = pd.read_csv(filepath)
        all_data = []

        for _, row in df_csv.iterrows():
            try:
                date_str = str(row.get("Ngày", ""))
                amount_str = str(row.get("Số tiền", ""))
                loai = str(row.get("Loại", "Chi tiêu")).strip()
                category = str(row.get("Hạng mục", "Khác"))
                person = str(row.get("Người nhập", ""))

                if date_str and amount_str and date_str != "nan":
                    # Try different date formats
                    date_obj = None
                    for fmt in ["%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"]:
                        try:
                            date_obj = datetime.strptime(date_str.strip(), fmt)
                            break
                        except ValueError:
                            continue

                    if date_obj:
                        all_data.append(
                            {
                                "date": date_obj,
                                "amount": parse_currency(amount_str),
                                "type": loai if loai.lower() in ["chi tiêu", "thu nhập"] else "Chi tiêu",
                                "category": category.strip() if category != "nan" else "Khác",
                                "person": person.strip() if person != "nan" else "Unknown",
                            }
                        )
            except Exception as e:
                print(f"⚠️ Error parsing row: {e}")
                continue

        if not all_data:
            print("❌ No data found in CSV")
            sys.exit(1)

        df = pd.DataFrame(all_data)
        print(f"✅ Loaded {len(df)} records from CSV")
        return df
    except FileNotFoundError:
        print(f"❌ File not found: {filepath}")
        sys.exit(1)


def fetch_notion_data():
    """Fetch expense data from Notion database"""
    print("📥 Fetching data from Notion...")
    all_data = []
    start_cursor = None

    while True:
        payload = {
            "page_size": 100,
        }
        if start_cursor:
            payload["start_cursor"] = start_cursor

        response = requests.post(
            f"{NOTION_API_URL}/databases/{NOTION_DATABASE_ID}/query",
            headers=HEADERS,
            json=payload,
        )

        if response.status_code != 200:
            print(f"❌ Notion API error: {response.status_code}")
            print(response.text)
            sys.exit(1)

        data = response.json()
        results = data.get("results", [])

        for item in results:
            properties = item.get("properties", {})
            try:
                date_str = (
                    properties.get("Ngày", {}).get("date", {}).get("start", "")
                )
                amount_str = properties.get("Số tiền", {}).get("rich_text", [])
                amount = (
                    amount_str[0].get("plain_text", "")
                    if amount_str
                    else ""
                )
                category = (
                    properties.get("Hạng mục", {}).get("select", {}).get("name", "Khác")
                    if properties.get("Hạng mục", {}).get("select")
                    else "Khác"
                )
                person = (
                    properties.get("Người nhập", {}).get("select", {}).get("name", "")
                    if properties.get("Người nhập", {}).get("select")
                    else ""
                )

                if date_str and amount:
                    all_data.append(
                        {
                            "date": datetime.strptime(date_str, "%Y-%m-%d"),
                            "amount": parse_currency(amount),
                            "category": category,
                            "person": person,
                        }
                    )
            except Exception as e:
                print(f"⚠️ Error parsing item: {e}")
                continue

        if data.get("has_more"):
            start_cursor = data.get("next_cursor")
        else:
            break

    if not all_data:
        print("❌ No expense data found in Notion database")
        sys.exit(1)

    df = pd.DataFrame(all_data)
    print(f"✅ Fetched {len(df)} expense records")
    return df


def process_data(df):
    """Process and aggregate data by month, separating income and expenses"""
    df["year_month"] = df["date"].dt.to_period("M")

    # Get current and previous month
    today = datetime.now()
    current_month = pd.Period(today, freq="M")
    previous_month = current_month - 1

    current_df = df[df["year_month"] == current_month].copy()
    previous_df = df[df["year_month"] == previous_month].copy()

    # Separate expenses and income
    current_expense_df = current_df[current_df["type"].str.lower() == "chi tiêu"]
    current_income_df = current_df[current_df["type"].str.lower() == "thu nhập"]
    previous_expense_df = previous_df[previous_df["type"].str.lower() == "chi tiêu"]
    previous_income_df = previous_df[previous_df["type"].str.lower() == "thu nhập"]

    # Calculate totals
    current_expense_total = current_expense_df["amount"].sum()
    current_income_total = current_income_df["amount"].sum()
    previous_expense_total = previous_expense_df["amount"].sum()
    previous_income_total = previous_income_df["amount"].sum()

    current_net = current_income_total - current_expense_total
    previous_net = previous_income_total - previous_expense_total

    expense_change = current_expense_total - previous_expense_total
    expense_change_percent = (expense_change / previous_expense_total * 100) if previous_expense_total > 0 else 0

    income_change = current_income_total - previous_income_total
    income_change_percent = (income_change / previous_income_total * 100) if previous_income_total > 0 else 0

    # Category breakdown (expenses only)
    current_by_category = current_expense_df.groupby("category")["amount"].sum().sort_values(
        ascending=False
    )
    previous_by_category = previous_expense_df.groupby("category")["amount"].sum().sort_values(
        ascending=False
    )

    # Person breakdown (expenses only)
    current_by_person = current_expense_df.groupby("person")["amount"].sum().sort_values(
        ascending=False
    )

    return {
        "current_month": str(current_month),
        "previous_month": str(previous_month),
        "current_expense_total": current_expense_total,
        "current_income_total": current_income_total,
        "current_net": current_net,
        "previous_expense_total": previous_expense_total,
        "previous_income_total": previous_income_total,
        "previous_net": previous_net,
        "expense_change": expense_change,
        "expense_change_percent": expense_change_percent,
        "income_change": income_change,
        "income_change_percent": income_change_percent,
        "current_by_category": current_by_category,
        "previous_by_category": previous_by_category,
        "current_by_person": current_by_person,
        "current_expense_df": current_expense_df,
        "current_income_df": current_income_df,
    }


def create_charts(data):
    """Create visualization charts"""
    print("📊 Creating charts...")
    chart_files = []

    # Chart 1: Income vs Expense comparison
    fig, ax = plt.subplots(figsize=(10, 6))
    months = [data["previous_month"], data["current_month"]]
    income = [data["previous_income_total"], data["current_income_total"]]
    expense = [data["previous_expense_total"], data["current_expense_total"]]

    x = range(len(months))
    width = 0.35

    bars1 = ax.bar([i - width / 2 for i in x], income, width, label="Thu nhập", color="#2ecc71")
    bars2 = ax.bar([i + width / 2 for i in x], expense, width, label="Chi tiêu", color="#e74c3c")

    ax.set_ylabel("Số tiền (VND)", fontsize=11)
    ax.set_title("So sánh Thu nhập vs Chi tiêu", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(months)
    ax.legend()
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"₫{x/1e6:.1f}M"))

    plt.tight_layout()
    chart_path = REPORTS_DIR / "chart_income_vs_expense.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    chart_files.append(chart_path)
    print(f"  ✅ Saved: {chart_path}")

    # Chart 2: Category comparison (pie chart for current month)
    if not data["current_by_category"].empty:
        fig, ax = plt.subplots(figsize=(10, 8))
        colors = plt.cm.Set3(range(len(data["current_by_category"])))
        wedges, texts, autotexts = ax.pie(
            data["current_by_category"].values,
            labels=data["current_by_category"].index,
            autopct="%1.1f%%",
            colors=colors,
            startangle=90,
        )
        ax.set_title(f"Chi tiêu theo hạng mục - {data['current_month']}", fontsize=14, fontweight="bold")
        plt.setp(autotexts, size=9, weight="bold")
        plt.setp(texts, size=10)
        plt.tight_layout()

        chart_path = REPORTS_DIR / "chart_category_pie.png"
        plt.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close()
        chart_files.append(chart_path)
        print(f"  ✅ Saved: {chart_path}")

    # Chart 2: Expense trend (bar chart)
    fig, ax = plt.subplots(figsize=(10, 6))
    months = [data["previous_month"], data["current_month"]]
    amounts = [data["previous_expense_total"], data["current_expense_total"]]
    colors_bar = ["#3498db", "#2ecc71" if data["expense_change"] < 0 else "#e74c3c"]

    bars = ax.bar(months, amounts, color=colors_bar, width=0.5)
    ax.set_ylabel("Số tiền (VND)", fontsize=11)
    ax.set_title("Xu hướng chi tiêu", fontsize=14, fontweight="bold")

    # Add value labels on bars
    for bar, amount in zip(bars, amounts):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height,
            f"₫{amount:,.0f}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )

    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"₫{x/1e6:.1f}M"))
    plt.tight_layout()

    chart_path = REPORTS_DIR / "chart_month_comparison.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    chart_files.append(chart_path)
    print(f"  ✅ Saved: {chart_path}")

    # Chart 3: Category comparison across months
    if not data["previous_by_category"].empty:
        fig, ax = plt.subplots(figsize=(12, 6))

        categories = sorted(
            set(data["current_by_category"].index) | set(data["previous_by_category"].index)
        )
        current_vals = [data["current_by_category"].get(cat, 0) for cat in categories]
        previous_vals = [data["previous_by_category"].get(cat, 0) for cat in categories]

        x = range(len(categories))
        width = 0.35

        ax.bar([i - width / 2 for i in x], previous_vals, width, label=data["previous_month"], color="#3498db")
        ax.bar([i + width / 2 for i in x], current_vals, width, label=data["current_month"], color="#2ecc71")

        ax.set_xlabel("Hạng mục", fontsize=11)
        ax.set_ylabel("Số tiền (VND)", fontsize=11)
        ax.set_title("So sánh chi tiêu theo hạng mục", fontsize=14, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(categories, rotation=45, ha="right")
        ax.legend()
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"₫{x/1e6:.1f}M"))

        plt.tight_layout()
        chart_path = REPORTS_DIR / "chart_category_comparison.png"
        plt.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close()
        chart_files.append(chart_path)
        print(f"  ✅ Saved: {chart_path}")

    # Chart 4: Person breakdown (current month)
    if not data["current_by_person"].empty:
        fig, ax = plt.subplots(figsize=(10, 6))
        colors = plt.cm.Pastel1(range(len(data["current_by_person"])))
        bars = ax.barh(data["current_by_person"].index, data["current_by_person"].values, color=colors)
        ax.set_xlabel("Số tiền (VND)", fontsize=11)
        ax.set_title(f"Chi tiêu theo người - {data['current_month']}", fontsize=14, fontweight="bold")
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"₫{x/1e6:.1f}M"))

        # Add value labels
        for bar, amount in zip(bars, data["current_by_person"].values):
            ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2, f"  ₫{amount:,.0f}",
                   va="center", fontsize=10, fontweight="bold")

        plt.tight_layout()
        chart_path = REPORTS_DIR / "chart_person_breakdown.png"
        plt.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close()
        chart_files.append(chart_path)
        print(f"  ✅ Saved: {chart_path}")

    return chart_files


def create_html_report(data, chart_files, for_email=True):
    """Create HTML email report

    Args:
        data: Processed expense data
        chart_files: List of chart file paths
        for_email: If True, uses cid: references for email. If False, uses file paths for local viewing.
    """
    current_month = data["current_month"]
    previous_month = data["previous_month"]
    current_income = data["current_income_total"]
    current_expense = data["current_expense_total"]
    current_net = data["current_net"]
    previous_income = data["previous_income_total"]
    previous_expense = data["previous_expense_total"]
    previous_net = data["previous_net"]
    expense_change = data["expense_change"]
    expense_change_percent = data["expense_change_percent"]
    income_change = data["income_change"]
    income_change_percent = data["income_change_percent"]

    expense_change_indicator = "📈" if expense_change >= 0 else "📉"
    expense_change_color = "#e74c3c" if expense_change >= 0 else "#2ecc71"
    income_change_indicator = "📈" if income_change >= 0 else "📉"
    income_change_color = "#2ecc71" if income_change >= 0 else "#e74c3c"

    # Top categories
    top_categories = data["current_by_category"].head(5)
    top_categories_html = "".join(
        [
            f"<tr><td>{cat}</td><td align='right'>₫{amt:,.0f}</td></tr>"
            for cat, amt in top_categories.items()
        ]
    )

    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                background: #f5f5f5;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 700px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #2c3e50;
                text-align: center;
                border-bottom: 3px solid #3498db;
                padding-bottom: 15px;
            }}
            h2 {{
                color: #34495e;
                margin-top: 25px;
                border-left: 4px solid #3498db;
                padding-left: 15px;
            }}
            .summary {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin: 20px 0;
            }}
            .summary-card {{
                background: #f8f9fa;
                padding: 15px;
                border-radius: 8px;
                border-left: 4px solid #3498db;
            }}
            .summary-card h3 {{
                margin: 0 0 10px 0;
                color: #7f8c8d;
                font-size: 0.9em;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            .summary-card .amount {{
                font-size: 1.5em;
                font-weight: bold;
                color: #2c3e50;
            }}
            .change {{
                font-weight: bold;
                font-size: 0.9em;
                margin-top: 5px;
            }}
            .change.positive {{
                color: #2ecc71;
            }}
            .change.negative {{
                color: #e74c3c;
            }}
            .summary-card.income {{
                border-left-color: #2ecc71;
            }}
            .summary-card.expense {{
                border-left-color: #e74c3c;
            }}
            .summary-card.net {{
                border-left-color: #3498db;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 15px 0;
            }}
            table th {{
                background: #3498db;
                color: white;
                padding: 12px;
                text-align: left;
            }}
            table td {{
                padding: 10px 12px;
                border-bottom: 1px solid #ddd;
            }}
            table tr:hover {{
                background: #f5f5f5;
            }}
            .chart-section {{
                margin: 20px 0;
                text-align: center;
            }}
            .chart-section img {{
                max-width: 100%;
                height: auto;
                border-radius: 8px;
                margin: 10px 0;
            }}
            .footer {{
                text-align: center;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                color: #7f8c8d;
                font-size: 0.9em;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 Báo cáo tài chính tháng {current_month}</h1>

            <div class="summary">
                <div class="summary-card income">
                    <h3>Thu nhập</h3>
                    <div class="amount">₫{current_income:,.0f}</div>
                    <div class="change {'positive' if income_change >= 0 else 'negative'}">
                        {'📈' if income_change >= 0 else '📉'} {'+' if income_change >= 0 else ''}{income_change:,.0f} ({income_change_percent:+.1f}%)
                    </div>
                </div>
                <div class="summary-card expense">
                    <h3>Chi tiêu</h3>
                    <div class="amount">₫{current_expense:,.0f}</div>
                    <div class="change {'negative' if expense_change >= 0 else 'positive'}">
                        {'📈' if expense_change >= 0 else '📉'} {'+' if expense_change >= 0 else ''}{expense_change:,.0f} ({expense_change_percent:+.1f}%)
                    </div>
                </div>
                <div class="summary-card net">
                    <h3>Tiết kiệm</h3>
                    <div class="amount">₫{current_net:,.0f}</div>
                    <div class="change {'positive' if current_net >= 0 else 'negative'}">
                        {'✅' if current_net >= 0 else '⚠️'} {'+' if current_net >= 0 else ''}{current_net:,.0f}
                    </div>
                </div>
            </div>

            <h2>💸 Top 5 Hạng mục chi tiêu</h2>
            <table>
                <thead>
                    <tr>
                        <th>Hạng mục</th>
                        <th align="right">Số tiền</th>
                    </tr>
                </thead>
                <tbody>
                    {top_categories_html}
                </tbody>
            </table>

            <h2>📈 Biểu đồ chi tiêu</h2>
    """

    # Add chart images
    if for_email:
        for i in range(len(chart_files)):
            html += f'<div class="chart-section"><img src="cid:chart{i}" alt="Chart {i}"></div>\n'
    else:
        for chart_file in chart_files:
            html += f'<div class="chart-section"><img src="{chart_file}" alt="Chart"></div>\n'

    html += f"""
            <div class="footer">
                <p>Báo cáo được tạo tự động vào {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                <p><em>Quản lý chi tiêu hàng tháng</em></p>
            </div>
        </div>
    </body>
    </html>
    """

    return html


def send_email(html_content, chart_files):
    """Send email report"""
    print("📧 Sending email report...")

    msg = MIMEMultipart("related")
    msg["Subject"] = f"📊 Báo cáo chi tiêu - {datetime.now().strftime('%B %Y')}"
    msg["From"] = GMAIL_EMAIL
    msg["To"] = ", ".join([e.strip() for e in EMAIL_RECIPIENTS])

    # Attach HTML content
    msg_alternative = MIMEMultipart("alternative")
    msg.attach(msg_alternative)
    msg_alternative.attach(MIMEText(html_content, "html", _charset="utf-8"))

    # Attach chart images
    for i, chart_file in enumerate(chart_files):
        with open(chart_file, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"inline; filename= {chart_file.name}")
            part.add_header("Content-ID", f"<chart{i}>")
            msg.attach(part)

    # Send email
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f"✅ Email sent to: {', '.join(EMAIL_RECIPIENTS)}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        sys.exit(1)


def main(demo_mode=False):
    """Main execution"""
    print("=" * 50)
    print("🚀 Expense Report Generator")
    print("=" * 50)

    validate_config(demo_mode=demo_mode)

    # Fetch and process data
    if demo_mode:
        df = load_csv_data("sample_data.csv")
    else:
        df = fetch_notion_data()

    data = process_data(df)

    # Create visualizations
    chart_files = create_charts(data)

    # Generate HTML reports (local viewing version)
    html_report_local = create_html_report(data, chart_files, for_email=False)
    report_path_local = REPORTS_DIR / f"report_{data['current_month']}_preview.html"
    with open(report_path_local, "w", encoding="utf-8") as f:
        f.write(html_report_local)
    print(f"💾 Preview saved to: {report_path_local}")

    # Generate HTML report for email
    html_report_email = create_html_report(data, chart_files, for_email=True)
    report_path = REPORTS_DIR / f"report_{data['current_month']}.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_report_email)
    print(f"💾 Email report saved to: {report_path}")

    # Send email (skip in demo mode)
    if not demo_mode:
        send_email(html_report_email, chart_files)
    else:
        print("⏭️  Email sending skipped in demo mode")

    print("=" * 50)
    print("✅ Report generated successfully!")
    print("=" * 50)


if __name__ == "__main__":
    import sys as sys_module
    demo_mode = "--demo" in sys_module.argv or "DEMO_MODE" in os.environ
    main(demo_mode=demo_mode)
