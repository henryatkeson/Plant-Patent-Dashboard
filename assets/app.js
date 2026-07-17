const state = {
  records: [],
  filtered: [],
  byKey: new Map(),
  cpvoVarieties: [],
  ownerProfiles: [],
  filteredOwners: [],
  ownerByKey: new Map(),
  companyProfiles: [],
  sourceStatus: null,
  lastFocus: null,
};

const els = {
  lastRefresh: document.querySelector("#lastRefresh"),
  sourcingBrief: document.querySelector("#sourcingBrief"),
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
  liveStatus: document.querySelector("#liveStatus"),
  ownerCount: document.querySelector("#ownerCount"),
  ownerSearchInput: document.querySelector("#ownerSearchInput"),
  ownerView: document.querySelector("#ownerView"),
  ownerSort: document.querySelector("#ownerSort"),
  ownerBody: document.querySelector("#ownerBody"),
  timelineCount: document.querySelector("#timelineCount"),
  cropCount: document.querySelector("#cropCount"),
  latestCount: document.querySelector("#latestCount"),
  sourceCount: document.querySelector("#sourceCount"),
  rowCount: document.querySelector("#rowCount"),
  recordsBody: document.querySelector("#recordsBody"),
  drawer: document.querySelector("#recordDrawer"),
  drawerBackdrop: document.querySelector("#drawerBackdrop"),
  drawerClose: document.querySelector("#drawerClose"),
  drawerEyebrow: document.querySelector("#drawerEyebrow"),
  drawerTitle: document.querySelector("#drawerTitle"),
  drawerBody: document.querySelector("#drawerBody"),
  tabButtons: document.querySelectorAll("[data-tab-target]"),
  viewPanels: document.querySelectorAll("[data-view-panel]"),
};

const LATEST_RELEVANT_CROPS = new Set([
  "almond",
  "almond rootstock",
  "annona",
  "apple",
  "apple rootstock",
  "apple/quince hybrid",
  "apricot",
  "avocado",
  "avocado rootstock",
  "banana",
  "blackberry",
  "blue honeysuckle",
  "blueberry",
  "cacao",
  "cherimoya",
  "cherry",
  "cherry rootstock",
  "cherry-sweet",
  "cherry-tart",
  "chestnut",
  "citrus",
  "citrus-finger lime hybrid",
  "citrus-grapefruit",
  "citrus-lemon",
  "citrus-mandarin hybrid",
  "citrus-misc",
  "citrus rootstock",
  "citrus-sweet orange",
  "citrus-sweet orange-like hybrid",
  "coconut",
  "cranberry",
  "currant",
  "currant-black",
  "elderberry",
  "fig",
  "goji",
  "gooseberry",
  "grape",
  "guava",
  "hazelnut",
  "huckleberry (vaccinium ovatum)",
  "kiwifruit",
  "lemon",
  "lingonberry",
  "loquat",
  "macadamia",
  "mango",
  "mulberry",
  "nectarine",
  "olive",
  "orange",
  "papaya",
  "passion fruit",
  "peach",
  "peach rootstock",
  "pear",
  "pear-rootstock",
  "pecan",
  "persimmon",
  "pineapple",
  "pistachio",
  "pistachio rootstock",
  "pitahaya",
  "plum",
  "plum rootstock",
  "plum-cherry",
  "plum-interspecific",
  "pomegranate",
  "prunophora hybrid",
  "prunophora hybrid-plumcot",
  "prunus",
  "quince",
  "raspberry",
  "raspberry-black",
  "red bayberry",
  "rubus",
  "soursop",
  "strawberry",
  "sugar apple",
  "walnut",
  "walnut rootstock",
  "walnut-black",
]);

function formatDate(value) {
  if (!value) return "--";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function debounce(fn, delay = 180) {
  let timer = 0;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), delay);
  };
}

function yearRange(firstYear, lastYear) {
  if (!firstYear && !lastYear) return "--";
  if (firstYear === lastYear) return String(firstYear);
  return `${firstYear || "--"}-${lastYear || "--"}`;
}

function normalize(value) {
  return String(value || "").toLowerCase();
}

