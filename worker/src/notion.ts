/**
 * Notion API helpers
 */

interface NotionPageProperties {
  "Tên (tuỳ chọn)": {
    title: Array<{
      text: {
        content: string;
      };
    }>;
  };
  "Số tiền": {
    number: number;
  };
  "Hạng mục": {
    select: {
      name: string;
    };
  };
  "Ngày": {
    date: {
      start: string;
    };
  };
  "Loại"?: {
    select: {
      name: string;
    };
  };
  "Người nhập"?: {
    select: {
      name: string;
    };
  };
  "Note"?: {
    rich_text: Array<{
      text: {
        content: string;
      };
    }>;
  };
}

export async function createNotionPage(
  token: string,
  databaseId: string,
  data: {
    name: string;
    amount: number;
    date: string;
    category: string;
    type?: "Chi tiêu" | "Thu nhập";
    person?: "Chồng" | "Vợ";
    merchant?: string;
    notes?: string;
    description?: string;
  }
): Promise<{ success: boolean; error?: string; pageId?: string; page?: any }> {
  const url = "https://api.notion.com/v1/pages";

  const properties: NotionPageProperties = {
    "Tên (tuỳ chọn)": {
      title: [
        {
          text: {
            content: data.name,
          },
        },
      ],
    },
    "Số tiền": {
      number: data.amount,
    },
    "Hạng mục": {
      select: {
        name: data.category,
      },
    },
    "Ngày": {
      date: {
        start: data.date,
      },
    },
  };

  if (data.type) {
    properties["Loại"] = {
      select: {
        name: data.type,
      },
    };
  }

  if (data.person) {
    properties["Người nhập"] = {
      select: {
        name: data.person,
      },
    };
  }

  if (data.notes || data.merchant) {
    properties["Note"] = {
      rich_text: [
        {
          text: {
            content: data.notes || data.merchant || "",
          },
        },
      ],
    };
  }

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        parent: {
          type: "database_id",
          database_id: databaseId,
        },
        properties,
      }),
    });

    if (!response.ok) {
      const errorData = await response.text();
      console.error("Notion API error:", errorData);
      return {
        success: false,
        error: `Lỗi Notion: ${response.status}`,
      };
    }

    const result = await response.json();
    return {
      success: true,
      pageId: result.id,
      page: result,
    };
  } catch (error) {
    console.error("Create Notion page error:", error);
    return {
      success: false,
      error: "Lỗi kết nối Notion",
    };
  }
}

/**
 * Validate Notion token and database access
 */
export async function validateNotionAccess(
  token: string,
  databaseId: string
): Promise<{ valid: boolean; error?: string }> {
  const url = `https://api.notion.com/v1/databases/${databaseId}`;

  try {
    const response = await fetch(url, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Notion-Version": "2022-06-28",
      },
    });

    if (!response.ok) {
      return {
        valid: false,
        error: `Database not found or no permission: ${response.status}`,
      };
    }

    return { valid: true };
  } catch (error) {
    return {
      valid: false,
      error: String(error),
    };
  }
}
