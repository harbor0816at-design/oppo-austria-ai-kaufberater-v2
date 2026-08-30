export const COPY = {
  de: {
    greeting: "Hallo! 👋 Ich helfe dir gerne bei der Auswahl. Was ist dir bei deinem nächsten Smartphone besonders wichtig?",
    placeholder: "Schreib eine Nachricht …",
    send: "Senden",
    clear: "Verlauf löschen",
    online: "Offizielle Produktberatung · AI",
    quick: ["Kamera", "Akku", "Preis", "Modelle vergleichen", "Ich weiß noch nicht"],
    user: "Du",
    assistant: "OPPO Kaufberatung · AI",
    notify: "Zum Verkaufsstart benachrichtigen",
    view: "Produkt ansehen",
    buy: "Jetzt kaufen",
    preorder: "Jetzt vorbestellen",
    sources: "Quellen",
    official: "OPPO offizielle Information",
    status: "Status",
    price: "Preis",
    shipping: "Versand",
    regions: "Regionen",
    features: "Highlights",
    email: "E-Mail",
    whatsapp: "WhatsApp",
    contact: "Kontakt",
    consent: "Ich möchte Informationen zum Verkaufsstart und relevante OPPO Angebote über den gewählten Kanal erhalten. Die Einwilligung kann jederzeit widerrufen werden.",
    subscribe: "Vormerkung speichern",
    subscribed: "Deine Vormerkung wurde gespeichert.",
    close: "Schließen",
    error: "Die Antwort konnte nicht geladen werden.",
    retry: "Bitte versuche es erneut.",
    noProducts: "Aktuell sind noch keine veröffentlichten Produkte in Source_B hinterlegt.",
    admin: "Admin"
  },
  en: {
    greeting: "Hello! 👋 I’m happy to help you choose. What matters most in your next smartphone?",
    placeholder: "Write a message …",
    send: "Send",
    clear: "Clear history",
    online: "Official product guidance · AI",
    quick: ["Camera", "Battery", "Price", "Compare models", "I’m not sure yet"],
    user: "You",
    assistant: "OPPO Consultation · AI",
    notify: "Notify me at launch",
    view: "View product",
    buy: "Buy now",
    preorder: "Pre-order now",
    sources: "Sources",
    official: "Official OPPO information",
    status: "Status",
    price: "Price",
    shipping: "Shipping",
    regions: "Regions",
    features: "Highlights",
    email: "Email",
    whatsapp: "WhatsApp",
    contact: "Contact",
    consent: "I would like to receive launch information and relevant OPPO offers via the selected channel. I can withdraw my consent at any time.",
    subscribe: "Save notification",
    subscribed: "Your notification request has been saved.",
    close: "Close",
    error: "The answer could not be loaded.",
    retry: "Please try again.",
    noProducts: "No published consumer products are currently available in Source_B.",
    admin: "Admin"
  },
  zh: {
    greeting: "你好！👋 我可以帮助你挑选更合适的手机。你最看重下一部手机的哪些方面？",
    placeholder: "输入消息……",
    send: "发送",
    clear: "清除记录",
    online: "官方产品导购 · AI",
    quick: ["相机", "续航", "价格", "机型对比", "我还不确定"],
    user: "你",
    assistant: "OPPO 智能导购 · AI",
    notify: "开售时通知我",
    view: "查看产品",
    buy: "立即购买",
    preorder: "立即预订",
    sources: "来源",
    official: "OPPO 官方信息",
    status: "状态",
    price: "价格",
    shipping: "发货",
    regions: "地区",
    features: "核心亮点",
    email: "邮箱",
    whatsapp: "WhatsApp",
    contact: "联系方式",
    consent: "我愿意通过所选渠道接收开售信息和相关 OPPO 优惠，并可随时撤回授权。",
    subscribe: "保存开售通知",
    subscribed: "已保存开售通知。",
    close: "关闭",
    error: "当前无法加载回答。",
    retry: "请稍后再试。",
    noProducts: "目前 Source_B 中还没有已发布的消费者商品数据。",
    admin: "后台"
  }
};

export function detectLanguage(text = "") {
  const value = String(text).trim().toLowerCase();
  if (/[\u3400-\u9fff]/u.test(value)) return "zh";
  const de = (value.match(/\b(ich|welche|welcher|welches|akku|preis|kamera|möchte|brauche|für|mit|versand|garantie)\b/gi) || []).length
    + (/[äöüß]/i.test(value) ? 2 : 0);
  const en = (value.match(/\b(which|what|best|battery|price|camera|recommend|compare|need|want|with|for|shipping|warranty)\b/gi) || []).length;
  return en > de ? "en" : "de";
}

export function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

function safeHttpUrl(value = "") {
  try {
    const url = new URL(String(value));
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function inline(value) {
  const raw = String(value);
  const tokens = [];
  const tokenized = raw
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, url) => {
      const safe = safeHttpUrl(url);
      if (!safe) return label;
      const token = `@@LINK${tokens.length}@@`;
      tokens.push(`<a class="inline-link" href="${escapeHtml(safe)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`);
      return token;
    })
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, (match, prefix, url) => {
      const safe = safeHttpUrl(url);
      if (!safe) return match;
      const token = `@@LINK${tokens.length}@@`;
      tokens.push(`<a class="inline-link" href="${escapeHtml(safe)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a>`);
      return `${prefix}${token}`;
    });

  let html = escapeHtml(tokenized)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
  tokens.forEach((token, index) => {
    html = html.replaceAll(`@@LINK${index}@@`, token);
  });
  return html;
}

function splitTableRow(line) {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map(cell => cell.trim());
}

export function renderMarkdown(markdown = "") {
  const lines = String(markdown).split(/\r?\n/);
  const parts = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const next = lines[index + 1] || "";

    if (
      line.includes("|")
      && next.includes("|")
      && splitTableRow(next).every(cell => /^:?-{3,}:?$/.test(cell))
    ) {
      const header = splitTableRow(line);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].includes("|")) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      parts.push(
        `<div class="table-wrap"><table><thead><tr>${header.map(cell => `<th>${inline(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${inline(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
      );
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) {
        items.push(`<li>${inline(lines[index].replace(/^[-*]\s+/, ""))}</li>`);
        index += 1;
      }
      parts.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    if (/^#{1,3}\s+/.test(line)) {
      const level = Math.min(3, line.match(/^#+/)[0].length);
      parts.push(`<h${level}>${inline(line.replace(/^#{1,3}\s+/, ""))}</h${level}>`);
      index += 1;
      continue;
    }

    if (line.trim()) parts.push(`<p>${inline(line)}</p>`);
    index += 1;
  }

  return parts.join("");
}

export function statusLabel(status, language) {
  const labels = {
    de: { launched: "Verfügbar", pre_order: "Vorbestellung", unannounced: "Noch nicht veröffentlicht" },
    en: { launched: "Available", pre_order: "Pre-order", unannounced: "Not published yet" },
    zh: { launched: "已上市", pre_order: "预订中", unannounced: "尚未发布" }
  };
  return labels[language]?.[status] || status || "";
}

export async function postEvent(apiBase, eventName, sessionId, payload = {}) {
  try {
    await fetch(`${apiBase}/api/analytics/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_name: eventName,
        session_id: sessionId,
        payload
      })
    });
  } catch {
    // Analytics must never block the user experience.
  }
}
