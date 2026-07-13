const state = {
  records: [],
  filtered: [],
};

const els = {
  lastRefresh: document.querySelector("#lastRefresh"),
  metricRecords: document.querySelector("#metricRecords"),
  metricLatest: document.querySelector("#metricLatest"),
  metricIssued: document.querySelector("#metricIssued"),
  metricPending: document.querySelector("#metricPending"),
  searchInput: document.querySelector("#searchInput"),
  cropFilter: document.querySelector("#cropFilter"),
  sourceFilter: document.querySelector("#sourceFilter"),
  fromDate: document.querySelector("#fromDate"),
  toDate: document.querySelector("#toDate"),
  resetButton: document.querySelector("#resetButton"),
  timelineChart: document.querySelector("#timelineChart"),
  cropChart: document.querySelector("#cropChart"),
  latestList: document.querySelector("#latestList"),
  sourceSummary: document.querySelector("#sourceSummary"),
  timelineCount: document.querySelector("#timelineCount"),
  cropCount: document.querySelector("#cropCount"),
  latestCount: document.querySelector("#latestCount"),
  sourceCount: document.querySelector("#sourceCount"),
  rowCount: document.querySelector("#rowCount"),
  recordsBody: document.querySelector("#recordsBody"),
};

function formatDate(value) {
  if (!value) return "--";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function normalize(value) {
  return String(value || "").toLowerCase();
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function countBy(rows, fn) {
  return rows.reduce((acc, row) => {
    const key = fn(row);
    if (!key) return acc;
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function topEntries(counts, limit) {
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit);
}

function renderBars(target, entries, max, emptyText) {
  target.innerHTML = "";
  if (!entries.length) {
    target.innerHTML = `<p class="subtle">${emptyText}</p>`;
    return;
  }
  for (const [label, value] of entries) {
    const width = max ? Math.max(4, Math.round((value / max) * 100)) : 0;
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <span>${escapeHtml(label)}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${width}%"></span></span>
      <strong>${value.toLocaleString()}</strong>
    `;
    target.appendChild(row);
  }
}

function populateFilters() {
  const crops = [...new Set(state.records.map((row) => row.crop).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b));
  els.cropFilter.innerHTML = `<option value="">All crops</option>${crops
    .map((crop) => `<option value="${escapeHtml(crop)}">${escapeHtml(crop)}</option>`)
    .join("")}`;

  const sources = [...new Set(state.records.map((row) => row.sourceKind).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b));
  els.sourceFilter.innerHTML = `<option value="">All sources</option>${sources
    .map((source) => `<option value="${escapeHtml(source)}">${escapeHtml(source)}</option>`)
    .join("")}`;
}

function applyFilters() {
  const term = normalize(els.searchInput.value);
  const crop = els.cropFilter.value;
  const source = els.sourceFilter.value;
  const from = els.fromDate.value;
  const to = els.toDate.value;

  state.filtered = state.records.filter((row) => {
    const haystack = normalize([
      row.title,
      row.crop,
      row.cultivar,
      row.tradeName,
      row.primarySource,
      row.breeders,
      row.assignee,
      row.inventors,
      row.notes,
    ].join(" "));
    if (term && !haystack.includes(term)) return false;
    if (crop && row.crop !== crop) return false;
    if (source && row.sourceKind !== source) return false;
    if (from && (!row.date || row.date < from)) return false;
    if (to && (!row.date || row.date > to)) return false;
    return true;
  });

  render();
}

function renderMetrics(rows) {
  const latest = rows.find((row) => row.date)?.date || "";
  const issued = rows.filter((row) => normalize(row.sourceKind).includes("issued plant patent")).length;
  const pending = rows.filter((row) => normalize(row.status).includes("pending") || normalize(row.sourceKind).includes("application")).length;

  els.metricRecords.textContent = rows.length.toLocaleString();
  els.metricLatest.textContent = formatDate(latest);
  els.metricIssued.textContent = issued.toLocaleString();
  els.metricPending.textContent = pending.toLocaleString();
}

function sourceLabel(row) {
  if (row.sourceUrl) return "Verified link";
  if (normalize(row.source).includes("workbook")) return "Baseline";
  return row.source || "Source";
}

function statusClass(row) {
  const status = normalize(row.status);
  if (status.includes("pending") || normalize(row.sourceKind).includes("application")) return "pending";
  if (normalize(row.sourceKind).includes("issued")) return "issued";
  return "";
}

function renderLatest(rows) {
  const latest = rows.filter((row) => row.date).slice(0, 6);
  els.latestCount.textContent = `${latest.length} shown`;
  els.latestList.innerHTML = "";
  if (!latest.length) {
    els.latestList.innerHTML = `<p class="empty-state">No records match the filters.</p>`;
    return;
  }

  for (const row of latest) {
    const title = row.cultivar || row.title || row.tradeName || "Untitled record";
    const sourceText = row.primarySource || row.patentNumber || row.sourceKind || "";
    const sourceMarkup = row.sourceUrl
      ? `<a href="${escapeHtml(row.sourceUrl)}" target="_blank" rel="noopener">${escapeHtml(sourceText)}</a>`
      : escapeHtml(sourceText);
    const owner = row.assignee || row.breeders || row.inventors || "";
    const card = document.createElement("article");
    card.className = "latest-card";
    card.innerHTML = `
      <div class="meta-line">
        <span class="badge">${escapeHtml(formatDate(row.date))}</span>
        <span class="badge">${escapeHtml(row.crop || "Unclassified")}</span>
      </div>
      <h3>${escapeHtml(title)}</h3>
      <div>
        ${sourceMarkup}
        <span class="subtle">${escapeHtml(row.sourceKind || row.source || "")}</span>
      </div>
      <div class="meta-line">
        <span class="badge ${statusClass(row)}">${escapeHtml(row.status || row.sourceKind || "record")}</span>
        <span class="badge ${row.sourceUrl ? "verified" : "baseline"}">${escapeHtml(sourceLabel(row))}</span>
      </div>
      ${owner ? `<span class="subtle">${escapeHtml(owner)}</span>` : ""}
    `;
    els.latestList.appendChild(card);
  }
}

function renderSources(rows) {
  const entries = topEntries(countBy(rows, (row) => row.sourceKind || row.source || "Other"), 6);
  els.sourceCount.textContent = `${entries.length} sources`;
  els.sourceSummary.innerHTML = "";
  if (!entries.length) {
    els.sourceSummary.innerHTML = `<p class="empty-state">No sources match the filters.</p>`;
    return;
  }
  for (const [label, value] of entries) {
    const row = document.createElement("div");
    row.className = "source-row";
    row.innerHTML = `<span>${escapeHtml(label)}</span><strong>${value.toLocaleString()}</strong>`;
    els.sourceSummary.appendChild(row);
  }
}

function renderCharts(rows) {
  const byYear = countBy(rows, (row) => (row.date || "").slice(0, 4));
  const yearEntries = Object.entries(byYear)
    .sort((a, b) => a[0].localeCompare(b[0]))
    .slice(-12);
  const maxYear = Math.max(0, ...yearEntries.map((entry) => entry[1]));
  renderBars(els.timelineChart, yearEntries, maxYear, "No dated records match the filters.");
  els.timelineCount.textContent = `${yearEntries.length} years shown`;

  const cropEntries = topEntries(countBy(rows, (row) => row.crop || "Unclassified"), 12);
  const maxCrop = Math.max(0, ...cropEntries.map((entry) => entry[1]));
  renderBars(els.cropChart, cropEntries, maxCrop, "No crop data matches the filters.");
  els.cropCount.textContent = `${cropEntries.length} crops shown`;
}

function renderTable(rows) {
  els.rowCount.textContent = `${rows.length.toLocaleString()} matching rows`;
  els.recordsBody.innerHTML = "";

  for (const row of rows.slice(0, 500)) {
    const title = row.cultivar || row.title || row.tradeName || "Untitled record";
    const link = row.sourceUrl
      ? `<a href="${escapeHtml(row.sourceUrl)}" target="_blank" rel="noopener">${escapeHtml(row.primarySource || row.patentNumber || "USPTO")}</a>`
      : `${escapeHtml(row.primarySource || row.patentNumber || "")}`;
    const subtitle = [row.tradeName, row.title && row.title !== title ? row.title : ""].filter(Boolean).join(" | ");
    const owner = row.assignee || row.breeders || row.inventors || "";
    const status = row.status || row.sourceKind || "";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${formatDate(row.date)}</td>
      <td><span class="badge">${escapeHtml(row.crop || "")}</span></td>
      <td><strong class="record-title">${escapeHtml(title)}</strong>${subtitle ? `<span class="subtle">${escapeHtml(subtitle)}</span>` : ""}</td>
      <td>${link}<span class="subtle">${row.sourceKind || row.source || ""}</span></td>
      <td><span class="badge ${statusClass(row)}">${escapeHtml(status)}</span></td>
      <td>${escapeHtml(owner)}</td>
    `;
    els.recordsBody.appendChild(tr);
  }
}

function render() {
  renderMetrics(state.filtered);
  renderLatest(state.filtered);
  renderSources(state.filtered);
  renderCharts(state.filtered);
  renderTable(state.filtered);
}

function resetFilters() {
  els.searchInput.value = "";
  els.cropFilter.value = "";
  els.sourceFilter.value = "";
  els.fromDate.value = "";
  els.toDate.value = "";
  applyFilters();
}

async function init() {
  const response = await fetch("data/plant_patents.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`Could not load data: ${response.status}`);
  const payload = await response.json();
  state.records = (payload.records || []).sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
  state.filtered = [...state.records];
  const generatedAt = payload.metadata?.generatedAt ? new Date(payload.metadata.generatedAt) : null;
  els.lastRefresh.textContent = generatedAt && !Number.isNaN(generatedAt.getTime())
    ? `Data refreshed ${generatedAt.toLocaleString()}`
    : "Data loaded";
  populateFilters();
  render();
}

for (const input of [els.searchInput, els.cropFilter, els.sourceFilter, els.fromDate, els.toDate]) {
  input.addEventListener("input", applyFilters);
}
els.resetButton.addEventListener("click", resetFilters);

init().catch((error) => {
  els.lastRefresh.textContent = "Could not load dashboard data";
  console.error(error);
});
