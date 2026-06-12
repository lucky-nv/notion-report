# Notion Expense Bot

Telegram bot to log personal expenses to Notion Database using Cloudflare Worker.

## Features

✅ Parse expense messages with smart amount parsing
✅ Support k (thousand), tr (million), or plain numbers
✅ Optional notes in same message (e.g., "grab 120k đi sân bay")
✅ Create pages in Notion Database automatically
✅ Only allow authorized user (via ALLOWED_USER_ID)
✅ VietNamese currency formatting (VND)
✅ No server, no database, no cost (uses free tiers)
✅ TypeScript with strict type checking
✅ Production-ready error handling

## Tech Stack

- **Cloudflare Workers** - Serverless execution
- **Notion API** - Database backend
- **Telegram API** - User interface
- **TypeScript** - Type safety
- **Wrangler** - Cloudflare CLI

## Usage

Send message to bot:
- `ăn trưa 50k` → logs 50,000 VND to "ăn trưa" category
- `grab 120k đi sân bay` → logs 120,000 with note
- `lương 20tr` → logs 20,000,000 for salary
- `mua sách 250k` → logs 250,000 to books

Bot replies with confirmation and stores in Notion DB.

## Setup

See [QUICK_START.md](./QUICK_START.md) for 7-step setup.

Or [SETUP.md](./SETUP.md) for detailed guide with troubleshooting.

## Project Structure

```
src/
├── index.ts    - Main worker handler
├── parser.ts   - Message parsing & formatting
├── notion.ts   - Notion API client
└── telegram.ts - Telegram API helpers
```

## Environment Variables

```
TELEGRAM_BOT_TOKEN      - Your Telegram bot token from @BotFather
NOTION_TOKEN            - Notion integration token
NOTION_DATABASE_ID      - Target Notion database ID
ALLOWED_USER_ID         - Your Telegram user ID (numeric)
```

## Development

```bash
npm install
npm run dev          # Local development server
npm run deploy       # Deploy to Cloudflare
npm run tail         # Live logs
npm run type-check   # TypeScript check
```

## Cost

**$0** - Uses only free tiers:
- Cloudflare Workers: 100,000 requests/day free
- Notion API: Free for all
- Telegram API: Free

## License

MIT
