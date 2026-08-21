import { escapeHtml } from "/shared.js";

const CONFIG = window.OPPO_CONFIG || { API_BASE_URL: "" };
const API = String(CONFIG.API_BASE_URL || "").replace(/\/$/, "");
let adminKey = sessionStorage.getItem("oppo-admin-key") || "";
let heroes = [];

const keyInput = document.querySelector("#admin-key");
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
    } catch {
      // Keep the status fallback.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function resetHeroForm() {
  document.querySelector("#hero-id").value = "";
  document.querySelector("#hero-title").value = "";
  document.querySelector("#hero-title-en").value = "";
  document.querySelector("#hero-title-zh").value = "";
  document.querySelector("#hero-subtitle").value = "";
  document.querySelector("#hero-subtitle-en").value = "";
  document.querySelector("#hero-subtitle-zh").value = "";
  document.querySelector("#hero-eyebrow").value = "";
  document.querySelector("#hero-media").value = "";
  document.querySelector("#hero-mobile-media").value = "";
  document.querySelector("#hero-cta-label").value = "";
  document.querySelector("#hero-cta-url").value = "";
  document.querySelector("#hero-sort").value = "0";
  document.querySelector("#hero-active").checked = true;
}

function heroPayload() {
  return {
    title: document.querySelector("#hero-title").value.trim(),
    title_en: document.querySelector("#hero-title-en").value.trim() || null,
    title_zh: document.querySelector("#hero-title-zh").value.trim() || null,
    subtitle: document.querySelector("#hero-subtitle").value.trim(),
    subtitle_en: document.querySelector("#hero-subtitle-en").value.trim() || null,
    subtitle_zh: document.querySelector("#hero-subtitle-zh").value.trim() || null,
    eyebrow: document.querySelector("#hero-eyebrow").value.trim() || null,
    media_type: document.querySelector("#hero-media").value.trim().match(/\.mp4(?:\?|$)/i) ? "video" : "image",
    media_url: document.querySelector("#hero-media").value.trim(),
    mobile_media_url: document.querySelector("#hero-mobile-media").value.trim() || null,
    cta_label: document.querySelector("#hero-cta-label").value.trim() || null,
    cta_url: document.querySelector("#hero-cta-url").value.trim() || null,
    sort_order: Number(document.querySelector("#hero-sort").value || 0),
    is_active: document.querySelector("#hero-active").checked
  };
}

function renderHeroes() {
  document.querySelector("#hero-list").innerHTML = heroes.map(slide => (
    `<article class="admin-item"><div><strong>${escapeHtml(slide.title)}</strong>`
    + `<small>#${slide.id} · order ${slide.sort_order} · ${slide.is_active ? "active" : "inactive"}</small>`
    + `<a href="${escapeHtml(slide.media_url)}" target="_blank" rel="noreferrer">${escapeHtml(slide.media_url)}</a></div>`
    + `<div class="admin-actions"><button data-edit-hero="${slide.id}" class="secondary">Edit</button>`
    + `<button data-delete-hero="${slide.id}" class="danger">Delete</button></div></article>`
  )).join("") || "<p>No stored slides. The consumer page is using fallback slides.</p>";
}

async function loadHeroes() {
  heroes = await adminFetch("/api/admin/hero-slides");
  renderHeroes();
}

function editHero(id) {
  const slide = heroes.find(item => item.id === id);
  if (!slide) return;
  document.querySelector("#hero-id").value = String(slide.id);
  document.querySelector("#hero-title").value = slide.title || "";
  document.querySelector("#hero-title-en").value = slide.title_en || "";
  document.querySelector("#hero-title-zh").value = slide.title_zh || "";
  document.querySelector("#hero-subtitle").value = slide.subtitle || "";
  document.querySelector("#hero-subtitle-en").value = slide.subtitle_en || "";
  document.querySelector("#hero-subtitle-zh").value = slide.subtitle_zh || "";
  document.querySelector("#hero-eyebrow").value = slide.eyebrow || "";
  document.querySelector("#hero-media").value = slide.media_url || "";
  document.querySelector("#hero-mobile-media").value = slide.mobile_media_url || "";
  document.querySelector("#hero-cta-label").value = slide.cta_label || "";
  document.querySelector("#hero-cta-url").value = slide.cta_url || "";
  document.querySelector("#hero-sort").value = String(slide.sort_order ?? 0);
  document.querySelector("#hero-active").checked = Boolean(slide.is_active);
  document.querySelector("#hero-form").scrollIntoView({ behavior: "smooth" });
}

