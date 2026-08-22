import {
  COPY,
  detectLanguage,
  escapeHtml,
  postEvent,
  renderMarkdown,
  statusLabel
} from "/shared.js";

const CONFIG = window.OPPO_CONFIG || { API_BASE_URL: "" };
const API = String(CONFIG.API_BASE_URL || "").replace(/\/$/, "");
let sessionId = localStorage.getItem("oppo-session-id") || crypto.randomUUID();
localStorage.setItem("oppo-session-id", sessionId);

let language = navigator.language?.startsWith("en")
  ? "en"
  : navigator.language?.startsWith("zh")
    ? "zh"
    : "de";
let messages = [];
let busy = false;
let heroSlides = [];
let heroIndex = 0;
let heroTimer = null;
let heroTouchStart = null;
let heroLastImpression = null;
let subscribeChannel = "email";

const conversation = document.querySelector("#conversation");
const composer = document.querySelector("#composer");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const quickReplies = document.querySelector("#quick-replies");
const heroStage = document.querySelector("#hero-stage");
const heroDots = document.querySelector("#hero-dots");
const subscribeDialog = document.querySelector("#subscribe-dialog");
const subscribeForm = document.querySelector("#subscribe-form");

function copy() { return COPY[language]; }

function applyLanguage() {
  document.documentElement.lang = language;
  document.querySelector("#online-label").textContent = copy().online;
  document.querySelector("#clear-chat").textContent = copy().clear;
  input.placeholder = copy().placeholder;
  sendButton.textContent = copy().send;
  document.querySelector("#subscribe-title").textContent = copy().notify;
  document.querySelector("#contact-label").textContent = copy().contact;
  document.querySelector("#consent-label").textContent = copy().consent;
  document.querySelector("#subscribe-submit").textContent = copy().subscribe;
  document.querySelector("#subscribe-close").setAttribute("aria-label", copy().close);

  quickReplies.innerHTML = copy().quick.map(text => `<button type="button">${escapeHtml(text)}</button>`).join("");
  quickReplies.querySelectorAll("button").forEach(button => {
    button.addEventListener("click", () => {
      const label = button.textContent || "";
      postEvent(API, "quick_reply_click", sessionId, { language, label });
      sendMessage(label);
    });
  });
  renderHero();
  renderConversation();
}

function addMessage(role, content = "", cards = [], pending = false) {
  const item = { id: crypto.randomUUID(), role, content, cards, pending };
  messages.push(item);
  renderConversation();
  return item;
}

function renderConversation() {
  conversation.innerHTML = messages.map(message => {
    const label = message.role === "user" ? copy().user : copy().assistant;
    const body = message.pending && !message.content
      ? '<span class="typing"><i></i><i></i><i></i></span>'
      : renderMarkdown(message.content);
    return `<article class="message ${message.role}"><div class="message-label">${escapeHtml(label)}</div><div class="message-body">${body}${message.cards.map(renderCard).join("")}</div></article>`;
  }).join("");
  conversation.scrollTop = conversation.scrollHeight;
}

function productActionLabel(product) {
  if (product.status === "pre_order") return copy().preorder;
  if (product.status === "launched") return copy().view;
  return copy().notify;
}