function normalizeCompany(value) {
  return normalize(value)
    .replace(/['`']/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\b(inc|llc|ltd|limited|corp|corporation|company|co|gmbh|bv|sa|sas|ag|nv|plc|pty|pte|holdings|holding)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function displayText(value, fallback = "") {
  const text = String(value || "")
    .replace(/\?{2,}/g, "patent unknown")
    .replace(/Investigaci\uFFFDn/gi, "Investigacion")
    .replace(/f\uFFFDr/gi, "fuer")
    .replace(/\uFFFD/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return text || fallback;
}

function companyProfileMatchesText(profile, text) {
  const haystack = ` ${normalizeCompany(text)} `;
  const aliases = [profile.canonicalName, ...(profile.aliases || [])];
  return aliases.some((alias) => {
    const needle = normalizeCompany(alias);
    if (!needle) return false;
    return needle.length <= 4 ? haystack.includes(` ${needle} `) : haystack.includes(needle);
  });
}

function companyProfilesForText(text) {
  const matches = [];
  const seen = new Set();
  for (const profile of state.companyProfiles) {
    if (!companyProfileMatchesText(profile, text)) continue;
    if (seen.has(profile.canonicalName)) continue;
    seen.add(profile.canonicalName);
    matches.push(profile);
  }
  return matches;
}

function companyActions(profile) {
  const links = [];
  if (profile.website) links.push(`<a class="detail-link" href="${escapeHtml(profile.website)}" target="_blank" rel="noopener">Company website</a>`);
  if (profile.contactUrl) links.push(`<a class="detail-button-muted" href="${escapeHtml(profile.contactUrl)}" target="_blank" rel="noopener">Contact page</a>`);
  if (profile.linkedinUrl) links.push(`<a class="detail-button-muted" href="${escapeHtml(profile.linkedinUrl)}" target="_blank" rel="noopener">LinkedIn</a>`);
  return links.join("");
}

function renderNewsLinks(profile) {
  const links = (profile.newsLinks || []).slice(0, 3);
  if (!links.length) return "";
  return `
    <div class="news-link-list">
      ${links.map((link) => `
        <a href="${escapeHtml(link.url)}" target="_blank" rel="noopener">
          ${escapeHtml(link.label || link.url)}
        </a>
      `).join("")}
    </div>
  `;
}

function renderCompanyCards(profiles) {
  if (!profiles.length) return "";
  return `
    <div class="matched-company-list">
      ${profiles.map((profile) => `
        <div class="matched-company">
          <div class="matched-company-head">
            <strong>${escapeHtml(profile.canonicalName || "Company profile")}</strong>
            <span>${escapeHtml(profile.targetFit || "Target fit not yet assessed")}</span>
          </div>
          ${profile.description ? `<p>${escapeHtml(profile.description)}</p>` : ""}
          <div class="detail-actions">${companyActions(profile)}</div>
          ${renderNewsLinks(profile)}
        </div>
      `).join("")}
    </div>
  `;
}

function displayAuditValue(value) {
  return displayText(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderOwnerAudit(owner) {
  const brandExamples = Array.isArray(owner.brandExamples)
    ? owner.brandExamples.filter(Boolean)
    : String(owner.brandExamples || "").split("|").map((item) => item.trim()).filter(Boolean);
  const contactName = [owner.primaryContactName, owner.primaryContactTitle].filter(Boolean).join(" - ");
  const contactLink = owner.primaryContactUrl || owner.contactSourceUrl;
  const evidenceLink = owner.websiteCultivarEvidenceUrl || owner.candidateParentEvidenceUrl;
  const researchSources = Array.isArray(owner.webResearchSources)
    ? owner.webResearchSources
    : [];
  const rows = [
    owner.webResearchStatus ? ["Web research", `${displayAuditValue(owner.webResearchStatus)}${owner.webResearchReviewedAt ? ` - reviewed ${displayText(owner.webResearchReviewedAt)}` : ""}`] : null,
    owner.auditStatus ? ["Audit status", displayAuditValue(owner.auditStatus)] : null,
    owner.auditConfidence ? ["Audit confidence", displayAuditValue(owner.auditConfidence)] : null,
    owner.ownershipType ? ["Ownership", displayAuditValue(owner.ownershipType)] : null,
    owner.parentCompany ? ["Parent company", displayText(owner.parentCompany)] : null,
    owner.ownershipSummary ? ["Ownership notes", displayText(owner.ownershipSummary)] : null,
    owner.headquarters ? ["Headquarters", displayText(owner.headquarters)] : null,
    owner.leadershipSummary ? ["Leadership", displayText(owner.leadershipSummary)] : null,
    owner.trademarkStatus ? ["Trademark check", displayAuditValue(owner.trademarkStatus)] : null,
    owner.trademarkOwner ? ["Trademark owner", displayText(owner.trademarkOwner)] : null,
    brandExamples.length ? ["Brand examples", brandExamples.slice(0, 5).map(displayText).join(" | ")] : null,
    owner.websiteCultivarCount ? ["Website cultivar count", `${Number(owner.websiteCultivarCount).toLocaleString()}${owner.websiteCultivarCountBasis ? ` - ${displayText(owner.websiteCultivarCountBasis)}` : ""}`] : null,
    contactName ? ["Primary contact", contactName] : null,
    owner.primaryContactEmail ? ["Public business email", displayText(owner.primaryContactEmail)] : null,
    owner.primaryContactPhone ? ["Public business phone", displayText(owner.primaryContactPhone)] : null,
    owner.candidateParent ? ["Candidate parent", `${displayText(owner.candidateParent)}${owner.candidateParentConfidence ? ` (${displayAuditValue(owner.candidateParentConfidence)} confidence)` : ""}${owner.candidateParentBasis ? ` - ${displayText(owner.candidateParentBasis)}` : ""}`] : null,
    owner.auditNotes ? ["Audit notes", displayText(owner.auditNotes)] : null,
    owner.webResearchNotes ? ["Research notes", displayText(owner.webResearchNotes)] : null,
  ].filter(Boolean);
  const links = [
    contactLink ? `<a href="${escapeHtml(contactLink)}" target="_blank" rel="noopener">Contact evidence</a>` : "",
    evidenceLink ? `<a href="${escapeHtml(evidenceLink)}" target="_blank" rel="noopener">Cultivar evidence</a>` : "",
    owner.trademarkEvidenceUrl ? `<a href="${escapeHtml(owner.trademarkEvidenceUrl)}" target="_blank" rel="noopener">Trademark evidence</a>` : "",
    ...researchSources.slice(0, 4).map((source) => {
      const url = typeof source === "string" ? source : source.url;
      const label = typeof source === "string" ? "Research source" : (source.label || "Research source");
      return url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>` : "";
    }),
  ].filter(Boolean).join("");
  if (!rows.length && !links) return "";
  return `
    <div class="audit-panel">
      <h3>Diligence Notes</h3>
      <dl>
        ${rows.map(([label, value]) => `
          <div>
            <dt>${escapeHtml(label)}</dt>
            <dd>${escapeHtml(value)}</dd>
          </div>
        `).join("")}
      </dl>
      ${links ? `<div class="audit-links">${links}</div>` : ""}
    </div>
  `;
}

function isResolvedAffiliation(owner) {
  return ["verified_relationship", "probable_relationship"].includes(normalize(owner.affiliationStatus));
}

function renderAffiliationEvidence(owner) {
  const linkedBreeders = Array.isArray(owner.affiliatedBreeders) ? owner.affiliatedBreeders : [];
  if (linkedBreeders.length) {
    return `
      <div class="audit-panel">
        <h3>Affiliated Breeders</h3>
        <p class="detail-note">These are evidence-backed relationships to the breeding program. Their personal record histories are not added to this company's legal portfolio unless a specific record names the company as assignee or holder.</p>
        <dl>
          ${linkedBreeders.slice(0, 30).map((breeder) => `
            <div>
              <dt>${escapeHtml(displayText(breeder.name))}</dt>
              <dd>${escapeHtml(displayAuditValue(breeder.confidence || "unverified"))} confidence${breeder.rightsRecordCount ? ` | ${Number(breeder.rightsRecordCount).toLocaleString()} scoped assignee records` : " | affiliation only"}</dd>
            </div>
          `).join("")}
        </dl>
        ${Number(owner.affiliatedBreederCount || 0) > 30 ? `<p class="detail-note">Showing 30 of ${Number(owner.affiliatedBreederCount).toLocaleString()} linked breeders.</p>` : ""}
      </div>
    `;
  }
  if (!owner.affiliatedCompany || !owner.affiliationStatus || owner.affiliationStatus === "unresolved") return "";
  const status = displayAuditValue(owner.affiliationStatus);
  const rightsIds = Array.isArray(owner.affiliationRightsRecordIds) ? owner.affiliationRightsRecordIds : [];
  const rightsSummary = owner.affiliationRightsBasis === "assignee_on_scoped_patent_records"
    ? `${rightsIds.length.toLocaleString()} patent records specifically name the company as assignee`
    : "No portfolio ownership is inferred from this affiliation";
  const evidence = Array.isArray(owner.affiliationEvidence) ? owner.affiliationEvidence : [];
  const evidenceLinks = evidence.map((source) => {
    const url = typeof source === "string" ? source : source.url;
    const label = typeof source === "string" ? "Affiliation source" : (source.label || "Affiliation source");
    return url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>` : "";
  }).filter(Boolean).join("");
  return `
    <div class="audit-panel">
      <h3>${isResolvedAffiliation(owner) ? "Breeding Program Affiliation" : "Candidate Affiliation"}</h3>
      <dl>
        <div><dt>Company / program</dt><dd>${escapeHtml(displayText(owner.affiliatedCompany))}</dd></div>
        <div><dt>Relationship status</dt><dd>${escapeHtml(status)} | ${escapeHtml(displayAuditValue(owner.affiliationConfidence || "unverified"))} confidence</dd></div>
        ${owner.affiliationRelationshipType ? `<div><dt>Relationship</dt><dd>${escapeHtml(displayAuditValue(owner.affiliationRelationshipType))}</dd></div>` : ""}
        ${owner.affiliationBasis ? `<div><dt>Evidence basis</dt><dd>${escapeHtml(displayText(owner.affiliationBasis))}</dd></div>` : ""}
        <div><dt>Rights treatment</dt><dd>${escapeHtml(rightsSummary)}</dd></div>
      </dl>
      ${evidenceLinks ? `<div class="audit-links">${evidenceLinks}</div>` : ""}
    </div>
  `;
}

function ownerContactStatus(owner) {
  const namedContact = [owner.primaryContactName, owner.primaryContactTitle].filter(Boolean).join(" - ");
  const directDetails = [owner.primaryContactEmail, owner.primaryContactPhone].filter(Boolean).join(" | ");
  if (namedContact && (owner.primaryContactUrl || owner.contactSourceUrl)) {
    return {
      label: "Named contact sourced",
      confidence: "High",
      body: [namedContact, directDetails].filter(Boolean).join(" | "),
      action: owner.primaryContactUrl || owner.contactSourceUrl,
      actionLabel: "Open contact evidence",
    };
  }
  if (owner.companyContactUrl) {
    return {
      label: "Company contact page",
      confidence: "High",
      body: "Use the official company contact page as the first outreach path.",
      action: owner.companyContactUrl,
      actionLabel: "Open contact page",
    };
  }
  if (owner.companyWebsite) {
    return {
      label: "Website only",
      confidence: "Medium",
      body: "Company website is verified, but a direct contact page or named decision maker is not yet captured.",
      action: owner.companyWebsite,
      actionLabel: "Open website",
    };
  }
  if (owner.candidateParent) {
    return {
      label: "Needs holder verification",
      confidence: "Low",
      body: `Possible parent: ${displayText(owner.candidateParent)}. Verify holder/applicant evidence before outreach.`,
      action: owner.candidateParentEvidenceUrl,
      actionLabel: "Open evidence",
    };
  }
  return {
    label: "No public contact found",
    confidence: "Low",
    body: "No source-backed company contact is captured yet. Do not infer a contact from breeder-only records.",
    action: "",
    actionLabel: "",
  };
}

function acquisitionFit(owner) {
  if (owner.acquisitionFitBand) {
    const band = displayText(owner.acquisitionFitBand);
    const className = normalize(band).includes("high")
      ? "good"
      : normalize(band).includes("benchmark") || normalize(band).includes("too large")
        ? "warn"
        : normalize(band).includes("public") || normalize(band).includes("partnership") || normalize(band).includes("verification") || normalize(band).includes("low")
          ? "muted"
          : "neutral";
    return { label: band, className };
  }
  const targetFit = normalize(owner.targetFit);
  const name = normalize(owner.ownerName);
  const recordCount = Number(owner.recordCount || 0);
  const protectedCount = Number(owner.protectedIpCount || 0);
  if (targetFit.includes("too large") || targetFit.includes("far too large") || targetFit.includes("benchmark only")) {
    return { label: "Benchmark / likely too large", className: "warn" };
  }
  if (targetFit.includes("above the current target range") || targetFit.includes("larger than the current target range") || targetFit.includes("likely larger")) {
    return { label: "Needs company sizing", className: "neutral" };
  }
  if (name.includes("university") || name.includes("usda") || name.includes("institute") || name.includes("research")) {
    return { label: "Public or institutional signal", className: "muted" };
  }
  if (owner.companyWebsite && protectedCount >= 2 && protectedCount <= 100 && recordCount <= 150) {
    return { label: "Potential acquisition lead", className: "good" };
  }
  if (owner.companyWebsite || owner.companyDescription) {
    return { label: "Company profile needs sizing", className: "neutral" };
  }
  return { label: "Needs profile verification", className: "muted" };
}

function profileNextAction(owner, contact) {
  const band = normalize(owner.acquisitionFitBand);
  if (band.includes("high")) {
    return "Prioritize company sizing, ownership confirmation, and a source-backed contact path; this profile fits the current acquisition screen better than most.";
  }
  if (band.includes("review")) {
    return "Move into research review: confirm ownership, estimate scale, and check whether the breeding asset is separable.";
  }
  if (band.includes("needs verification")) {
    return "Verify the holder, company website, and operating status before treating this as an actionable target.";
  }
  if (band.includes("public")) {
    return "Treat as ecosystem intelligence or licensing context, not a company acquisition target.";
  }
  if (band.includes("partnership")) {
    return "Treat as a licensing, partnership, or relationship opportunity unless a controllable asset or operating-company transaction becomes available.";
  }
  if (band.includes("benchmark")) {
    return "Use as a market benchmark or buyer/license counterparty, not a near-term acquisition target.";
  }
  const fit = normalize(owner.targetFit);
  if (fit.includes("too large") || fit.includes("benchmark only")) {
    return "Use as a market benchmark or buyer/license counterparty, not a near-term acquisition target.";
  }
  if (fit.includes("above the current target range") || fit.includes("larger than the current target range") || fit.includes("likely larger")) {
    return "Verify company scale, ownership, and whether a separable breeding asset exists before treating this as an acquisition lead.";
  }
  if (!owner.companyWebsite && !owner.companyDescription) {
    return "Verify the legal holder and identify a real company profile before outreach.";
  }
  if (!owner.companyContactUrl && !owner.primaryContactUrl && !owner.contactSourceUrl) {
    return "Find a source-backed contact path or named owner/operator before moving to outreach.";
  }
  if (contact.confidence === "High") {
    return "Ready for business review once ownership, size, and fit are checked.";
  }
  return "Keep in research queue until contact and ownership evidence are stronger.";
}

function profileBlockers(owner) {
  if (Array.isArray(owner.acquisitionFitBlockers) && owner.acquisitionFitBlockers.length) {
    return owner.acquisitionFitBlockers.map(displayText);
  }
  const blockers = [];
  const targetFit = normalize(owner.targetFit);
  if (targetFit.includes("too large") || targetFit.includes("far too large")) blockers.push("Likely too large for the $1-5m EBITDA target range.");
  if (!owner.companyWebsite) blockers.push("No verified company website captured.");
  if (!owner.companyContactUrl && !owner.primaryContactUrl && !owner.contactSourceUrl) blockers.push("No source-backed contact path captured.");
  if (Number(owner.legalOwnerRecordCount || 0) === 0) blockers.push("No confirmed legal-owner records in the current profile.");
  if (owner.auditConfidence && normalize(owner.auditConfidence) === "low") blockers.push("Manual audit confidence is low.");
  if (!blockers.length) blockers.push("No major data blocker captured yet; still verify company size and ownership before outreach.");
  return blockers;
}

function renderProfileSnapshot(owner) {
  const contact = ownerContactStatus(owner);
  const fit = acquisitionFit(owner);
  const protectedCount = Number(owner.ownerScopedProtectedIpCount || 0);
  return `
    <section class="profile-snapshot">
      <div class="profile-kpi">
        <span>Acquisition score</span>
        <strong>${Number(owner.acquisitionFitScore ?? owner.sourcingScore ?? 0)}</strong>
      </div>
      <div class="profile-kpi ${fit.className}">
        <span>Fit band</span>
        <strong>${escapeHtml(fit.label)}</strong>
      </div>
      <div class="profile-kpi">
        <span>IP score</span>
        <strong>${Number(owner.sourcingScore || 0)}</strong>
      </div>
      <div class="profile-kpi">
        <span>Owner-scoped protected IP</span>
        <strong>${protectedCount.toLocaleString()}</strong>
      </div>
    </section>
    ${renderContactPanel(owner, contact)}
  `;
}

function renderContactPanel(owner, contact = ownerContactStatus(owner)) {
  const contactAction = contact.action
    ? `<a class="detail-link" href="${escapeHtml(contact.action)}" target="_blank" rel="noopener">${escapeHtml(contact.actionLabel || "Open contact")}</a>`
    : "";
  const supportLinks = [
    owner.primaryContactEmail ? `<a class="detail-button-muted" href="mailto:${escapeHtml(owner.primaryContactEmail)}">Email</a>` : "",
    owner.primaryContactPhone ? `<a class="detail-button-muted" href="tel:${escapeHtml(owner.primaryContactPhone.replace(/[^+\d]/g, ""))}">Call</a>` : "",
    owner.companyWebsite ? `<a class="detail-button-muted" href="${escapeHtml(owner.companyWebsite)}" target="_blank" rel="noopener">Website</a>` : "",
    owner.companyLinkedInUrl ? `<a class="detail-button-muted" href="${escapeHtml(owner.companyLinkedInUrl)}" target="_blank" rel="noopener">LinkedIn</a>` : "",
    owner.companySourceUrl && owner.companySourceUrl !== owner.companyWebsite ? `<a class="detail-button-muted" href="${escapeHtml(owner.companySourceUrl)}" target="_blank" rel="noopener">Profile source</a>` : "",
  ].filter(Boolean).join("");
  return `
    <section class="profile-panel contact-panel">
      <div>
        <p class="eyebrow">Best public contact path</p>
        <h3>${escapeHtml(contact.label)}</h3>
        <p>${escapeHtml(contact.body)}</p>
        <span class="confidence-chip">${escapeHtml(contact.confidence)} confidence</span>
      </div>
      <div class="detail-actions compact">
        ${contactAction}
        ${supportLinks}
      </div>
    </section>
  `;
}

function renderAcquisitionMemo(owner) {
  const contact = ownerContactStatus(owner);
  const blockers = profileBlockers(owner);
  const reasons = Array.isArray(owner.acquisitionFitReasons) ? owner.acquisitionFitReasons.filter(Boolean) : [];
  return `
    <section class="profile-panel">
      <p class="eyebrow">Acquisition memo</p>
      <h3>Why this profile matters</h3>
      <p>${escapeHtml(owner.targetFit || owner.companyDescription || "Needs more company-level research before the profile can be used as an actionable sourcing target.")}</p>
      ${reasons.length ? `
        <h3>Fit drivers</h3>
        <ul class="blocker-list positive">
          ${reasons.map((item) => `<li>${escapeHtml(displayText(item))}</li>`).join("")}
        </ul>
      ` : ""}
      <h3>Recommended next action</h3>
      <p>${escapeHtml(profileNextAction(owner, contact))}</p>
      <h3>Diligence blockers</h3>
      <ul class="blocker-list">
        ${blockers.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    </section>
  `;
}

function titleCaseWord(word) {
  const lower = word.toLowerCase();
  if (["and", "or", "of", "the", "in"].includes(lower)) return lower;
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

function displayCrop(value) {
  let crop = displayText(value, "Unclassified");
  if (crop.length > 90 && crop.includes("[")) crop = crop.split("[")[0].trim();
  if (crop.length > 90) crop = `${crop.slice(0, 87).trim()}...`;
  return crop
    .split(/([-\u2013\u2014/() ])/)
    .map((part) => (/^[A-Za-z]+$/.test(part) ? titleCaseWord(part) : part))
    .join("");
}

function isCpvoRecord(row) {
  return normalize(row.source).includes("cpvo") || normalize(row.sourceKind).includes("cpvo");
}

function isRelevantLatestRecord(row) {
  const crop = normalize(row.crop);
  const cropFocus = normalize(row.cropFocus);
  const combined = normalize([row.crop, row.title, row.notes, row.speciesLatinName].join(" "));
  if (!crop) return false;
  if (crop.includes("ornamental") || combined.includes("ornamental")) return false;
  if (cropFocus.includes("other plant patent")) return false;
  return LATEST_RELEVANT_CROPS.has(crop);
}

function detailValue(row, keys) {
  for (const key of keys) {
    if (row[key]) return displayText(row[key]);
  }
  return "";
}

function patentLookupUrl(row) {
  if (isCpvoRecord(row)) return row.sourceUrl || "https://online.plantvarieties.eu/";
  if (row.sourceUrl) return row.sourceUrl;
  const source = [row.primarySource, row.patentNumber, row.publicationNumber, row.id].filter(Boolean).join(" ");
  const uspp = source.match(/\bUSPP\s*([0-9,]+)\b/i) || source.match(/\bPP0*([0-9]{5,6})\b/i);
  if (uspp) {
    const number = uspp[1].replace(/\D/g, "");
    return `https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/PP${number}`;
  }
  const usppa = source.match(/\bUSPPA\s*([0-9]{11})\b/i);
  if (usppa) {
    return `https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/${usppa[1]}`;
  }
  return "";
}

function patentLookupLabel(row) {
  if (isCpvoRecord(row)) return "Open CPVO Variety Finder";
  if (row.sourceUrl) return "Open verified source";
  const source = [row.primarySource, row.patentNumber, row.publicationNumber, row.id].filter(Boolean).join(" ");
  if (/\bUSPP\s*[0-9,]+\b|\bPP0*[0-9]{5,6}\b/i.test(source)) return "Open patent lookup";
  if (/\bUSPPA\s*[0-9]{11}\b/i.test(source)) return "Open application lookup";
  return "";
}

function sourceLabel(row) {
  if (isCpvoRecord(row)) return row.registerGroup || "CPVO";
  if (row.sourceUrl) return "Verified link";
  if (patentLookupUrl(row)) return "Generated lookup";
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

function listSummary(items, labelKey = "crop", countKey = "count", limit = 3) {
  return (items || [])
    .slice(0, limit)
    .map((item) => `${displayText(item[labelKey])} ${Number(item[countKey] || 0).toLocaleString()}`)
    .join(" | ");
}

function cropListSummary(items, limit = 4) {
  return (items || [])
    .slice(0, limit)
    .map((item) => `${displayCrop(item.crop)} ${Number(item.count || 0).toLocaleString()}`)
    .join(" | ");
}

function ownerSearchText(owner) {
  return normalize([
    owner.ownerName,
    owner.normalizedOwnerName,
    owner.acquisitionFitBand,
    owner.ownershipType,
    owner.ownershipSummary,
    owner.parentCompany,
    owner.headquarters,
    owner.leadershipSummary,
    owner.primaryContactName,
    owner.primaryContactTitle,
    owner.primaryContactEmail,
    owner.primaryContactPhone,
    owner.trademarkOwner,
    owner.trademarkStatus,
    owner.affiliatedCompany,
    owner.affiliationStatus,
    owner.affiliationBasis,
    ...(owner.affiliatedBreeders || []).map((item) => item.name),
    ...(Array.isArray(owner.brandExamples) ? owner.brandExamples : []),
    ...(owner.acquisitionFitReasons || []),
    ...(owner.acquisitionFitBlockers || []),
    ...(owner.topCrops || []).map((item) => item.crop),
    ...(owner.topJurisdictions || []).map((item) => item.jurisdiction),
    ...(owner.topBreeders || []).map((item) => item.name),
    ...(owner.sourcingFlags || []),
  ].join(" "));
}

function ownerSignalSummary(owner) {
  const legal = Number(owner.legalOwnerRecordCount || 0);
  const breeder = Number(owner.breederSignalRecordCount || 0);
  const lineage = Number((owner.ownerRoleCounts || {})["Program lineage"] || 0);
  const parts = [];
  if (legal) parts.push(`${legal.toLocaleString()} confirmed assignee`);
  if (breeder) parts.push(`${breeder.toLocaleString()} breeder signal`);
  if (lineage) parts.push(`${lineage.toLocaleString()} program lineage`);
  return parts.join(" | ") || "Owner signal";
}

function sortOwners(owners) {
  const mode = els.ownerSort?.value || "acquisition";
  const sorters = {
    acquisition: (a, b) => (b.acquisitionFitScore || 0) - (a.acquisitionFitScore || 0) || (b.sourcingScore || 0) - (a.sourcingScore || 0),
    confidence: (a, b) => (b.relevantLegalOwnerRecordCount || 0) - (a.relevantLegalOwnerRecordCount || 0) || (b.relevantIpRecordCount || 0) - (a.relevantIpRecordCount || 0) || (b.legalOwnerRecordCount || 0) - (a.legalOwnerRecordCount || 0) || (b.sourcingScore || 0) - (a.sourcingScore || 0),
    score: (a, b) => (b.sourcingScore || 0) - (a.sourcingScore || 0),
    protected: (a, b) => (b.ownerScopedProtectedIpCount || 0) - (a.ownerScopedProtectedIpCount || 0) || (b.protectedIpCount || 0) - (a.protectedIpCount || 0),
    recent: (a, b) => (b.lastYear || 0) - (a.lastYear || 0),
    cliff: (a, b) => (b.ownerScopedExpirationNext5Years || 0) - (a.ownerScopedExpirationNext5Years || 0),
    velocity: (a, b) => (b.filingVelocity5Year || 0) - (a.filingVelocity5Year || 0),
  };
  return [...owners].sort((a, b) => {
    const primary = (sorters[mode] || sorters.acquisition)(a, b);
    return primary || (b.protectedIpCount || 0) - (a.protectedIpCount || 0) || (b.recordCount || 0) - (a.recordCount || 0);
  });
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
    .map((crop) => `<option value="${escapeHtml(crop)}">${escapeHtml(displayCrop(crop))}</option>`)
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
      row.country,
      row.registerType,
      row.registerLabel,
      row.registerGroup,
      row.speciesClass,
      row.speciesLatinName,
      row.breederReference,
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
  renderSourcingMetrics();
}

function hasCompanySignal(owner) {
  return Boolean(
    owner.isParentRollup
    || owner.companyWebsite
    || owner.companyDescription
    || owner.companyContactUrl
    || owner.companyLinkedInUrl
    || owner.companySourceUrl
    || (!owner.individualOwner && Number(owner.legalOwnerRecordCount || 0) > 0)
  );
}

function hasUnresolvedIdentity(owner) {
  const band = normalize(owner.acquisitionFitBand);
  const status = normalize(owner.webResearchStatus);
  const ownership = normalize(owner.ownershipType);
  return band.includes("identity unresolved")
    || status.includes("identity_unresolved")
    || status.includes("suppress_scoring")
    || ownership.includes("identity unresolved");
}

function isIndependentOwnerSignal(owner) {
  if (!owner.individualOwner || owner.candidateParent || owner.parentCompany || isResolvedAffiliation(owner) || hasUnresolvedIdentity(owner)) return false;
  const ownership = normalize(owner.ownershipType);
  const researchStatus = normalize(owner.webResearchStatus);
  const auditConfidence = normalize(owner.auditConfidence);
  const independentlyOwned = [
    "individual owner",
    "individual breeder-owner",
    "family-owned",
    "founder-owned",
    "owner-breeder",
    "sole proprietor",
    "privately held",
  ].some((term) => ownership.includes(term));
  const ownershipResearched = researchStatus.includes("verified")
    || auditConfidence === "high"
    || auditConfidence === "medium";
  return independentlyOwned && ownershipResearched;
}

function isPrimarySourcingProfile(owner) {
  if (Number(owner.relevantIpRecordCount || 0) <= 0 || hasUnresolvedIdentity(owner)) return false;
  if (isIndependentOwnerSignal(owner)) return true;
  if (owner.individualOwner) return false;
  return hasCompanySignal(owner);
}

function isAffiliationResearchSignal(owner) {
  return Number(owner.relevantIpRecordCount || 0) > 0
    && Boolean(owner.individualOwner || owner.soleNamedBreeder)
    && !isResolvedAffiliation(owner)
    && !isIndependentOwnerSignal(owner)
    && !isPrimarySourcingProfile(owner);
}

function isAcquisitionLead(owner) {
  if (!isPrimarySourcingProfile(owner)) return false;
  const band = normalize(owner.acquisitionFitBand);
  if (band.includes("benchmark") || band.includes("public") || band.includes("low") || band.includes("verify") || band.includes("verification")) return false;
  if (band.includes("high") || band.includes("review")) return true;
  if (Number(owner.acquisitionFitScore || 0) >= 75 && owner.companyWebsite) return true;
  const protectedCount = Number(owner.protectedIpCount || 0);
  return Number(owner.relevantIpRecordCount || 0) > 0
    && protectedCount >= 2
    && protectedCount <= 100
    && Number(owner.recordCount || 0) <= 150
    && !owner.isParentRollup;
}

function renderSourcingMetrics() {
  if (!els.sourcingBrief) return;
  if (!state.ownerProfiles.length) {
    els.sourcingBrief.innerHTML = `<div class="brief-tile"><span>Sourcing brief</span><strong>Loading profiles</strong></div>`;
    return;
  }
  const relevant = state.ownerProfiles.filter((owner) => Number(owner.relevantIpRecordCount || 0) > 0);
  const targets = relevant.filter(isPrimarySourcingProfile);
  const leads = targets.filter(isAcquisitionLead);
  const highFit = targets.filter((owner) => normalize(owner.acquisitionFitBand).includes("high"));
  const independent = targets.filter(isIndependentOwnerSignal);
  const affiliationQueue = relevant.filter(isAffiliationResearchSignal);
  els.sourcingBrief.innerHTML = `
    <div class="brief-tile"><span>Company / owner targets</span><strong>${targets.length.toLocaleString()}</strong></div>
    <div class="brief-tile"><span>Review-or-better leads</span><strong>${leads.length.toLocaleString()}</strong></div>
    <div class="brief-tile"><span>High-fit leads</span><strong>${highFit.length.toLocaleString()}</strong></div>
    <div class="brief-tile"><span>Independent-owner signals</span><strong>${independent.length.toLocaleString()}</strong></div>
    <div class="brief-tile"><span>Affiliation research queue</span><strong>${affiliationQueue.length.toLocaleString()}</strong></div>
  `;
}

function statusClass(row) {
  const status = normalize(row.status);
  if (status.includes("pending") || status.includes("application") || normalize(row.sourceKind).includes("application")) return "pending";
  if (status.includes("registered") || status.includes("approved")) return "registered";
  if (normalize(row.sourceKind).includes("issued")) return "issued";
  return "";
}

function renderLatest(rows) {
  const latest = rows.filter((row) => row.date && isRelevantLatestRecord(row)).slice(0, 6);
  els.latestCount.textContent = `${latest.length} shown`;
  els.latestList.innerHTML = "";
  if (!latest.length) {
    els.latestList.innerHTML = `<p class="empty-state">No relevant fruit, tree nut, or vegetable records match the filters.</p>`;
    return;
  }

  for (const row of latest) {
    const title = displayText(row.cultivar || row.title || row.tradeName, "Untitled record");
    const sourceText = displayText(row.primarySource || row.patentNumber || row.sourceKind, "Source unknown");
    const sourceUrl = patentLookupUrl(row);
    const sourceMarkup = sourceUrl
      ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener">${escapeHtml(sourceText)}</a>`
      : escapeHtml(sourceText);
    const owner = displayText(row.assignee || row.breeders || row.inventors || "");
    const card = document.createElement("article");
    card.className = "latest-card";
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.dataset.recordKey = row.__key;
    card.innerHTML = `
      <div class="meta-line">
        <span class="badge">${escapeHtml(formatDate(row.date))}</span>
        <span class="badge">${escapeHtml(displayCrop(row.crop))}</span>
      </div>
      <h3>${escapeHtml(title)}</h3>
      <div>
        ${sourceMarkup}
        <span class="subtle">${escapeHtml(displayText(row.sourceKind || row.source || ""))}</span>
      </div>
      <div class="meta-line">
        <span class="badge ${statusClass(row)}">${escapeHtml(displayText(row.status || row.sourceKind || "record"))}</span>
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

function renderLiveStatus() {
  if (!els.liveStatus) return;
  if (!state.sourceStatus?.sources?.length) {
    els.liveStatus.innerHTML = `<p class="empty-state">Live source status will appear after the next refresh manifest is built.</p>`;
    return;
  }
  els.liveStatus.innerHTML = `
    <p class="live-strategy">${escapeHtml(state.sourceStatus.strategy || "")}</p>
    <div class="source-list">
      ${state.sourceStatus.sources.map((source) => `
        <div class="source-row live-source-row">
          <span>
            <strong>${escapeHtml(source.name)}</strong>
            <small>${escapeHtml(source.mode)} | ${escapeHtml(source.cadence)}</small>
            <small>Latest record: ${escapeHtml(formatDate(source.latestRecordDate) || "n/a")}</small>
          </span>
          <strong>${Number(source.recordCount || 0).toLocaleString()}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function applyOwnerFilters() {
  if (!els.ownerBody) return;
  const term = normalize(els.ownerSearchInput?.value || "");
  const view = els.ownerView?.value || "targets";
  let owners = term
    ? state.ownerProfiles.filter((owner) => ownerSearchText(owner).includes(term))
    : [...state.ownerProfiles];
  if (view === "targets") {
    owners = owners.filter(isPrimarySourcingProfile);
  } else if (view === "relevant") {
    owners = owners.filter((owner) => Number(owner.relevantIpRecordCount || 0) > 0);
  } else if (view === "acquisition") {
    owners = owners.filter(isAcquisitionLead);
  } else if (view === "independent") {
    owners = owners.filter((owner) => Number(owner.relevantIpRecordCount || 0) > 0 && isIndependentOwnerSignal(owner));
  } else if (view === "affiliated") {
    owners = owners.filter((owner) => Number(owner.relevantIpRecordCount || 0) > 0 && isResolvedAffiliation(owner));
  } else if (view === "individuals") {
    owners = owners.filter(isAffiliationResearchSignal);
  } else if (view === "legal") {
    owners = owners.filter((owner) => Number(owner.legalOwnerRecordCount || 0) > 0);
  } else if (view === "succession") {
    owners = owners.filter((owner) => owner.individualOwner || owner.soleNamedBreeder || (owner.sourcingFlags || []).includes("Dormant portfolio"));
  } else if (view === "cliff") {
    owners = owners.filter((owner) => Number(owner.ownerScopedExpirationNext5Years || 0) > 0);
  }
  state.filteredOwners = sortOwners(owners);
  renderOwners();
}

function renderOwners() {
  if (!els.ownerBody) return;
  const owners = state.filteredOwners;
  const shown = owners.slice(0, 250);
  els.ownerCount.textContent = `${owners.length.toLocaleString()} profiles`;

  els.ownerBody.innerHTML = "";
  if (!shown.length) {
    els.ownerBody.innerHTML = `<tr><td colspan="8"><p class="empty-state">No owner profiles match the search.</p></td></tr>`;
    return;
  }

  shown.forEach((owner, index) => {
    const row = document.createElement("tr");
    row.dataset.ownerKey = owner.__key;
    row.tabIndex = 0;
    row.setAttribute("role", "button");
    const flags = (owner.sourcingFlags || []).slice(0, 3).map((flag) => `<span class="badge">${escapeHtml(flag)}</span>`).join("");
    const fitScore = Number(owner.acquisitionFitScore ?? owner.sourcingScore ?? 0);
    const fitBand = displayText(owner.acquisitionFitBand || "Fit score");
    const affiliationSummary = owner.affiliatedCompany && owner.affiliationStatus !== "unresolved"
      ? `Affiliated with ${displayText(owner.affiliatedCompany)} | ${displayAuditValue(owner.affiliationConfidence || "unverified")} confidence`
      : ownerSignalSummary(owner);
    row.innerHTML = `
      <td class="row-number">${(index + 1).toLocaleString()}</td>
      <td>
        <strong class="score-pill">${fitScore}</strong>
        <span class="subtle">${escapeHtml(fitBand)}</span>
        <span class="subtle">IP ${Number(owner.sourcingScore || 0)}</span>
      </td>
      <td>
        <strong class="record-title">${escapeHtml(displayText(owner.ownerName, "Unknown owner"))}</strong>
        <span class="subtle">${escapeHtml(affiliationSummary)}</span>
      </td>
      <td>
        <strong>${Number(owner.recordCount || 0).toLocaleString()} public records</strong>
        <span class="subtle">${Number(owner.distinctCultivarCount || 0).toLocaleString()} variety labels | ${Number(owner.relevantIpRecordCount || 0).toLocaleString()} relevant signals | ${Number(owner.protectedIpCount || 0).toLocaleString()} protected-right observations | ${Number(owner.ownerScopedRecordCount || 0).toLocaleString()} confirmed owner records</span>
      </td>
      <td>
        ${escapeHtml(cropListSummary(owner.topCrops, 4) || "--")}
      </td>
      <td>
        ${escapeHtml(listSummary(owner.topJurisdictions, "jurisdiction", "count", 4) || "No jurisdictions")}
      </td>
      <td>
        <strong>${escapeHtml(yearRange(owner.firstYear, owner.lastYear))}</strong>
        <span class="subtle">${Number(owner.recordsLast5Years || 0).toLocaleString()} records last 5 yrs | ${Number(owner.filingVelocity5Year || 0).toLocaleString()} / yr</span>
      </td>
      <td>
        <strong>${Number(owner.ownerScopedExpirationNext5Years || 0).toLocaleString()} owner-scoped expiries in 5 yrs</strong>
        <span class="flag-list">${flags || '<span class="subtle">No major flags</span>'}</span>
      </td>
    `;
    els.ownerBody.appendChild(row);
  });
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
  }).reverse();
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
    label: displayCrop(label),
    value,
    note: rows.length ? `${Math.round((value / rows.length) * 100)}% share` : "",
  }));
  renderBars(els.cropChart, annotatedCrops, maxCrop, "No crop data matches the filters.");
  els.cropCount.textContent = `${cropEntries.length} crops shown`;
  const topCrop = cropEntries[0] || ["--", 0];
  const topThree = cropEntries.slice(0, 3).reduce((sum, entry) => sum + entry[1], 0);
  els.cropInsight.innerHTML = `
    <div class="insight-pill"><span>Top crop</span><strong>${escapeHtml(displayCrop(topCrop[0]))} · ${topCrop[1].toLocaleString()}</strong></div>
    <div class="insight-pill"><span>Top 3 share</span><strong>${rows.length ? Math.round((topThree / rows.length) * 100) : 0}%</strong></div>
    <div class="insight-pill"><span>Crop breadth</span><strong>${Object.keys(countBy(rows, (row) => row.crop || "Unclassified")).length.toLocaleString()} crops</strong></div>
  `;
}

function renderTable(rows) {
  els.rowCount.textContent = `${rows.length.toLocaleString()} matching rows`;
  els.recordsBody.innerHTML = "";

  rows.slice(0, 500).forEach((row, index) => {
    const title = displayText(row.cultivar || row.title || row.tradeName, "Untitled record");
    const sourceUrl = patentLookupUrl(row);
    const link = sourceUrl
      ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener">${escapeHtml(displayText(row.primarySource || row.patentNumber, "Source unknown"))}</a>`
      : `${escapeHtml(displayText(row.primarySource || row.patentNumber, "Source unknown"))}`;
    const subtitle = [row.tradeName, row.title && row.title !== title ? row.title : ""].filter(Boolean).map((value) => displayText(value)).join(" | ");
    const owner = displayText(row.assignee || row.breeders || row.inventors || "");
    const status = displayText(row.status || row.sourceKind || "");
    const tr = document.createElement("tr");
    tr.dataset.recordKey = row.__key;
    tr.innerHTML = `
      <td class="row-number">${(index + 1).toLocaleString()}</td>
      <td>${formatDate(row.date)}</td>
      <td><span class="badge">${escapeHtml(displayCrop(row.crop))}</span></td>
      <td><strong class="record-title">${escapeHtml(title)}</strong>${subtitle ? `<span class="subtle">${escapeHtml(subtitle)}</span>` : ""}</td>
      <td>${link}<span class="subtle">${escapeHtml(displayText(row.sourceKind || row.source || ""))}</span></td>
      <td><span class="badge ${statusClass(row)}">${escapeHtml(status)}</span></td>
      <td>${escapeHtml(owner)}</td>
    `;
    els.recordsBody.appendChild(tr);
  });
}

function renderDetailItem(label, value) {
  if (!value) return "";
  return `
    <div class="detail-item">
      <span>${escapeHtml(label)}</span>
      <p>${escapeHtml(displayText(value))}</p>
    </div>
  `;
}

function renderMiniList(label, items, keyName = "name") {
  if (!items || !items.length) return "";
  const text = items
    .slice(0, 8)
    .map((item) => `${item[keyName] || item.crop || item.jurisdiction}: ${Number(item.count || 0).toLocaleString()}`)
    .join(" | ");
  return renderDetailItem(label, text);
}

function renderProfileBarChart(title, items, labelKey = "year", countKey = "count", limit = 12, emptyText = "No dated records available.") {
  const values = (items || []).slice(-limit);
  if (!values.length) {
    return `
      <div class="profile-chart">
        <h3>${escapeHtml(title)}</h3>
        <p class="subtle">${escapeHtml(emptyText)}</p>
      </div>
    `;
  }
  const max = Math.max(...values.map((item) => Number(item[countKey] || 0)), 1);
  return `
    <div class="profile-chart">
      <h3>${escapeHtml(title)}</h3>
      <div class="profile-bars">
        ${values.map((item) => {
          const value = Number(item[countKey] || 0);
          const height = Math.max(8, Math.round((value / max) * 72));
          return `
            <div class="profile-bar-item" title="${escapeHtml(String(item[labelKey]))}: ${value.toLocaleString()}">
              <span class="profile-bar-value">${value.toLocaleString()}</span>
              <span class="profile-bar" style="height:${height}px"></span>
              <span class="profile-bar-label">${escapeHtml(String(item[labelKey]))}</span>
            </div>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function futureExpirationItems(owner) {
  const currentYear = new Date().getFullYear();
  return (owner.ownerScopedExpirationSchedule || [])
    .filter((item) => Number(item.year) >= currentYear - 1)
    .slice(0, 14);
}

function openRecordDrawer(recordKey) {
  const row = state.byKey.get(recordKey);
  if (!row) return;
  state.lastFocus = document.activeElement;
  els.drawer.classList.remove("profile-drawer");

  const title = displayText(row.cultivar || row.title || row.tradeName, "Patent record");
  const sourceText = displayText(row.primarySource || row.patentNumber || row.publicationNumber || row.sourceKind, "Source unknown");
  const owner = detailValue(row, ["assignee", "breeders", "inventors"]);
  const matchedCompanies = companyProfilesForText([
    row.assignee,
    row.breeders,
    row.inventors,
    row.title,
    row.cultivar,
    row.tradeName,
  ].join(" "));
  const isCpvo = isCpvoRecord(row);
  const lookupUrl = patentLookupUrl(row);
  const gazetteAction = row.gazetteUrl
    ? `<a class="detail-button-muted" href="${escapeHtml(row.gazetteUrl)}" target="_blank" rel="noopener">Open Gazette notice</a>`
    : "";
  const sourceAction = lookupUrl
    ? `<a class="detail-link" href="${escapeHtml(lookupUrl)}" target="_blank" rel="noopener">${escapeHtml(patentLookupLabel(row))}</a>`
    : `<span class="detail-button-muted">No direct source link yet</span>`;

  els.drawerEyebrow.textContent = "Record detail";
  els.drawerTitle.textContent = title;
  els.drawerBody.innerHTML = `
    <div class="detail-actions">
      ${sourceAction}
      ${gazetteAction}
      <span class="badge ${row.sourceUrl ? "verified" : "baseline"}">${escapeHtml(sourceLabel(row))}</span>
      <span class="badge ${statusClass(row)}">${escapeHtml(row.status || row.sourceKind || "record")}</span>
    </div>
    <div class="detail-grid">
      ${renderDetailItem("Date", formatDate(row.date))}
      ${renderDetailItem("Crop", displayCrop(row.crop))}
      ${renderDetailItem("Cultivar / denomination", row.cultivar)}
      ${renderDetailItem("Trade name", row.tradeName)}
      ${renderDetailItem("Title", row.title)}
      ${renderDetailItem("Primary source", sourceText)}
      ${renderDetailItem("Source type", row.sourceKind || row.source)}
      ${renderDetailItem("Register group", row.registerGroup)}
      ${renderDetailItem("Register type", row.registerType ? `${row.registerType} - ${row.registerLabel || ""}` : "")}
      ${renderDetailItem("Country", row.country)}
      ${renderDetailItem("Species class", row.speciesClass)}
      ${renderDetailItem("Species latin name", row.speciesLatinName)}
      ${renderDetailItem("Assignee / breeder", owner)}
      ${renderDetailItem("Breeder reference", row.breederReference)}
      ${renderDetailItem("Inventors", row.inventors && row.inventors !== owner ? row.inventors : "")}
      ${renderDetailItem("Application number", row.applicationNumber)}
      ${renderDetailItem("Application date", row.applicationDate || row.filedDateText)}
      ${renderDetailItem("Grant / registration date", row.grantDate)}
      ${renderDetailItem("Denomination status", row.denominationStatus)}
      ${renderDetailItem("List", row.list)}
      ${renderDetailItem("Notes", row.notes)}
    </div>
    ${renderCompanyCards(matchedCompanies)}
    <p class="detail-note">
      ${isCpvo
        ? "This record comes from the CPVO Variety Finder export. The button above opens the CPVO search site; the row-specific details are stored in the dashboard data from the Excel export."
        : row.sourceUrl
        ? "This record has a verified source link from the dashboard data. The button above opens the patent or source page in a new tab."
        : lookupUrl
          ? "This record does not yet have a verified dashboard source URL, so the button uses a generated public patent lookup link. We can replace these with verified USPTO Gazette links as the dataset is enriched."
          : "This record is still based on the baseline workbook or another non-linked source. We can add source verification as we enrich the dataset."}
    </p>
  `;
  els.drawerBackdrop.hidden = false;
  els.drawer.classList.add("open");
  els.drawer.setAttribute("aria-hidden", "false");
  els.drawerClose.focus();
}

function openOwnerDrawer(ownerKey) {
  const owner = state.ownerByKey.get(ownerKey);
  if (!owner) return;
  state.lastFocus = document.activeElement;
  const flags = (owner.sourcingFlags || []).map((flag) => `<span class="badge">${escapeHtml(flag)}</span>`).join("");
  const ownerNewsLinks = renderNewsLinks({ newsLinks: owner.companyNewsLinks || [] });
  const isCompanyProfile = Boolean(owner.companyWebsite || owner.companyDescription || owner.companyContactUrl);
  els.drawer.classList.add("profile-drawer");
  els.drawerEyebrow.textContent = isCompanyProfile ? "Company profile" : "Owner / breeder profile";
  els.drawerTitle.textContent = displayText(owner.ownerName, "Owner profile");
  els.drawerBody.innerHTML = `
    ${renderProfileSnapshot(owner)}
    ${owner.companyDescription ? `<p class="company-description">${escapeHtml(owner.companyDescription)}</p>` : ""}
    ${renderAcquisitionMemo(owner)}
    <div class="detail-actions">
      ${flags || '<span class="badge baseline">No major flags</span>'}
    </div>
    ${ownerNewsLinks}
    ${renderOwnerAudit(owner)}
    ${renderAffiliationEvidence(owner)}
    <div class="detail-grid">
      ${renderDetailItem("Portfolio observations", `${Number(owner.recordCount || 0).toLocaleString()} public records | ${Number(owner.distinctCultivarCount || 0).toLocaleString()} distinct variety labels | ${Number(owner.protectedIpCount || 0).toLocaleString()} protected-right observations`)}
      ${renderDetailItem("Relevant crop exposure", `${Number(owner.relevantIpRecordCount || 0).toLocaleString()} fruit/nut/vegetable records | ${Number(owner.relevantLegalOwnerRecordCount || 0).toLocaleString()} confirmed assignee records`)}
      ${renderDetailItem("Owner-scoped rights", `${Number(owner.ownerScopedRecordCount || 0).toLocaleString()} confirmed owner records | ${Number(owner.ownerScopedProtectedIpCount || 0).toLocaleString()} protected | ${Number(owner.ownerScopedActiveProtectionCount || 0).toLocaleString()} active`)}
      ${renderDetailItem("US / CPVO protected", `${Number(owner.usPlantPatentCount || 0).toLocaleString()} US plant patents | ${Number(owner.cpvoPbrCount || 0).toLocaleString()} CPVO PBR`)}
      ${renderDetailItem("Filing years", `${yearRange(owner.firstYear, owner.lastYear)} | ${Number(owner.recordsLast5Years || 0).toLocaleString()} records last 5 years`)}
      ${renderDetailItem("Owner-scoped expiration curve", `${Number(owner.ownerScopedExpirationNext1Year || 0).toLocaleString()} in 1 yr | ${Number(owner.ownerScopedExpirationNext3Years || 0).toLocaleString()} in 3 yrs | ${Number(owner.ownerScopedExpirationNext5Years || 0).toLocaleString()} in 5 yrs | ${Number(owner.ownerScopedExpiredProtectionCount || 0).toLocaleString()} expired`)}
      ${renderDetailItem("Signal confidence", ownerSignalSummary(owner))}
      ${renderDetailItem("Rollup includes", (owner.rollupChildren || []).join(" | "))}
      ${renderDetailItem("Owner signal", Object.entries(owner.ownerRoleCounts || {}).map(([key, value]) => `${key}: ${value}`).join(" | "))}
      ${renderMiniList("Top crops", owner.topCrops, "crop")}
      ${renderMiniList("Jurisdictions", owner.topJurisdictions, "jurisdiction")}
      ${renderMiniList("Named breeders", owner.topBreeders, "name")}
    </div>
    <div class="profile-chart-grid">
      ${renderProfileBarChart("Owner-scoped filing activity", owner.ownerScopedAnnualCounts || [], "year", "count", 12, "No record-specific owner filings captured.")}
      ${renderProfileBarChart("Owner-scoped expiration cliff", futureExpirationItems(owner), "year", "count", 14, "No record-specific owner expirations captured.")}
    </div>
    <p class="detail-note">
      Portfolio observations are sourcing signals rather than a legal title schedule. Owner-scoped figures use record-specific assignee evidence. CPVO profiles currently use breeder names from the Variety Finder export because holder/applicant fields are not in the downloaded workbook.
    </p>
  `;
  els.drawerBackdrop.hidden = false;
  els.drawer.classList.add("open");
  els.drawer.setAttribute("aria-hidden", "false");
  els.drawerClose.focus();
}

function closeRecordDrawer() {
  els.drawer.classList.remove("open");
  els.drawer.setAttribute("aria-hidden", "true");
  els.drawerBackdrop.hidden = true;
  if (state.lastFocus && typeof state.lastFocus.focus === "function") {
    state.lastFocus.focus();
  }
}

function setActiveTab(tabName) {
  els.tabButtons.forEach((button) => {
    const isActive = button.dataset.tabTarget === tabName;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
    button.tabIndex = isActive ? 0 : -1;
  });
  els.viewPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.viewPanel === tabName);
    panel.hidden = panel.dataset.viewPanel !== tabName;
  });
}

function render() {
  renderMetrics(state.filtered);
  renderLatest(state.filtered);
  renderSources(state.filtered);
  renderLiveStatus();
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

async function loadOwnerProfiles() {
  if (els.ownerCount) els.ownerCount.textContent = "Loading owners...";
  try {
    const response = await fetch("data/owner_profiles.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`Could not load owner profiles: ${response.status}`);
    const ownerProfilesPayload = await response.json();
    const ownerRows = ownerProfilesPayload.owners || [];
    const ownerFields = ownerProfilesPayload.ownerFields || [];
    const owners = ownerFields.length
      ? ownerRows.map((row) => Object.fromEntries(ownerFields.map((field, index) => [field, row[index]])))
      : ownerRows;
    state.ownerProfiles = owners
      .map((owner, index) => ({ ...owner, __key: `${index}-${owner.id || owner.normalizedOwnerName || "owner"}` }));
    state.ownerByKey = new Map(state.ownerProfiles.map((owner) => [owner.__key, owner]));
    applyOwnerFilters();
    renderSourcingMetrics();
  } catch (error) {
    if (els.ownerCount) els.ownerCount.textContent = "Owner profiles unavailable";
    if (els.ownerBody) els.ownerBody.innerHTML = `<tr><td colspan="6"><p class="empty-state">Owner profiles could not be loaded.</p></td></tr>`;
    console.error(error);
  }
}

async function init() {
  const [response, cpvoVarietiesResponse, companyProfilesResponse, sourceStatusResponse] = await Promise.all([
    fetch("data/plant_patents.json", { cache: "no-store" }),
    fetch("data/cpvo_varieties.json", { cache: "no-store" }).catch(() => null),
    fetch("config/company_profiles.json", { cache: "no-store" }).catch(() => null),
    fetch("data/source_status.json", { cache: "no-store" }).catch(() => null),
  ]);
  if (!response.ok) throw new Error(`Could not load data: ${response.status}`);
  const payload = await response.json();
  if (companyProfilesResponse && companyProfilesResponse.ok) {
    state.companyProfiles = await companyProfilesResponse.json();
  }
  if (sourceStatusResponse && sourceStatusResponse.ok) {
    state.sourceStatus = await sourceStatusResponse.json();
  }
  if (cpvoVarietiesResponse && cpvoVarietiesResponse.ok) {
    const cpvoVarietiesPayload = await cpvoVarietiesResponse.json();
    state.cpvoVarieties = cpvoVarietiesPayload.records || [];
  }
  state.records = [...(payload.records || []), ...state.cpvoVarieties]
    .map((row, index) => ({ ...row, __key: `${index}-${row.id || row.primarySource || row.cultivar || "record"}` }))
    .sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
  state.byKey = new Map(state.records.map((row) => [row.__key, row]));
  state.filtered = [...state.records];
  const generatedAtValue = state.sourceStatus?.generatedAt || payload.metadata?.generatedAt;
  const generatedAt = generatedAtValue ? new Date(generatedAtValue) : null;
  els.lastRefresh.textContent = generatedAt && !Number.isNaN(generatedAt.getTime())
    ? `Dashboard refreshed ${generatedAt.toLocaleString()}`
    : "Data loaded";
  populateFilters();
  render();
  setActiveTab("overview");
  loadOwnerProfiles();
}

const debouncedApplyFilters = debounce(applyFilters);
const debouncedApplyOwnerFilters = debounce(applyOwnerFilters);
for (const input of [els.searchInput, els.cropFilter, els.sourceFilter, els.fromDate, els.toDate]) {
  input.addEventListener("input", debouncedApplyFilters);
}
els.tabButtons.forEach((button) => {
  button.addEventListener("click", () => setActiveTab(button.dataset.tabTarget));
  button.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const buttons = [...els.tabButtons];
    const currentIndex = buttons.indexOf(button);
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? buttons.length - 1
        : event.key === "ArrowRight"
          ? (currentIndex + 1) % buttons.length
          : (currentIndex - 1 + buttons.length) % buttons.length;
    buttons[nextIndex].focus();
    setActiveTab(buttons[nextIndex].dataset.tabTarget);
  });
});
if (els.ownerSearchInput) els.ownerSearchInput.addEventListener("input", debouncedApplyOwnerFilters);
if (els.ownerView) els.ownerView.addEventListener("input", applyOwnerFilters);
if (els.ownerSort) els.ownerSort.addEventListener("input", applyOwnerFilters);
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
if (els.ownerBody) {
  els.ownerBody.addEventListener("click", (event) => {
    const row = event.target.closest("[data-owner-key]");
    if (!row || event.target.closest("a")) return;
    openOwnerDrawer(row.dataset.ownerKey);
  });
  els.ownerBody.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const row = event.target.closest("[data-owner-key]");
    if (!row) return;
    event.preventDefault();
    openOwnerDrawer(row.dataset.ownerKey);
  });
}
els.drawerClose.addEventListener("click", closeRecordDrawer);
els.drawerBackdrop.addEventListener("click", closeRecordDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeRecordDrawer();
});

init().catch((error) => {
  els.lastRefresh.textContent = "Could not load dashboard data";
  console.error(error);
});