async function loadFacts() {
  const facts = await adminFetch("/api/admin/facts");
  document.querySelector("#facts-list").innerHTML = facts.map(fact => (
    `<article class="admin-item"><div><strong>${escapeHtml(fact.product_name)}</strong>`
    + `<small>${escapeHtml(fact.sku_id)} · ${escapeHtml(fact.official_status)}</small></div>`
    + `<button class="danger" data-delete-fact="${escapeHtml(fact.sku_id)}">Delete</button></article>`
  )).join("") || "<p>No Source_B products saved yet.</p>";
}

async function loadLeads() {
  const leads = await adminFetch("/api/admin/leads");
  document.querySelector("#leads-list").innerHTML = leads.map(lead => (
    `<article class="admin-item"><div><strong>${escapeHtml(lead.contact)}</strong>`
    + `<small>${escapeHtml(lead.channel)} · ${escapeHtml(lead.target_sku)} · ${escapeHtml(lead.created_at)}</small></div></article>`
  )).join("") || "<p>No leads.</p>";
}

async function connect() {
  adminKey = keyInput.value.trim();
  sessionStorage.setItem("oppo-admin-key", adminKey);
  const result = document.querySelector("#health-result");
  try {
    await Promise.all([loadHeroes(), loadFacts()]);
    result.textContent = "Connected.";
  } catch (error) {
    result.textContent = error.message;
  }
}

document.querySelector("#admin-connect").addEventListener("click", connect);
document.querySelector("#ai-health").addEventListener("click", async () => {
  try {
    document.querySelector("#health-result").textContent = pretty(await adminFetch("/api/admin/ai-health"));
  } catch (error) {
    document.querySelector("#health-result").textContent = error.message;
  }
});
document.querySelector("#analytics-load").addEventListener("click", async () => {
  try {
    document.querySelector("#health-result").textContent = pretty(await adminFetch("/api/admin/analytics/summary"));
  } catch (error) {
    document.querySelector("#health-result").textContent = error.message;
  }
});
document.querySelector("#hero-reset").addEventListener("click", resetHeroForm);
document.querySelector("#hero-form").addEventListener("submit", async event => {
  event.preventDefault();
  const id = document.querySelector("#hero-id").value;
  try {
    await adminFetch(id ? `/api/admin/hero-slides/${id}` : "/api/admin/hero-slides", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(heroPayload())
    });
    resetHeroForm();
    await loadHeroes();
  } catch (error) {
    alert(error.message);
  }
});
document.querySelector("#hero-list").addEventListener("click", async event => {
  const edit = event.target.closest("[data-edit-hero]");
  const remove = event.target.closest("[data-delete-hero]");
  if (edit) editHero(Number(edit.dataset.editHero));
  if (remove && confirm("Delete this slide?")) {
    try {
      await adminFetch(`/api/admin/hero-slides/${remove.dataset.deleteHero}`, { method: "DELETE" });
      await loadHeroes();
    } catch (error) {
      alert(error.message);
    }
  }
});
document.querySelector("#hero-upload").addEventListener("click", async () => {
  const file = document.querySelector("#hero-file").files[0];
  const output = document.querySelector("#upload-result");
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  try {
    const data = await adminFetch("/api/admin/hero-assets/upload", { method: "POST", body });
    document.querySelector("#hero-media").value = data.url;
    output.textContent = "Uploaded.";
  } catch (error) {
    output.textContent = error.message;
  }
});
document.querySelector("#facts-upload").addEventListener("click", async () => {
  const output = document.querySelector("#facts-result");
  try {
    const parsed = JSON.parse(document.querySelector("#facts-json").value);
    const items = Array.isArray(parsed) ? parsed : [parsed];
    const results = [];
    for (const item of items) {
      results.push(await adminFetch("/api/admin/facts", {
        method: "POST",
        body: JSON.stringify(item)
      }));
    }
    output.textContent = pretty(results);
    await loadFacts();
  } catch (error) {
    output.textContent = error.message;
  }
});
document.querySelector("#facts-load").addEventListener("click", loadFacts);
document.querySelector("#facts-list").addEventListener("click", async event => {
  const button = event.target.closest("[data-delete-fact]");
  if (!button || !confirm("Delete this Source_B product?")) return;
  try {
    await adminFetch(`/api/admin/facts/${encodeURIComponent(button.dataset.deleteFact)}`, { method: "DELETE" });
    await loadFacts();
  } catch (error) {
    alert(error.message);
  }
});
document.querySelector("#load-leads").addEventListener("click", loadLeads);

if (adminKey) connect();
