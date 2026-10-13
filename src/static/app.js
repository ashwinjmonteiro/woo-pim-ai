"use strict";

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const prettyTime = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
};

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, { ...options, headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) } });
  } catch {
    throw new Error("Could not connect to the API. Check that the server is running and try again.");
  }
  let payload = {};
  if (response.status !== 204) {
    try { payload = await response.json(); } catch { payload = {}; }
  }
  if (!response.ok) throw new Error(payload?.error?.message || `The request could not be completed (HTTP ${response.status}).`);
  return payload;
}

function toast(message, kind = "error") {
  const item = document.createElement("div");
  item.className = `toast ${kind === "success" ? "success" : ""}`;
  const icon = document.createElement("span");
  icon.className = "toast-icon";
  icon.textContent = kind === "success" ? "✓" : "!";
  const copy = document.createElement("span");
  copy.textContent = message || "Something went wrong. Please try again.";
  item.append(icon, copy);
  byId("toast-region").append(item);
  window.setTimeout(() => item.remove(), 4600);
}

function badge(status) {
  const normalized = String(status || "pending").toLowerCase();
  let color = "neutral";
  if (["success", "complete", "published", "enriched"].includes(normalized)) color = "success";
  else if (["partial", "pending"].includes(normalized)) color = "warning";
  else if (normalized === "failed") color = "danger";
  const label = normalized.replaceAll("_", " ");
  return `<span class="badge badge-${color}">${escapeHtml(label)}</span>`;
}

function setActiveTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => {
    const active = tab.dataset.tab === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    const active = panel.id === `panel-${name}`;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
  if (name === "products") loadProducts();
  if (name === "sync") loadSync();
}

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => setActiveTab(tab.dataset.tab)));

function latestSyncByProduct(records) {
  const latest = new Map();
  for (const record of records) {
    if (record.product_id && !latest.has(record.product_id)) latest.set(record.product_id, record);
  }
  return latest;
}

async function loadProducts() {
  const body = byId("products-body");
  body.innerHTML = '<tr><td colspan="7" class="empty-cell">Loading your catalog…</td></tr>';
  try {
    const [products, records] = await Promise.all([api("/products?limit=100"), api("/sync/status")]);
    const latest = latestSyncByProduct(records);
    byId("product-count").textContent = String(products.length);
    byId("product-summary").textContent = products.length ? `${products.length} product${products.length === 1 ? "" : "s"}` : "Your catalog is ready for its first product";
    if (!products.length) {
      body.innerHTML = '<tr><td colspan="7" class="empty-cell">No products yet. Add one above or create a draft in AI Enrich.</td></tr>';
      return;
    }
    body.innerHTML = products.map((product) => {
      const sync = latest.get(product.id);
      return `<tr>
        <td class="product-cell"><div class="product-name" title="${escapeHtml(product.title)}">${escapeHtml(product.title)}</div><div class="product-sub">Updated ${escapeHtml(prettyTime(product.updated_at))}</div></td>
        <td>${escapeHtml(product.sku)}</td><td>${escapeHtml(product.category || "—")}</td>
        <td>${badge(product.status)}</td><td>${escapeHtml(product.woo_id || "—")}</td>
        <td>${sync ? badge(sync.status) : badge("pending")}</td>
        <td><div class="row-actions"><button class="mini-button push-product" data-id="${Number(product.id)}">Push</button><button class="mini-button danger delete-product" data-id="${Number(product.id)}">Delete</button></div></td>
      </tr>`;
    }).join("");
  } catch (error) {
    body.innerHTML = '<tr><td colspan="7" class="empty-cell">Products could not be loaded.</td></tr>';
    toast(error.message);
  }
}

byId("refresh-products").addEventListener("click", loadProducts);
byId("products-body").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-id]");
  if (!button) return;
  const productId = Number(button.dataset.id);
  button.disabled = true;
  try {
    if (button.classList.contains("push-product")) {
      const record = await api(`/sync/push/${productId}`, { method: "POST" });
      toast(record.status === "success" ? "Product pushed to WooCommerce." : record.error || "Product could not be pushed.", record.status === "success" ? "success" : "error");
    } else if (button.classList.contains("delete-product")) {
      if (!window.confirm("Delete this product from the PIM catalog?")) return;
      await api(`/products/${productId}`, { method: "DELETE" });
      toast("Product deleted.", "success");
    }
    await loadProducts();
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
  }
});

byId("add-product-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector("button[type=submit]");
  const values = new FormData(form);
  const product = { title: values.get("title").trim(), sku: values.get("sku").trim(), description: "", tags: [], attributes: {}, status: "draft" };
  if (values.get("price")) product.price = Number(values.get("price"));
  submit.disabled = true;
  try {
    await api("/products", { method: "POST", body: JSON.stringify(product) });
    form.reset();
    toast("Product added to your catalog.", "success");
    await loadProducts();
  } catch (error) {
    toast(error.message);
  } finally {
    submit.disabled = false;
  }
});

function shortResult(result) {
  let text = typeof result === "string" ? result : Array.isArray(result) ? result.join(", ") : JSON.stringify(result);
  if (!text) return "Tool completed.";
  return text.length > 180 ? `${text.slice(0, 177)}…` : text;
}

