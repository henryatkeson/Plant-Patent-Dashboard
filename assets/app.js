const state = {
  records: [],
  filtered: [],
  byKey: new Map(),
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
  timelineInsight: document.querySelector("#timelineInsight"),
  cropInsight: document.querySelector("#cropInsight"),
  latestList: document.querySelector("#latestList"),
  sourceSummary: document.querySelector("#sourceSummary"),
  timelineCount: document.querySelector("#timelineCount"),
  cropCount: document.querySelector("#cropCount"),
  latestCount: document.querySelector("#latestCount"),
  sourceCount: document.querySelector("#sourceCount"),
  rowCount: document.querySelector("#rowCount"),
  recordsBody: document.querySelector("#recordsBody"),
  drawer: document.querySelector("#recordDrawer"),
  drawerBackdrop: document.querySelector("#drawerBackdrop"),
  drawerClose: document.querySelector("#drawerClose"),
  drawerTitle: document.querySelector("#drawerTitle"),
  drawerBody: document.querySelector("#drawerBody"),
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

function detailValue(row, keys) {
  for (const key of keys) {
    if (row[key]) return row[key];
  }
  return "";
}

function sourceLabel(row) {
  if (row.sourceUrl) return "Verified link";
  if (normalize(row.source).includes("workbook")) return "Baseline";
  return row.source || "Source";
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

function formatSigned(value) {
  if (value > 0) return `+${value}`;
  return String(value);
}

function renderBars(target, entries, max, emptyText) {
  target.innerHTML = "";
  if (!entries.length) {
    target.innerHTML = `<p class="subtle">${emptyText}</p>`;
    return;
  }
  for (const entry of entries) {
    const label = Array.isArray(entry) ? entry[0] : entry.label;
    const value = Array.isArray(entry) ? entry[1] : entry.value;
    const note = Array.isArray(entry) ? "" : entry.note;
    const noteClass = Array.isArray(entry) ? "" : entry.noteClass;
    const width = max ? Math.max(4, Math.round((value / max) * 100)) : 0;
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <span class="bar-label" title="${escapeHtml(label)}">${escapeHtml(label)}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${width}%"></span></span>
      <span class="bar-value">
        <strong>${value.toLocaleString()}</strong>
        ${note ? `<span class="bar-note ${escapeHtml(noteClass || "")}">${escapeHtml(note)}</span>` : ""}
      </span>
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
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.dataset.recordKey = row.__key;
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
  const currentYear = String(new Date().getFullYear());
  const annotatedYears = yearEntries.map(([year, value], index) => {
    const previous = index > 0 ? yearEntries[index - 1][1] : null;
    const delta = previous === null ? null : value - previous;
    const isCurrentYear = year === currentYear;
    return {
      label: isCurrentYear ? `${year} YTD` : year,
      value,
      note: isCurrentYear ? "partial" : delta === null ? "" : `${formatSigned(delta)} YoY`,
      noteClass: delta > 0 ? "good" : delta < 0 ? "soft" : "",
    };
  });
  renderBars(els.timelineChart, annotatedYears, maxYear, "No dated records match the filters.");
  els.timelineCount.textContent = `${yearEntries.length} years shown`;

  const peakYear = yearEntries.reduce((best, entry) => (entry[1] > best[1] ? entry : best), ["", 0]);
  const lastFullYear = [...yearEntries].reverse().find(([year]) => year !== currentYear);
  const currentYearEntry = yearEntries.find(([year]) => year === currentYear);
  els.timelineInsight.innerHTML = `
    <div class="insight-pill"><span>Peak year</span><strong>${escapeHtml(peakYear[0] || "--")} · ${peakYear[1].toLocaleString()}</strong></div>
    <div class="insight-pill"><span>Latest full year</span><strong>${escapeHtml(lastFullYear?.[0] || "--")} · ${(lastFullYear?.[1] || 0).toLocaleString()}</strong></div>
    <div class="insight-pill"><span>${escapeHtml(currentYear)} so far</span><strong>${(currentYearEntry?.[1] || 0).toLocaleString()} records</strong></div>
  `;

  const cropEntries = topEntries(countBy(rows, (row) => row.crop || "Unclassified"), 12);
  const maxCrop = Math.max(0, ...cropEntries.map((entry) => entry[1]));
  const annotatedCrops = cropEntries.map(([label, value]) => ({
    label,
    value,
    note: rows.length ? `${Math.round((value / rows.length) * 100)}% share` : "",
  }));
  renderBars(els.cropChart, annotatedCrops, maxCrop, "No crop data matches the filters.");
  els.cropCount.textContent = `${cropEntries.length} crops shown`;
  const topCrop = cropEntries[0] || ["--", 0];
  const topThree = cropEntries.slice(0, 3).reduce((sum, entry) => sum + entry[1], 0);
  els.cropInsight.innerHTML = `
    <div class="insight-pill"><span>Top crop</span><strong>${escapeHtml(topCrop[0])} · ${topCrop[1].toLocaleString()}</strong></div>
    <div class="insight-pill"><span>Top 3 share</span><strong>${rows.length ? Math.round((topThree / rows.length) * 100) : 0}%</strong></div>
    <div class="insight-pill"><span>Crop breadth</span><strong>${Object.keys(countBy(rows, (row) => row.crop || "Unclassified")).length.toLocaleString()} crops</strong></div>
  `;
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
    tr.dataset.recordKey = row.__key;
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

function renderDetailItem(label, value) {
  if (!value) return "";
  return `
    <div class="detail-item">
      <span>${escapeHtml(label)}</span>
      <p>${escapeHtml(value)}</p>
    </div>
  `;
}

function openRecordDrawer(recordKey) {
  const row = state.byKey.get(recordKey);
  if (!row) return;

  const title = row.cultivar || row.title || row.tradeName || "Patent record";
  const sourceText = row.primarySource || row.patentNumber || row.publicationNumber || row.sourceKind || "Source";
  const owner = detailValue(row, ["assignee", "breeders", "inventors"]);
  const sourceAction = row.sourceUrl
    ? `<a class="detail-link" href="${escapeHtml(row.sourceUrl)}" target="_blank" rel="noopener">Open patent/source</a>`
    : `<span class="detail-button-muted">No direct source link yet</span>`;

  els.drawerTitle.textContent = title;
  els.drawerBody.innerHTML = `
    <div class="detail-actions">
      ${sourceAction}
      <span class="badge ${row.sourceUrl ? "verified" : "baseline"}">${escapeHtml(sourceLabel(row))}</span>
      <span class="badge ${statusClass(row)}">${escapeHtml(row.status || row.sourceKind || "record")}</span>
    </div>
    <div class="detail-grid">
      ${renderDetailItem("Date", formatDate(row.date))}
      ${renderDetailItem("Crop", row.crop)}
      ${renderDetailItem("Cultivar / denomination", row.cultivar)}
      ${renderDetailItem("Trade name", row.tradeName)}
      ${renderDetailItem("Title", row.title)}
      ${renderDetailItem("Primary source", sourceText)}
      ${renderDetailItem("Source type", row.sourceKind || row.source)}
      ${renderDetailItem("Assignee / breeder", owner)}
      ${renderDetailItem("Inventors", row.inventors && row.inventors !== owner ? row.inventors : "")}
      ${renderDetailItem("Application number", row.applicationNumber)}
      ${renderDetailItem("Filed", row.filedDateText)}
      ${renderDetailItem("List", row.list)}
      ${renderDetailItem("Notes", row.notes)}
    </div>
    <p class="detail-note">
      ${row.sourceUrl
        ? "This record has a direct source link. The button above opens the patent or source page in a new tab."
        : "This record is still based on the baseline workbook or another non-linked source. We can add source verification as we enrich the dataset."}
    </p>
  `;
  els.drawerBackdrop.hidden = false;
  els.drawer.classList.add("open");
  els.drawer.setAttribute("aria-hidden", "false");
}

function closeRecordDrawer() {
  els.drawer.classList.remove("open");
  els.drawer.setAttribute("aria-hidden", "true");
  els.drawerBackdrop.hidden = true;
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
  state.records = (payload.records || [])
    .map((row, index) => ({ ...row, __key: `${index}-${row.id || row.primarySource || row.cultivar || "record"}` }))
    .sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
  state.byKey = new Map(state.records.map((row) => [row.__key, row]));
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
els.latestList.addEventListener("click", (event) => {
  const card = event.target.closest("[data-record-key]");
  if (!card || event.target.closest("a")) return;
  openRecordDrawer(card.dataset.recordKey);
});
els.latestList.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const card = event.target.closest("[data-record-key]");
  if (!card) return;
  event.preventDefault();
  openRecordDrawer(card.dataset.recordKey);
});
els.recordsBody.addEventListener("click", (event) => {
  const row = event.target.closest("[data-record-key]");
  if (!row || event.target.closest("a")) return;
  openRecordDrawer(row.dataset.recordKey);
});
els.drawerClose.addEventListener("click", closeRecordDrawer);
els.drawerBackdrop.addEventListener("click", closeRecordDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeRecordDrawer();
});

init().catch((error) => {
  els.lastRefresh.textContent = "Could not load dashboard data";
  console.error(error);
});
