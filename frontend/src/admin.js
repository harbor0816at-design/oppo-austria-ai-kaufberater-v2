import { escapeHtml } from "/shared.js";

const CONFIG = window.OPPO_CONFIG || { API_BASE_URL: "" };
const API = String(CONFIG.API_BASE_URL || "").replace(/\/$/, "");
let adminKey = sessionStorage.getItem("oppo-admin-key") || "";
let heroes = [];
let faqs = [];
let dashboardDays = 7;

const $ = selector => document.querySelector(selector);
const $$ = selector => Array.from(document.querySelectorAll(selector));
const keyInput = $("#admin-key");
keyInput.value = adminKey;

function headers(json = false) {
  const value = { "X-Admin-Key": adminKey };
  if (json) value["Content-Type"] = "application/json";
  return value;
}

async function adminFetch(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      ...headers(Boolean(options.body) && !(options.body instanceof FormData)),
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
    } catch {}
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function number(value, digits = 0) {
  const n = Number(value || 0);
  return Number.isFinite(n) ? n.toLocaleString("de-AT", { maximumFractionDigits: digits }) : "0";
}

function pct(value) {
  return `${number(value, 1)}%`;
}

function ms(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "—";
  return n >= 1000 ? `${(n / 1000).toFixed(1)}s` : `${Math.round(n)}ms`;
}

function switchTab(name) {
  $$('[data-tab]').forEach(button => button.classList.toggle("active", button.dataset.tab === name));
  $$('[data-panel]').forEach(panel => panel.classList.toggle("active", panel.dataset.panel === name));
}

function renderBars(selector, items = []) {
  const root = $(selector);
  if (!items.length) {
    root.innerHTML = '<div class="empty-state">暂无数据</div>';
    return;
  }
  const max = Math.max(...items.map(item => Number(item.value || 0)), 1);
  root.innerHTML = items.map(item => {
    const value = Number(item.value || 0);
    const width = Math.max(value ? 4 : 0, Math.round((value / max) * 100));
    return `<div class="bar-row"><span>${escapeHtml(item.label || "unknown")}</span><div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div><strong>${number(value)}</strong></div>`;
  }).join("");
}

function renderDaily(items = []) {
  const root = $("#daily-chart");
  if (!items.length) {
    root.innerHTML = '<div class="empty-state">暂无趋势数据</div>';
    return;
  }
  const max = Math.max(...items.flatMap(item => [Number(item.questions || 0), Number(item.answers || 0), Number(item.conversions || 0)]), 1);
  root.innerHTML = items.map(item => {
    const q = Math.max(2, Math.round((Number(item.questions || 0) / max) * 125));
    const a = Math.max(2, Math.round((Number(item.answers || 0) / max) * 125));
    const c = Number(item.conversions || 0) ? Math.max(2, Math.round((Number(item.conversions || 0) / max) * 125)) : 0;
    return `<div class="day-col"><div class="day-bars"><i class="q" style="height:${q}px" title="提问 ${number(item.questions)}"></i><i class="a" style="height:${a}px" title="回答 ${number(item.answers)}"></i><i class="c" style="height:${c}px" title="留资 ${number(item.conversions)}"></i></div><small>${escapeHtml(String(item.day || "").slice(5))}</small></div>`;
  }).join("");
}

function renderKpis(k = {}) {
  const cards = [
    ["访问会话", number(k.visitors), "打开导购的独立会话"],
    ["提问会话", number(k.question_sessions), "至少提问一次"],
    ["总问题数", number(k.questions), `人均 ${number(k.questions_per_visitor, 2)} 问`],
    ["回答成功率", pct(k.answer_success_pct), `前端错误 ${number(k.answer_errors)}`],
    ["平均响应", ms(k.avg_latency_ms), `快速路径 ${pct(k.fast_path_pct)}`],
    ["推荐展示", number(k.recommendation_views), "产生产品推荐卡"],
    ["商品点击", number(k.product_clicks), `CTR ${pct(k.product_ctr_pct)}`],
    ["留资 / 订阅", number(k.conversions), `QPCR ${pct(k.qpcr_pct)}`],
    ["FAQ 命中", number(k.faq_uses), "运营知识快速回答"],
    ["快捷入口", number(k.quick_reply_clicks), "相机 / 续航 / 价格等"],
    ["Hero 曝光", number(k.hero_views), `点击 ${number(k.hero_clicks)}`],
    ["后台错误", number(k.backend_errors), "近周期 chat error"]
  ];
  $("#kpi-grid").innerHTML = cards.map(([label, value, note]) => `<article class="kpi-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`).join("");
}

