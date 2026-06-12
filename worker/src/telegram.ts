/**
 * Telegram API helpers
 */

interface TelegramUpdate {
  update_id: number;
  message?: {
    message_id: number;
    from: {
      id: number;
      is_bot: boolean;
      first_name: string;
      username?: string;
    };
    chat: {
      id: number;
      type: string;
    };
    date: number;
    text?: string;
  };
}

interface TelegramUser {
  id: number;
  first_name: string;
  username?: string;
}

export function extractUserAndMessage(
  update: TelegramUpdate
): { user: TelegramUser | null; text: string | null } {
  if (!update.message || !update.message.text || !update.message.from) {
    return { user: null, text: null };
  }

  const user = {
    id: update.message.from.id,
    first_name: update.message.from.first_name,
    username: update.message.from.username,
  };

  return {
    user,
    text: update.message.text,
  };
}

/**
 * Send message to Telegram user
 */
export async function sendTelegramMessage(
  botToken: string,
  chatId: number,
  text: string
): Promise<Response> {
  const url = `https://api.telegram.org/bot${botToken}/sendMessage`;

  return fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      parse_mode: "HTML",
    }),
  });
}

/**
 * Validate Telegram update signature
 * Telegram sends X-Telegram-Bot-API-Secret-Token header with each request
 * For production, you should verify this token matches what you set
 */
export function validateTelegramRequest(
  request: Request,
  botToken: string
): boolean {
  // Note: This is a basic check. For production, implement proper HMAC verification
  // if you've set a secret token in Telegram's setWebhook
  const secretToken = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
  if (!secretToken) {
    // Telegram webhook without secret token - allow for now, but log
    console.log("No secret token in request");
    return true;
  }
  // If you set a secret token, verify it here
  // return secretToken === YOUR_SECRET_TOKEN;
  return true;
}

/**
 * Verify Telegram bot token format
 */
export function isValidBotToken(token: string): boolean {
  // Telegram bot token format: 123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ
  return /^\d+:[A-Za-z0-9_-]{25,}$/.test(token);
}