function renderCard(card) {
  if (card.type === "guardrail") {
    const action = card.target_sku
      ? `<button class="card-action" data-notify="${escapeHtml(card.target_sku)}" data-product="">${escapeHtml(copy().notify)}</button>`
      : "";
    return `<section class="result-card warning"><strong>${escapeHtml(card.title || "")}</strong><p>${escapeHtml(card.message || "")}</p>${action}</section>`;
  }

  if (card.type === "launch_notification") {
    return `<section class="result-card accent"><strong>${escapeHtml(card.product_name || "")}</strong><button class="card-action" data-notify="${escapeHtml(card.target_sku || "")}" data-product="${escapeHtml(card.product_name || "")}">${escapeHtml(copy().notify)}</button></section>`;
  }

  if (card.type === "recommendation") {
    return '<div class="product-grid">' + (card.products || []).map(product => {
      const price = product.price == null ? "" : `<span class="price">€${Number(product.price).toFixed(2)}</span>`;
      const href = product.purchase_url || product.product_url || "https://www.oppo.com/at/smartphones/";
      const featureList = (product.features || []).slice(0, 3).map(feature => `<li>${escapeHtml(feature)}</li>`).join("");
      return `<article class="product-card"><div class="product-card-head"><strong>${escapeHtml(product.product_name)}</strong>${price}</div>${featureList ? `<ul>${featureList}</ul>` : ""}<a data-product-click="1" data-sku="${escapeHtml(product.sku_id || "")}" href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${escapeHtml(productActionLabel(product))}</a></article>`;
    }).join("") + "</div>";
  }

  if (card.type === "official_fact") {
    const facts = (card.facts || []).map(fact => `<div><span>${escapeHtml(fact.label)}</span><strong>${escapeHtml(fact.value)}</strong></div>`).join("");
    const link = card.purchase_url || card.product_url;
    return `<section class="result-card"><div class="source-chip">${escapeHtml(copy().official)}</div><strong>${escapeHtml(card.title || "")}</strong><div class="fact-list">${facts}</div>${link ? `<a class="inline-link" data-product-click="1" data-sku="${escapeHtml(card.sku_id || "")}" href="${escapeHtml(link)}" target="_blank" rel="noreferrer">${escapeHtml(copy().view)}</a>` : ""}</section>`;
  }

  if (card.type === "public_sources") {
    return `<section class="result-card"><strong>${escapeHtml(copy().sources)}</strong>${(card.sources || []).map(source => `<a class="source-link" href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.title)}</a>`).join("")}</section>`;
  }
  return "";
}

async function parseSSE(response, onEvent) {
  if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      let event = "message";
      const dataLines = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;
      try { onEvent(event, JSON.parse(dataLines.join("\n"))); } catch {}
    }
  }
}

