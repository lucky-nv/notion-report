# Notion Expense Report Automation

Tự động tổng hợp chi tiêu hàng tháng từ Notion Database, so sánh với tháng trước, và gửi báo cáo qua email.

## 📋 Cấu hình

### 1. Local Development Setup

**Bước 1: Copy file env**
```bash
cp .env.example .env
```

**Bước 2: Điền thông tin vào `.env`**
```env
NOTION_API_KEY=your_notion_api_key_here
NOTION_DATABASE_ID=your_database_id_here
GMAIL_EMAIL=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_specific_password_here
EMAIL_RECIPIENTS=recipient1@gmail.com,recipient2@gmail.com
TIMEZONE=Asia/Ho_Chi_Minh
```

### 2. Lấy thông tin từ Notion

**Notion API Key:**
1. Truy cập https://www.notion.so/profile/integrations
2. Tạo "New integration" với tên "Expense Report"
3. Copy token từ phần "Secrets"

**Database ID:**
1. Mở Notion database chi tiêu
2. URL có dạng: `https://www.notion.so/[workspace]/[DATABASE_ID]?v=...`
3. Lấy phần DATABASE_ID (32 ký tự, hoặc dấu gạch ngang: `12a3b4c5-d6e7-8f9a-0b1c-2d3e4f5a6b7c`)
4. **Quan trọng:** Chia sẻ database cho integration vừa tạo (nhấn share → chọn integration)

### 3. Thiết lập Gmail

**Tạo App Password:**
1. Bật 2-factor authentication: https://myaccount.google.com/security
2. Tạo App Password: https://myaccount.google.com/apppasswords
   - Chọn "Mail" và "Windows Computer" (hoặc thiết bị của bạn)
   - Google sẽ sinh password 16 ký tự
3. Copy password vào `.env` (GMAIL_APP_PASSWORD)

**Email Recipients:**
- Danh sách email nhận báo cáo, cách nhau bằng dấu phẩy

## 🚀 Chạy Script

```bash
python expense_report.py
```

Script sẽ:
- Lấy dữ liệu từ Notion
- Tính tổng chi tiêu tháng hiện tại
- So sánh với tháng trước
- Tạo charts
- Gửi báo cáo qua email

## 📅 GitHub Actions (Tự động chạy hàng tháng)

Workflow được cấu hình tự động chạy vào **ngày 1 hàng tháng lúc 09:00 AM UTC**.

### Thiết lập GitHub Secrets

1. Truy cập: Settings → Secrets and variables → Actions
2. Thêm các secrets sau:
   - `NOTION_API_KEY`
   - `NOTION_DATABASE_ID`
   - `GMAIL_EMAIL`
   - `GMAIL_APP_PASSWORD`
   - `EMAIL_RECIPIENTS`
   - `TIMEZONE` (optional)

3. `.env` sẽ được tự động tạo từ secrets khi workflow chạy

### Chạy thủ công

Nếu muốn chạy ngay, không chờ đến ngày 1:
- Truy cập: Actions → Monthly Expense Report → Run workflow

## 📁 Cấu trúc dự án

```
.
├── .env.example              # Template biến môi trường
├── .gitignore               # Bỏ qua .env khi commit
├── expense_report.py        # Script chính
├── requirements.txt         # Dependencies
└── reports/                 # Thư mục lưu báo cáo (tự tạo)
```

## ⚠️ Bảo mật

- **KHÔNG** commit file `.env` (đã thêm vào `.gitignore`)
- Sử dụng GitHub Secrets cho CI/CD
- App Password của Gmail chỉ dùng cho app này
- Database Notion phải share với integration

## 📝 Thay đổi cấu hình

- Thay đổi timezone: Sửa `TIMEZONE` trong `.env`
- Thay đổi email nhận: Sửa `EMAIL_RECIPIENTS`
- Thay đổi lịch chạy: Sửa cron expression trong `.github/workflows/expense-report.yml`
