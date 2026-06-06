#!/bin/bash
# Setup script for Notion Expense Report

set -e

echo "=========================================="
echo "🚀 Notion Expense Report Setup"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "✅ Python found: $(python3 --version)"
echo ""

# Create virtual environment
echo "📦 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1
echo "✅ Dependencies installed"
echo ""

# Create .env file if not exists
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
    echo "✅ .env file created"
    echo ""
    echo "⚠️  Please edit .env file and add your credentials:"
    echo "   - NOTION_API_KEY"
    echo "   - NOTION_DATABASE_ID"
    echo "   - GMAIL_EMAIL"
    echo "   - GMAIL_APP_PASSWORD"
    echo "   - EMAIL_RECIPIENTS"
else
    echo "✅ .env file already exists"
fi

# Create reports directory
echo "📂 Creating reports directory..."
mkdir -p reports
echo "✅ reports directory ready"
echo ""

echo "=========================================="
echo "✅ Setup completed!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials:"
echo "   nano .env"
echo ""
echo "2. Test the script locally:"
echo "   python expense_report.py"
echo ""
echo "3. Push to GitHub and add secrets:"
echo "   git add ."
echo "   git commit -m 'Add expense report automation'"
echo "   git push"
echo ""
echo "4. Configure GitHub Secrets (see GITHUB_SECRETS_SETUP.md)"
echo ""
echo "For more details, see README.md"
echo ""