function renderErrors(items = []) {
  const root = $("#recent-errors");
  if (!items.length) {
    root.innerHTML = '<div class="empty-state">当前周期没有记录到聊天异常</div>';
    return;
  }
  root.innerHTML = items.map(item => {
    const payload = item.payload || {};
    const kind = payload.error_type || payload.error_code || "error";
    return `<div class="compact-item"><code>${escapeHtml(item.event_type || "error")}</code><span>${escapeHtml(kind)}</span><time>${escapeHtml(new Date(item.created_at).toLocaleString("de-AT"))}</time></div>`;
  }).join("");
}

async function loadDashboard() {
  const data = await adminFetch(`/api/admin/analytics/dashboard?days=${dashboardDays}`);
  renderKpis(data.kpis || {});
  renderDaily(data.daily || []);
  renderBars("#language-bars", data.languages || []);
  renderBars("#route-bars", data.routes || []);
  renderBars("#quick-bars", data.quick_replies || []);
  renderBars("#event-bars", data.event_counts || []);
  renderErrors(data.recent_errors || []);
}

function resetHeroForm() {
  $("#hero-id").value = "";
  ["#hero-title", "#hero-title-en", "#hero-title-zh", "#hero-subtitle", "#hero-subtitle-en", "#hero-subtitle-zh", "#hero-eyebrow", "#hero-media", "#hero-mobile-media", "#hero-cta-label", "#hero-cta-url"].forEach(selector => $(selector).value = "");
  $("#hero-sort").value = "0";
  $("#hero-active").checked = true;
  updateHeroPreview();
}

function heroPayload() {
  return {
    title: $("#hero-title").value.trim(),
    title_en: $("#hero-title-en").value.trim() || null,
    title_zh: $("#hero-title-zh").value.trim() || null,
    subtitle: $("#hero-subtitle").value.trim(),
    subtitle_en: $("#hero-subtitle-en").value.trim() || null,
    subtitle_zh: $("#hero-subtitle-zh").value.trim() || null,
    eyebrow: $("#hero-eyebrow").value.trim() || null,
    media_type: $("#hero-media").value.trim().match(/\.mp4(?:\?|$)/i) ? "video" : "image",
    media_url: $("#hero-media").value.trim(),
    mobile_media_url: $("#hero-mobile-media").value.trim() || null,
    cta_label: $("#hero-cta-label").value.trim() || null,
    cta_url: $("#hero-cta-url").value.trim() || null,
    sort_order: Number($("#hero-sort").value || 0),
    is_active: $("#hero-active").checked
  };
}

function updateHeroPreview() {
  const mediaUrl = $("#hero-media").value.trim();
  const title = $("#hero-title-zh").value.trim() || $("#hero-title").value.trim();
  const subtitle = $("#hero-subtitle-zh").value.trim() || $("#hero-subtitle").value.trim();
  const eyebrow = $("#hero-eyebrow").value.trim() || "OPPO";
  if (!mediaUrl) {
    $("#hero-preview").innerHTML = '<div class="empty-state">填写素材和标题后预览</div>';
    return;
  }
  const media = mediaUrl.match(/\.mp4(?:\?|$)/i)
    ? `<video autoplay muted loop playsinline src="${escapeHtml(mediaUrl)}"></video>`
    : `<img src="${escapeHtml(mediaUrl)}" alt="preview">`;
  $("#hero-preview").innerHTML = `${media}<div class="overlay"></div><div class="copy"><small>${escapeHtml(eyebrow)}</small><h3>${escapeHtml(title || "OPPO")}</h3><p>${escapeHtml(subtitle)}</p></div>`;
}

function editHero(id) {
  const slide = heroes.find(item => item.id === id);
  if (!slide) return;
  $("#hero-id").value = String(slide.id);
  $("#hero-title").value = slide.title || "";
  $("#hero-title-en").value = slide.title_en || "";
  $("#hero-title-zh").value = slide.title_zh || "";
  $("#hero-subtitle").value = slide.subtitle || "";
  $("#hero-subtitle-en").value = slide.subtitle_en || "";
  $("#hero-subtitle-zh").value = slide.subtitle_zh || "";
  $("#hero-eyebrow").value = slide.eyebrow || "";
  $("#hero-media").value = slide.media_url || "";
  $("#hero-mobile-media").value = slide.mobile_media_url || "";
  $("#hero-cta-label").value = slide.cta_label || "";
  $("#hero-cta-url").value = slide.cta_url || "";
  $("#hero-sort").value = String(slide.sort_order ?? 0);
  $("#hero-active").checked = Boolean(slide.is_active);
  updateHeroPreview();
  $("#hero-form").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderHeroes() {
  if (!heroes.length) {
    $("#hero-list").innerHTML = '<div class="empty-state">暂无后台轮播，消费者页面会使用 fallback 素材。</div>';
    return;
  }
  const sorted = [...heroes].sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0));
  $("#hero-list").innerHTML = sorted.map((slide, index) => {
    const preview = slide.media_type === "video" ? '<div class="content-thumb empty-state">VIDEO</div>' : `<img class="content-thumb" src="${escapeHtml(slide.media_url)}" alt="">`;
    return `<article class="content-row ${slide.is_active ? "" : "inactive"}">${preview}<div class="content-main"><strong>${escapeHtml(slide.title)}</strong><p>${escapeHtml(slide.subtitle || "")}</p><small>#${slide.id} · order ${slide.sort_order} · ${slide.is_active ? "启用" : "停用"}</small></div><div class="row-actions"><button class="secondary" data-move-hero="${slide.id}" data-dir="-1" ${index === 0 ? "disabled" : ""}>↑</button><button class="secondary" data-move-hero="${slide.id}" data-dir="1" ${index === sorted.length - 1 ? "disabled" : ""}>↓</button><button class="secondary" data-edit-hero="${slide.id}">编辑</button><button class="danger" data-delete-hero="${slide.id}">删除</button></div></article>`;
  }).join("");
}

