import { escapeHtml } from "/shared.js";

const CONFIG = window.OPPO_CONFIG || { API_BASE_URL: "" };
const API = String(CONFIG.API_BASE_URL || "").replace(/\/$/, "");
const $ = selector => document.querySelector(selector);
let reviewDays = 7;
let conversations = [];
let candidates = [];
let selectedSession = null;

function adminKey() {
  return sessionStorage.getItem("oppo-admin-key") || "";
}

const nativeFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const response = await nativeFetch(...args);
  try {
    const input = args[0];
    const options = args[1] || {};
    const url = typeof input === "string" ? input : String(input?.url || "");
    const method = String(options.method || "GET").toUpperCase();
    const form = $("#faq-form");
    const candidateId = form?.dataset.candidateId;
    if (candidateId && response.ok && method === "POST" && url.includes("/api/admin/faqs")) {
      const saved = await response.clone().json();
      await nativeFetch(`${API}/api/admin/faq-candidates/${candidateId}/status`, {
        method: "POST",
        headers: { "X-Admin-Key": adminKey(), "Content-Type": "application/json" },
        body: JSON.stringify({ status: "converted", faq_id: saved?.id ?? null })
      });
      delete form.dataset.candidateId;
      const note = $("#faq-candidate-note");
      if (note) {
        note.style.display = "block";
        note.textContent = "FAQ 已发布，候选问题已自动标记为“已转 FAQ”。后续类似问题将优先走 FAQ 快速回答。";
      }
    }
  } catch {
    // FAQ itself has already saved successfully; review-state sync is best effort.
  }
  return response;
};

async function reviewFetch(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      "X-Admin-Key": adminKey(),
      ...(options.body ? { "Content-Type": "application/json" } : {}),
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
  return response.status === 204 ? null : response.json();
}

function safeDate(value) {
  try { return new Date(value).toLocaleString("de-AT"); } catch { return String(value || ""); }
}

function normalizeMessages(value) {
  if (Array.isArray(value)) return value;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
  }
  return [];
}

function renderConversationList() {
  const root = $("#conversation-list");
  if (!root) return;
  if (!conversations.length) {
    root.innerHTML = '<div class="empty-state">当前筛选范围没有对话记录</div>';
    return;
  }
  root.innerHTML = conversations.map(item => (
    `<button class="conversation-row ${selectedSession === item.session_id ? "active" : ""}" data-session="${escapeHtml(item.session_id)}">`
    + `<div><strong>${escapeHtml(item.first_question || "未识别首个问题")}</strong>`
    + `<small>${escapeHtml(item.language || "-")} · ${Number(item.message_count || 0)} 条消息</small></div>`
    + `<time>${escapeHtml(safeDate(item.updated_at))}</time></button>`
  )).join("");
}

function renderConversationDetail(data) {
  const root = $("#conversation-detail");
  if (!data) {
    root.innerHTML = '<div class="empty-state">选择左侧对话查看完整沟通记录</div>';
    return;
  }
  const messages = normalizeMessages(data.messages);
  root.innerHTML = (
    `<div class="conversation-meta"><span>语言 ${escapeHtml(data.language || "-")}</span><span>${escapeHtml(safeDate(data.updated_at))}</span></div>`
    + (messages.length ? messages.map(message => {
      const role = message?.role === "user" ? "user" : "assistant";
      const label = role === "user" ? "消费者" : "智能导购";
      const meta = role === "assistant" && message?.route
        ? `<em>${escapeHtml(String(message.route))}${message.fast_path ? " · fast" : ""}</em>`
        : "";
      return `<article class="review-message ${role}"><small>${label}${meta}</small><div>${escapeHtml(String(message?.content || ""))}</div></article>`;
    }).join("") : '<div class="empty-state">该会话没有可显示消息</div>')
  );
}

async function loadConversations() {
  const search = encodeURIComponent($("#conversation-search")?.value.trim() || "");
  conversations = await reviewFetch(`/api/admin/conversations?days=${reviewDays}&limit=150&search=${search}`);
  renderConversationList();
  if (selectedSession && !conversations.some(item => item.session_id === selectedSession)) {
    selectedSession = null;
    renderConversationDetail(null);
  }
}

async function openConversation(sessionId) {
  selectedSession = sessionId;
  renderConversationList();
  const data = await reviewFetch(`/api/admin/conversations/${encodeURIComponent(sessionId)}`);
  renderConversationDetail(data);
}