async function sendMessage(text) {
  const value = String(text || input.value).trim();
  if (!value || busy) return;

  const startedAt = performance.now();
  let finalRoute = "unknown";
  let fastPath = false;
  let faqId = null;
  let recommendationSeen = false;
  let hadSseError = false;

  language = detectLanguage(value);
  if (messages.length === 1 && messages[0].role === "assistant" && !messages.some(item => item.role === "user")) {
    messages[0].content = COPY[language].greeting;
  }
  applyLanguage();
  addMessage("user", value);
  input.value = "";
  input.style.height = "auto";
  const assistant = addMessage("assistant", "", [], true);
  busy = true;
  sendButton.disabled = true;
  postEvent(API, "question_sent", sessionId, { language });

  try {
    const response = await fetch(`${API}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        channel: "web",
        source: "smartphone_finder",
        locale: language,
        message: value,
        context: { sku: null }
      })
    });

    await parseSSE(response, (event, data) => {
      if (event === "meta" && data.language) {
        language = data.language;
        applyLanguage();
      }
      if (event === "card") {
        assistant.cards.push(data);
        if (data.type === "recommendation") recommendationSeen = true;
      }
      if (event === "message") assistant.content += data.delta || "";
      if (event === "error") {
        hadSseError = true;
        assistant.content = data.message || copy().error;
      }
      if (event === "done") {
        assistant.pending = false;
        finalRoute = data.route || "unknown";
        fastPath = Boolean(data.fast_path);
        faqId = data.faq_id ?? null;
      }
      renderConversation();
    });
    assistant.pending = false;
    if (!assistant.content) assistant.content = copy().error;

    const latencyMs = Math.round(performance.now() - startedAt);
    if (hadSseError) {
      postEvent(API, "answer_error", sessionId, { language, route: finalRoute, latency_ms: latencyMs });
    } else {
      postEvent(API, "answer_completed", sessionId, { language, route: finalRoute, fast_path: fastPath, latency_ms: latencyMs });
      if (recommendationSeen) postEvent(API, "recommendation_view", sessionId, { language, route: finalRoute });
      if (faqId != null) postEvent(API, "faq_used", sessionId, { language, faq_id: faqId });
      if (finalRoute.startsWith("comparison")) postEvent(API, "comparison_view", sessionId, { language, route: finalRoute });
    }
  } catch (error) {
    assistant.pending = false;
    assistant.content = `${copy().error} ${copy().retry}`;
    postEvent(API, "answer_error", sessionId, {
      language,
      route: finalRoute,
      latency_ms: Math.round(performance.now() - startedAt),
      error_type: error?.name || "FetchError"
    });
  } finally {
    busy = false;
    sendButton.disabled = false;
    renderConversation();
    input.focus();
  }
}

function fallbackSlides() {
  return [
    { id: -1, title: "OPPO Österreich", subtitle: "Offizielle Beratung für dein nächstes Smartphone.", title_en: "OPPO Austria", subtitle_en: "Official guidance for your next smartphone.", title_zh: "OPPO 奥地利", subtitle_zh: "为你的下一部手机提供官方选购建议。", eyebrow: "OPPO KAUFBERATUNG", media_type: "image", media_url: "/assets/hero-brand.svg", cta_label: "Beratung starten", cta_label_en: "Start consultation", cta_label_zh: "开始咨询", cta_url: "#chat" },
    { id: -2, title: "Fotografie neu entdecken", subtitle: "Porträt, Reise und Nachtaufnahme — finde das passende OPPO.", title_en: "Rediscover photography", subtitle_en: "Portraits, travel and night shots — find the right OPPO.", title_zh: "重新发现影像乐趣", subtitle_zh: "人像、旅行与夜景——找到更适合你的 OPPO。", eyebrow: "OPPO IMAGING", media_type: "image", media_url: "/assets/hero-camera.svg", cta_label: "Kamera-Beratung", cta_label_en: "Camera guidance", cta_label_zh: "影像选购建议", cta_url: "#chat" },
    { id: -3, title: "OPPO in Wien erleben", subtitle: "Persönliche Beratung, Abholung und Datenübertragung im DC Tower.", title_en: "Experience OPPO in Vienna", subtitle_en: "Personal advice, pickup and data transfer at DC Tower.", title_zh: "在维也纳体验 OPPO", subtitle_zh: "在 DC Tower 享受产品咨询、自提与数据迁移服务。", eyebrow: "VIENNA SHOWROOM", media_type: "image", media_url: "/assets/hero-vienna.svg", cta_label: "Showroom entdecken", cta_label_en: "Explore the showroom", cta_label_zh: "了解线下展厅", cta_url: "https://www.oppo.com/at/" }
  ];
}

function localizedSlide(slide) {
  if (language === "en") return { title: slide.title_en || slide.title, subtitle: slide.subtitle_en || slide.subtitle, cta: slide.cta_label_en || slide.cta_label };
  if (language === "zh") return { title: slide.title_zh || slide.title, subtitle: slide.subtitle_zh || slide.subtitle, cta: slide.cta_label_zh || slide.cta_label };
  return { title: slide.title, subtitle: slide.subtitle, cta: slide.cta_label };
}

function renderHero() {
  if (!heroSlides.length) return;
  heroIndex = ((heroIndex % heroSlides.length) + heroSlides.length) % heroSlides.length;
  const slide = heroSlides[heroIndex];
  const localized = localizedSlide(slide);
  const media = slide.media_type === "video"
    ? `<video class="hero-media" autoplay muted loop playsinline src="${escapeHtml(slide.media_url)}"></video>`
    : `<img class="hero-media" src="${escapeHtml(slide.media_url)}" alt="${escapeHtml(localized.title || "OPPO")}">`;
  heroStage.innerHTML = `<article class="hero-slide">${media}<div class="hero-overlay"></div><div class="hero-copy"><p class="hero-eyebrow">${escapeHtml(slide.eyebrow || "OPPO")}</p><h2>${escapeHtml(localized.title || "")}</h2><p>${escapeHtml(localized.subtitle || "")}</p>${localized.cta && slide.cta_url ? `<a data-hero-cta="1" data-slide-id="${escapeHtml(String(slide.id))}" href="${escapeHtml(slide.cta_url)}">${escapeHtml(localized.cta)} <span>↗</span></a>` : ""}</div></article>`;
  heroDots.innerHTML = heroSlides.map((_, index) => `<button type="button" data-hero-index="${index}" class="${index === heroIndex ? "active" : ""}" aria-label="Slide ${index + 1}"></button>`).join("");
  heroDots.querySelectorAll("button").forEach(button => {
    button.addEventListener("click", () => {
      heroIndex = Number(button.dataset.heroIndex);
      restartHeroTimer();
      renderHero();
    });
  });
  const impressionKey = `${slide.id}:${heroIndex}`;
  if (heroLastImpression !== impressionKey) {
    heroLastImpression = impressionKey;
    postEvent(API, "hero_view", sessionId, { language, slide_id: slide.id, position: heroIndex });
  }
}

function moveHero(direction) { heroIndex += direction; renderHero(); restartHeroTimer(); }
function restartHeroTimer() { clearInterval(heroTimer); heroTimer = setInterval(() => { heroIndex += 1; renderHero(); }, 6500); }

async function loadHeroes() {
  try {
    const response = await fetch(`${API}/api/ui/hero-slides`);
    if (!response.ok) throw new Error("hero fetch failed");
    const data = await response.json();
    heroSlides = Array.isArray(data) && data.length ? data : fallbackSlides();
  } catch { heroSlides = fallbackSlides(); }
  renderHero();
  restartHeroTimer();
}

function openSubscribe(sku, productName = "") {
  document.querySelector("#subscribe-sku").value = sku;
  document.querySelector("#subscribe-product").textContent = productName;
  document.querySelector("#subscribe-result").textContent = "";
  document.querySelector("#subscribe-contact").value = "";
  document.querySelector("#subscribe-consent").checked = false;
  subscribeDialog.showModal();
}

async function submitSubscription(event) {
  event.preventDefault();
  const sku = document.querySelector("#subscribe-sku").value;
  const contact = document.querySelector("#subscribe-contact").value.trim();
  const consent = document.querySelector("#subscribe-consent").checked;
  const result = document.querySelector("#subscribe-result");
  if (!sku || !contact || !consent) return;
  try {
    const response = await fetch(`${API}/api/leads/subscribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contact, target_sku: sku, channel: subscribeChannel, consent_marketing: true, consent_version: "launch-v1", locale: language, session_id: sessionId })
    });
    if (!response.ok) throw new Error("subscription failed");
    result.textContent = copy().subscribed;
    postEvent(API, "qualified_private_domain_capture", sessionId, { channel: subscribeChannel, language });
    setTimeout(() => subscribeDialog.close(), 900);
  } catch { result.textContent = copy().error; }
}