async function loadHeroes() {
  heroes = await adminFetch("/api/admin/hero-slides");
  renderHeroes();
}

async function moveHero(id, dir) {
  const sorted = [...heroes].sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0));
  const index = sorted.findIndex(item => item.id === id);
  const other = index + Number(dir);
  if (index < 0 || other < 0 || other >= sorted.length) return;
  [sorted[index], sorted[other]] = [sorted[other], sorted[index]];
  const payload = sorted.map((item, position) => ({ id: item.id, sort_order: (position + 1) * 10 }));
  heroes = await adminFetch("/api/admin/hero-slides/reorder", { method: "POST", body: JSON.stringify(payload) });
  renderHeroes();
}

function resetFaqForm() {
  $("#faq-id").value = "";
  $("#faq-category").value = "general";
  $("#faq-priority").value = "0";
  $("#faq-active").checked = true;
  ["#faq-question-de", "#faq-question-en", "#faq-question-zh", "#faq-answer-de", "#faq-answer-en", "#faq-answer-zh", "#faq-keywords"].forEach(selector => $(selector).value = "");
}

function faqPayload() {
  return {
    category: $("#faq-category").value,
    question_de: $("#faq-question-de").value.trim(),
    answer_de: $("#faq-answer-de").value.trim(),
    question_en: $("#faq-question-en").value.trim() || null,
    answer_en: $("#faq-answer-en").value.trim() || null,
    question_zh: $("#faq-question-zh").value.trim() || null,
    answer_zh: $("#faq-answer-zh").value.trim() || null,
    keywords: $("#faq-keywords").value.split(/[,，;]/).map(value => value.trim()).filter(Boolean),
    priority: Number($("#faq-priority").value || 0),
    is_active: $("#faq-active").checked
  };
}