function renderEnrichment(data) {
  const product = data.product || {};
  byId("enrich-result").hidden = false;
  byId("enrich-empty").hidden = true;
  byId("result-title").textContent = product.title || "Enriched product";
  byId("result-description").textContent = product.description || "No description was generated.";
  byId("result-category").textContent = product.category || "No category suggested";
  byId("result-status").outerHTML = `<span id="result-status" class="badge badge-${data.status === "complete" ? "success" : data.status === "partial" ? "warning" : "danger"}">${escapeHtml(data.status || "failed")}</span>`;
  const tags = product.tags || [];
  byId("result-tags").innerHTML = tags.length ? tags.map((tag) => `<span class="chip">${escapeHtml(tag)}</span>`).join("") : '<span class="muted">No tags suggested.</span>';
  const attributes = Object.entries(product.attributes || {});
  byId("result-attributes").innerHTML = attributes.length ? attributes.map(([key, value]) => `<tr><td>${escapeHtml(key)}</td><td>${escapeHtml(Array.isArray(value) ? value.join(", ") : value)}</td></tr>`).join("") : '<tr><td colspan="2" class="empty-cell">No attributes extracted</td></tr>';
  const persisted = byId("persisted-note");
  persisted.hidden = !data.persisted;
  persisted.textContent = data.persisted ? `Saved to catalog as ${data.persisted.sku}.` : "";
  const trace = data.trace || [];
  byId("trace-summary").textContent = `${trace.length} tool call${trace.length === 1 ? "" : "s"}`;
  const traceItems = trace.map((step, index) => `<li class="trace-item"><span class="trace-number">${index + 1}</span><div><div class="trace-name">${escapeHtml(step.tool)}</div><div class="trace-detail">${escapeHtml(shortResult(step.result))}</div></div><span class="trace-ok">✓ Complete</span></li>`);
  if (data.error) traceItems.push(`<li class="trace-item"><span class="trace-number">${traceItems.length + 1}</span><div><div class="trace-name">Validation / retry</div><div class="trace-detail">${escapeHtml(data.error)}</div></div><span class="trace-fail">! Needs attention</span></li>`);
  byId("trace-list").innerHTML = traceItems.length ? traceItems.join("") : '<li class="empty-cell">The agent did not call any tools.</li>';
}

byId("enrich-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = byId("enrich-button");
  const title = byId("enrich-title").value.trim();
  if (!title) return;
  button.disabled = true;
  button.classList.add("loading");
  button.setAttribute("aria-busy", "true");
  try {
    const persist = byId("persist-enrichment").checked;
    const data = await api(`/ai/enrich?persist=${persist}`, { method: "POST", body: JSON.stringify({ title }) });
    renderEnrichment(data);
    toast(data.status === "complete" ? "Product enrichment is complete." : "Enrichment finished with some fields missing.", data.status === "complete" ? "success" : "error");
    if (data.persisted) await loadProducts();
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.classList.remove("loading");
    button.removeAttribute("aria-busy");
  }
});

async function loadSync() {
  const body = byId("sync-body");
  body.innerHTML = '<tr><td colspan="6" class="empty-cell">Loading sync history…</td></tr>';
  try {
    const [records, products] = await Promise.all([api("/sync/status"), api("/products?limit=100")]);
    const names = new Map(products.map((product) => [product.id, product.title]));
    if (!records.length) {
      body.innerHTML = '<tr><td colspan="6" class="empty-cell">No sync activity yet. Push or pull products to see results here.</td></tr>';
      return;
    }
    body.innerHTML = records.slice(0, 50).map((record) => `<tr>
      <td class="product-cell"><div class="product-name">${escapeHtml(names.get(record.product_id) || (record.product_id ? `Product #${record.product_id}` : "WooCommerce import"))}</div></td>
      <td>${escapeHtml(record.direction)}</td><td>${badge(record.status)}</td><td>${escapeHtml(record.attempts)}</td>
      <td class="sync-error" title="${escapeHtml(record.error || "")}">${escapeHtml(record.error || "—")}</td><td>${escapeHtml(prettyTime(record.completed_at || record.created_at))}</td>
    </tr>`).join("");
  } catch (error) {
    body.innerHTML = '<tr><td colspan="6" class="empty-cell">Sync history could not be loaded.</td></tr>';
    toast(error.message);
  }
}

byId("refresh-sync").addEventListener("click", loadSync);
byId("push-all").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const records = await api("/sync/push-all", { method: "POST" });
    const successes = records.filter((record) => record.status === "success").length;
    toast(`Push finished: ${successes} of ${records.length} product${records.length === 1 ? "" : "s"} synced.`, successes === records.length ? "success" : "error");
    await Promise.all([loadProducts(), loadSync()]);
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
  }
});

byId("pull-woo").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const records = await api("/sync/pull", { method: "POST" });
    const successes = records.filter((record) => record.status === "success").length;
    toast(`Pull finished: ${successes} product${successes === 1 ? "" : "s"} imported or updated.`, successes === records.length ? "success" : "error");
    await Promise.all([loadProducts(), loadSync()]);
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
  }
});

loadProducts();
