import {
  extractUserAndMessage,
  sendTelegramMessage,
  isValidBotToken,
} from "./telegram";
import { createNotionPage, validateNotionAccess } from "./notion";
import { parseExpense, formatVND, getCurrentDateISO } from "./parser";
import type { ExportedHandler, ScheduledController } from "@cloudflare/workers-types";

interface Env {
  TELEGRAM_BOT_TOKEN: string;
  NOTION_TOKEN: string;
  NOTION_DATABASE_ID: string;
  ALLOWED_USER_IDS: string;
  ALLOWED_GROUP_IDS?: string;
}

export default {
  async fetch(request, env: Env) {
    try {
      // Only accept POST from Telegram webhook
      if (request.method !== "POST") {
        return new Response("Method not allowed", { status: 405 }) as any;
      }

      // Parse Telegram webhook body
      const update = (await request.json()) as any;

      // Extract user and message
      const { user, text } = extractUserAndMessage(update);

      if (!user || !text) {
        // Invalid update, silently ignore
        return new Response("ok", { status: 200 }) as any;
      }

      // Get chat ID (user ID or group ID)
      const chatId = update.message?.chat?.id;
      if (!chatId) {
        return new Response("ok", { status: 200 }) as any;
      }

      // Check if user/group is allowed
      const allowedUserIds = env.ALLOWED_USER_IDS.split(",")
        .map((id) => parseInt(id.trim(), 10))
        .filter((id) => !isNaN(id));

      const allowedGroupIds = env.ALLOWED_GROUP_IDS
        ? env.ALLOWED_GROUP_IDS.split(",")
            .map((id) => parseInt(id.trim(), 10))
            .filter((id) => !isNaN(id))
        : [];

      const allAllowedIds = [...allowedUserIds, ...allowedGroupIds];

      console.log(`ChatID: ${chatId}, Allowed: ${allAllowedIds.join(", ")}`);

      if (!allAllowedIds.includes(chatId)) {
        // Silently ignore unauthorized users/groups
        console.log(`Unauthorized chat ${chatId} tried to use bot`);
        return new Response("ok", { status: 200 }) as any;
      }

      console.log(`Message from ${user.first_name}: "${text}"`);

      // Parse the expense message
      const sender = user.username ? `@${user.username}` : undefined;
      const parseResult = parseExpense(text, sender);

      if (!parseResult.success) {
        // Send error guidance message
        await sendTelegramMessage(
          env.TELEGRAM_BOT_TOKEN,
          chatId,
          parseResult.error || "Lỗi không xác định"
        );
        return new Response("ok", { status: 200 }) as any;
      }

      // Create page in Notion
      const notionResult = await createNotionPage(env.NOTION_TOKEN, env.NOTION_DATABASE_ID, {
        name: parseResult.name || parseResult.merchant || "Transaction",
        amount: parseResult.amount || 0,
        date: parseResult.date || getCurrentDateISO(),
        category: parseResult.category || "💳 Khác",
        type: parseResult.type,
        person: parseResult.person,
        merchant: parseResult.merchant,
        notes: parseResult.notes,
        description: parseResult.description,
      });

      if (!notionResult.success) {
        // Send error message
        await sendTelegramMessage(
          env.TELEGRAM_BOT_TOKEN,
          chatId,
          `❌ Lỗi: ${notionResult.error}`
        );
        return new Response("ok", { status: 200 }) as any;
      }

      // Send success message with full record details
      const successMsg = `✅ Đã ghi:
<b>${parseResult.merchant}</b> - ${formatVND(parseResult.amount || 0)}
${parseResult.category} | ${parseResult.type}
👤 ${parseResult.person}
📅 ${parseResult.date}
${parseResult.notes ? `📝 ${parseResult.notes}` : ""}`;
      await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId, successMsg);

      return new Response("ok", { status: 200 }) as any;
    } catch (error) {
      console.error("Worker error:", error);
      return new Response("Internal error", { status: 500 }) as any;
    }
  },

  // Health check endpoint
  async scheduled(_event: ScheduledController, _env: Env): Promise<void> {
    console.log("Scheduled event triggered");
  },
} satisfies ExportedHandler<Env>;