function renderCandidates() {
  const root = $("#faq-candidate-list");
  if (!root) return;
  $("#faq-candidate-count").textContent = `${candidates.length} 条`;
  if (!candidates.length) {
    root.innerHTML = '<div class="empty-state">当前没有待处理 FAQ 候选</div>';
    return;
  }
  root.innerHTML = candidates.map(item => {
    const status = item.status || "new";
    const actions = status === "new"
      ? `<button class="secondary" data-candidate-to-faq="${item.id}">转为 FAQ</button><button class="danger" data-candidate-dismiss="${item.id}">忽略</button>`
      : status === "reviewing"
        ? `<button class="secondary" data-candidate-to-faq="${item.id}">继续编辑</button><button class="secondary" data-candidate-converted="${item.id}">标记已发布</button><button class="danger" data-candidate-dismiss="${item.id}">忽略</button>`
        : "";
    const answerPreview = item.sample_answer
      ? `<p class="candidate-answer">参考回答：${escapeHtml(String(item.sample_answer).slice(0, 220))}${String(item.sample_answer).length > 220 ? "…" : ""}</p>`
      : "";
    return `<article class="candidate-row"><div class="candidate-count"><strong>${Number(item.occurrence_count || 0)}</strong><span>次</span></div><div class="content-main"><strong>${escapeHtml(item.sample_question || "")}</strong><p>语言 ${escapeHtml(item.language || "-")} · 最近 ${escapeHtml(safeDate(item.last_seen_at))}</p>${answerPreview}<small>${escapeHtml(status)}</small></div><div class="row-actions">${actions}</div></article>`;
  }).join("");
}

async function loadCandidates() {
  const status = encodeURIComponent($("#candidate-status")?.value || "new");
  const search = encodeURIComponent($("#candidate-search")?.value.trim() || "");
  candidates = await reviewFetch(`/api/admin/faq-candidates?status=${status}&limit=150&search=${search}`);
  renderCandidates();
}

async function setCandidateStatus(id, status, faqId = null) {
  await reviewFetch(`/api/admin/faq-candidates/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status, faq_id: faqId })
  });
  await loadCandidates();
}

async function candidateToFaq(id) {
  const item = candidates.find(candidate => Number(candidate.id) === Number(id));
  if (!item) return;
  await setCandidateStatus(id, "reviewing");

  const faqTab = document.querySelector('[data-tab="faq"]');
  if (faqTab) faqTab.click();
  const newButton = $("#faq-new");
  if (newButton) newButton.click();

  const question = item.sample_question || "";
  const answer = item.sample_answer || "";
  const language = String(item.language || "de").toLowerCase();
  if (language.startsWith("zh")) {
    $("#faq-question-zh").value = question;
    $("#faq-answer-zh").value = answer;
  } else if (language.startsWith("en")) {
    $("#faq-question-en").value = question;
    $("#faq-answer-en").value = answer;
  } else {
    $("#faq-question-de").value = question;
    $("#faq-answer-de").value = answer;
  }
  $("#faq-priority").value = String(Math.min(100, Math.max(0, Number(item.occurrence_count || 1) * 10)));
  $("#faq-keywords").value = question.length <= 80 ? question : "";
  $("#faq-form").dataset.candidateId = String(id);
  $("#faq-form").scrollIntoView({ behavior: "smooth", block: "start" });
  const note = $("#faq-candidate-note");
  if (note) {
    note.style.display = "block";
    note.textContent = language.startsWith("de")
      ? "已从消费者问题和已有回答带入。请人工校验正式答案后发布；保存成功后系统会自动标记候选为已转 FAQ。"
      : "已带入消费者原始语言的问题和参考回答。请补齐德语正式问题与回答并人工校验后发布。";
  }
}

async function loadReview() {
  const notice = $("#review-load-status");
  try {
    if (notice) notice.textContent = "加载中…";
    await Promise.all([loadConversations(), loadCandidates()]);
    if (notice) notice.textContent = "";
  } catch (error) {
    if (notice) notice.textContent = error.message;
  }
}

function wireReview() {
  document.querySelectorAll('[data-tab]').forEach(button => {
    button.addEventListener("click", () => {
      if (button.dataset.tab === "conversations") loadReview();
    });
  });

  document.querySelectorAll('[data-review-days]').forEach(button => {
    button.addEventListener("click", () => {
      reviewDays = Number(button.dataset.reviewDays || 7);
      document.querySelectorAll('[data-review-days]').forEach(item => item.classList.toggle("active", item === button));
      loadConversations();
    });
  });

  $("#conversation-refresh")?.addEventListener("click", loadConversations);
  $("#conversation-search")?.addEventListener("keydown", event => {
    if (event.key === "Enter") loadConversations();
  });
  $("#conversation-list")?.addEventListener("click", event => {
    const row = event.target.closest("[data-session]");
    if (row) openConversation(row.dataset.session);
  });

  $("#candidate-refresh")?.addEventListener("click", loadCandidates);
  $("#candidate-status")?.addEventListener("change", loadCandidates);
  $("#candidate-search")?.addEventListener("keydown", event => {
    if (event.key === "Enter") loadCandidates();
  });
  $("#faq-candidate-list")?.addEventListener("click", async event => {
    const toFaq = event.target.closest("[data-candidate-to-faq]");
    const dismiss = event.target.closest("[data-candidate-dismiss]");
    const converted = event.target.closest("[data-candidate-converted]");
    try {
      if (toFaq) await candidateToFaq(Number(toFaq.dataset.candidateToFaq));
      if (dismiss) await setCandidateStatus(Number(dismiss.dataset.candidateDismiss), "dismissed");
      if (converted) await setCandidateStatus(Number(converted.dataset.candidateConverted), "converted");
    } catch (error) {
      alert(error.message);
    }
  });
}

wireReview();