function editFaq(id) {
  const item = faqs.find(faq => faq.id === id);
  if (!item) return;
  $("#faq-id").value = String(item.id);
  $("#faq-category").value = item.category || "general";
  $("#faq-priority").value = String(item.priority || 0);
  $("#faq-active").checked = Boolean(item.is_active);
  $("#faq-question-de").value = item.question_de || "";
  $("#faq-question-en").value = item.question_en || "";
  $("#faq-question-zh").value = item.question_zh || "";
  $("#faq-answer-de").value = item.answer_de || "";
  $("#faq-answer-en").value = item.answer_en || "";
  $("#faq-answer-zh").value = item.answer_zh || "";
  $("#faq-keywords").value = (item.keywords || []).join(", ");
  $("#faq-form").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderFaqs() {
  const query = $("#faq-search").value.trim().toLowerCase();
  const category = $("#faq-filter-category").value;
  const filtered = faqs.filter(item => {
    if (category && item.category !== category) return false;
    if (!query) return true;
    const haystack = [item.question_de, item.question_en, item.question_zh, item.answer_de, item.answer_en, item.answer_zh, ...(item.keywords || [])].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  $("#faq-count").textContent = `${filtered.length} / ${faqs.length}`;
  if (!filtered.length) {
    $("#faq-list").innerHTML = '<div class="empty-state">没有匹配的 FAQ</div>';
    return;
  }
  $("#faq-list").innerHTML = filtered.map(item => `<article class="content-row ${item.is_active ? "" : "inactive"}"><div class="faq-badge">${escapeHtml(item.category)}</div><div class="content-main"><strong>${escapeHtml(item.question_de)}</strong><p>${escapeHtml(item.answer_de.slice(0, 220))}${item.answer_de.length > 220 ? "…" : ""}</p><div class="mini-tags">${(item.keywords || []).slice(0, 8).map(tag => `<span>${escapeHtml(tag)}</span>`).join("")}</div><small>优先级 ${number(item.priority)} · ${item.is_active ? "启用" : "停用"}</small></div><div class="row-actions"><button class="secondary" data-edit-faq="${item.id}">编辑</button><button class="danger" data-delete-faq="${item.id}">删除</button></div></article>`).join("");
}

function rebuildFaqCategoryFilter() {
  const select = $("#faq-filter-category");
  const categories = [...new Set(faqs.map(item => item.category).filter(Boolean))].sort();
  select.innerHTML = '<option value="">全部分类</option>' + categories.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
}

async function loadFaqs() {
  faqs = await adminFetch("/api/admin/faqs");
  rebuildFaqCategoryFilter();
  renderFaqs();
}

async function connect() {
  adminKey = keyInput.value.trim();
  sessionStorage.setItem("oppo-admin-key", adminKey);
  $("#login-result").textContent = "正在连接…";
  try {
    const status = await adminFetch("/api/admin/status");
    $("#system-badge").className = "status-badge ok";
    $("#system-badge").textContent = status.admin_data_reachable ? "系统正常" : "部分服务不可用";
    $("#login-result").textContent = "连接成功";
    $("#login-panel").classList.add("hidden");
    $("#admin-content").classList.remove("hidden");
    await Promise.all([loadDashboard(), loadHeroes(), loadFaqs()]);
  } catch (error) {
    $("#login-result").textContent = error.message;
    $("#system-badge").className = "status-badge warn";
    $("#system-badge").textContent = "连接失败";
  }
}

$$('[data-tab]').forEach(button => button.addEventListener("click", () => switchTab(button.dataset.tab)));
$$('[data-days]').forEach(button => button.addEventListener("click", async () => {
  dashboardDays = Number(button.dataset.days || 7);
  $$('[data-days]').forEach(item => item.classList.toggle("active", item === button));
  await loadDashboard();
}));
$("#dashboard-refresh").addEventListener("click", loadDashboard);
$("#admin-connect").addEventListener("click", connect);
keyInput.addEventListener("keydown", event => { if (event.key === "Enter") connect(); });

$("#hero-form").addEventListener("input", updateHeroPreview);
$("#hero-new").addEventListener("click", resetHeroForm);
$("#hero-reset").addEventListener("click", resetHeroForm);
$("#hero-form").addEventListener("submit", async event => {
  event.preventDefault();
  const id = $("#hero-id").value;
  try {
    await adminFetch(id ? `/api/admin/hero-slides/${id}` : "/api/admin/hero-slides", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(heroPayload())
    });
    resetHeroForm();
    await loadHeroes();
  } catch (error) { alert(error.message); }
});
$("#hero-upload").addEventListener("click", async () => {
  const file = $("#hero-file").files[0];
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  $("#upload-result").textContent = "上传中…";
  try {
    const data = await adminFetch("/api/admin/hero-assets/upload", { method: "POST", body });
    $("#hero-media").value = data.url;
    $("#upload-result").textContent = "上传完成";
    updateHeroPreview();
  } catch (error) { $("#upload-result").textContent = error.message; }
});
$("#hero-list").addEventListener("click", async event => {
  const edit = event.target.closest("[data-edit-hero]");
  const remove = event.target.closest("[data-delete-hero]");
  const move = event.target.closest("[data-move-hero]");
  if (edit) editHero(Number(edit.dataset.editHero));
  if (move) await moveHero(Number(move.dataset.moveHero), Number(move.dataset.dir));
  if (remove && confirm("确认删除这条轮播？")) {
    try {
      await adminFetch(`/api/admin/hero-slides/${remove.dataset.deleteHero}`, { method: "DELETE" });
      await loadHeroes();
    } catch (error) { alert(error.message); }
  }
});

$("#faq-new").addEventListener("click", resetFaqForm);
$("#faq-reset").addEventListener("click", resetFaqForm);
$("#faq-form").addEventListener("submit", async event => {
  event.preventDefault();
  const id = $("#faq-id").value;
  try {
    await adminFetch(id ? `/api/admin/faqs/${id}` : "/api/admin/faqs", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(faqPayload())
    });
    resetFaqForm();
    await loadFaqs();
  } catch (error) { alert(error.message); }
});
$("#faq-list").addEventListener("click", async event => {
  const edit = event.target.closest("[data-edit-faq]");
  const remove = event.target.closest("[data-delete-faq]");
  if (edit) editFaq(Number(edit.dataset.editFaq));
  if (remove && confirm("确认删除这条 FAQ？")) {
    try {
      await adminFetch(`/api/admin/faqs/${remove.dataset.deleteFaq}`, { method: "DELETE" });
      await loadFaqs();
    } catch (error) { alert(error.message); }
  }
});
$("#faq-search").addEventListener("input", renderFaqs);
$("#faq-filter-category").addEventListener("change", renderFaqs);

resetHeroForm();
resetFaqForm();
if (adminKey) connect();