composer.addEventListener("submit", event => { event.preventDefault(); sendMessage(); });
input.addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(); } });
input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 160)}px`; });
document.querySelector("#clear-chat").addEventListener("click", () => { messages = []; sessionId = crypto.randomUUID(); localStorage.setItem("oppo-session-id", sessionId); addMessage("assistant", copy().greeting); postEvent(API, "assistant_open", sessionId, { language, reset: true }); });
document.querySelector("#hero-prev").addEventListener("click", () => moveHero(-1));
document.querySelector("#hero-next").addEventListener("click", () => moveHero(1));
document.querySelector("#hero-carousel").addEventListener("touchstart", event => { heroTouchStart = event.touches[0]?.clientX ?? null; }, { passive: true });
document.querySelector("#hero-carousel").addEventListener("touchend", event => { if (heroTouchStart == null) return; const end = event.changedTouches[0]?.clientX ?? heroTouchStart; if (Math.abs(end - heroTouchStart) > 45) moveHero(end < heroTouchStart ? 1 : -1); heroTouchStart = null; }, { passive: true });
heroStage.addEventListener("click", event => {
  const link = event.target.closest("[data-hero-cta]");
  if (link) postEvent(API, "hero_click", sessionId, { language, slide_id: link.dataset.slideId || "" });
});
conversation.addEventListener("click", event => {
  const button = event.target.closest("[data-notify]");
  if (button) openSubscribe(button.dataset.notify, button.dataset.product || "");
  const productLink = event.target.closest("[data-product-click]");
  if (productLink) postEvent(API, "product_click", sessionId, { language, sku: productLink.dataset.sku || "" });
});
document.querySelector("#subscribe-close").addEventListener("click", () => subscribeDialog.close());
subscribeForm.addEventListener("submit", submitSubscription);
document.querySelectorAll("[data-channel]").forEach(button => {
  button.addEventListener("click", () => {
    subscribeChannel = button.dataset.channel;
    document.querySelectorAll("[data-channel]").forEach(item => item.classList.toggle("active", item === button));
    const field = document.querySelector("#subscribe-contact");
    field.type = subscribeChannel === "email" ? "email" : "tel";
    field.autocomplete = subscribeChannel === "email" ? "email" : "tel";
  });
});

applyLanguage();
addMessage("assistant", copy().greeting);
loadHeroes();
postEvent(API, "assistant_open", sessionId, { language });
