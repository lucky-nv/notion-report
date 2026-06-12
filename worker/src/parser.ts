/**
 * Parse expense message from user
 * Examples:
 * - "ăn trưa 50k" => { category: "ăn trưa", amount: 50000, note: "" }
 * - "grab 120k đi sân bay" => { category: "grab", amount: 120000, note: "đi sân bay" }
 * - "lương 20tr" => { category: "lương", amount: 20000000, note: "" }
 */

interface ParseResult {
  success: boolean;
  error?: string;
  // Notion fields
  name?: string; // Title
  date?: string; // ISO format YYYY-MM-DD
  amount?: number;
  category?: string; // Emoji category
  type?: "Chi tiêu" | "Thu nhập"; // Loại
  person?: "Chồng" | "Vợ"; // Người nhập
  merchant?: string; // For notes
  notes?: string;
  description?: string;
}

function getTransactionCategory(merchantName: string): string {
  if (!merchantName) return "💳 Khác";

  const merchantLower = merchantName.toLowerCase();

  const categories: Record<string, { keywords: string[]; score: number }> = {
    "🛒 Mua sắm": {
      keywords: ["shop", "store", "mall", "aeon", "vinmart", "amazon", "apple",
        "shopping", "retail", "market", "supermarket", "lazada", "shopee",
        "tiki", "sendo", "fashion", "clothing", "electronics", "wincommerce"],
      score: 10
    },
    "🍽️ Ăn uống": {
      keywords: ["restaurant", "cafe", "coffee", "food", "quán", "nhà hàng", "ăn", "drink",
        "pizza", "burger", "noodle", "pho", "bánh", "cơm", "trà", "nước", "beer",
        "bar", "pub", "bistro", "ca phe", "coffee shop", "fast food"],
      score: 10
    },
    "⛽ Xăng dầu": {
      keywords: ["fuel", "gas", "petrol", "xăng", "dầu", "shell", "bp", "esso"],
      score: 10
    },
    "✈️ Du lịch": {
      keywords: ["hotel", "airline", "flight", "khách sạn", "bay", "booking", "agoda", "travel"],
      score: 10
    },
    "⚕️ Y tế": {
      keywords: ["hospital", "clinic", "pharmacy", "bệnh viện", "nhà thuốc", "doctor", "medical"],
      score: 10
    },
    "📱 Ví điện tử": {
      keywords: ["momo", "zalopay", "apple pay", "google pay", "paypal", "topup"],
      score: 10
    },
  };

  const scores: Record<string, number> = {};
  for (const [category, rules] of Object.entries(categories)) {
    let score = 0;
    for (const keyword of rules.keywords) {
      if (keyword.includes(merchantLower) || merchantLower.includes(keyword)) {
        score += rules.score;
      }
    }
    if (score > 0) scores[category] = score;
  }

  if (Object.keys(scores).length > 0) {
    return Object.entries(scores).sort(([, a], [, b]) => b - a)[0][0];
  }

  return "💳 Khác";
}

export function parseExpense(message: string, sender?: string): ParseResult {
  const trimmed = message.trim();

  // Match pattern: <category text> <amount with k/tr/nothing>
  // Amount can be: 50k, 50000, 20tr, 20.5k, etc.
  const pattern = /^(.+?)\s+(\d+(?:[.,]\d+)?)\s*(k|tr|K|TR)?\s*(.*?)$/;
  const match = trimmed.match(pattern);

  if (!match) {
    return {
      success: false,
      error: "Không hiểu định dạng. Nhắn kiểu: ăn trưa 50k hoặc grab 120k đi sân bay",
    };
  }

  const [, categoryPart, numberPart, unit, notesPart] = match;

  // Parse amount
  let amount = parseFloat(numberPart.replace(",", "."));

  // Apply unit multiplier
  if (unit) {
    const unitLower = unit.toLowerCase();
    if (unitLower === "k") {
      amount *= 1000;
    } else if (unitLower === "tr") {
      amount *= 1000000;
    }
  }

  // Validate amount
  if (isNaN(amount) || amount <= 0) {
    return {
      success: false,
      error: "Số tiền không hợp lệ",
    };
  }

  const merchantName = categoryPart.trim();
  const notes = notesPart.trim();

  // Validate category (at least 2 characters, reasonable length)
  if (merchantName.length < 2 || merchantName.length > 100) {
    return {
      success: false,
      error: "Tên danh mục không hợp lệ",
    };
  }

  // Determine transaction type: "Thu nhập" if contains "Lương", otherwise "Chi tiêu"
  const type: "Chi tiêu" | "Thu nhập" =
    trimmed.toLowerCase().includes("lương") ? "Thu nhập" : "Chi tiêu";

  // Determine person: "Chồng" if sender is @lucky_t01, otherwise "Vợ"
  const person: "Chồng" | "Vợ" = sender === "@lucky_t01" ? "Chồng" : "Vợ";

  // Get Notion category
  const notionCategory = getTransactionCategory(merchantName);

  return {
    success: true,
    name: `${merchantName}${notes ? " - " + notes : ""}`.slice(0, 100),
    date: getCurrentDateISO(),
    amount: Math.round(amount),
    category: notionCategory,
    type,
    person,
    merchant: merchantName,
    notes,
    description: `${type === "Thu nhập" ? "💰" : "💸"} ${merchantName}`,
  };
}

/**
 * Format amount to Vietnamese currency
 */
export function formatVND(amount: number): string {
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    minimumFractionDigits: 0,
  }).format(amount);
}

/**
 * Get current date in ISO format for Notion
 */
export function getCurrentDateISO(): string {
  return new Date().toISOString().split("T")[0];
}
