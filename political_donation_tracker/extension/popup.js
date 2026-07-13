const API_BASE = "http://127.0.0.1:8000";

const els = {
  query: document.getElementById("query"),
  searchBtn: document.getElementById("searchBtn"),
  searchLabel: document.getElementById("searchLabel"),
  modePoliticians: document.getElementById("modePoliticians"),
  modePacs: document.getElementById("modePacs"),
  results: document.getElementById("results"),
  profile: document.getElementById("profile"),
  candidatePhoto: document.getElementById("candidatePhoto"),
  candidateName: document.getElementById("candidateName"),
  candidateMeta: document.getElementById("candidateMeta"),
  cycleSelect: document.getElementById("cycleSelect"),
  summaryHeading: document.getElementById("summaryHeading"),
  llmSummary: document.getElementById("llmSummary"),
  totals: document.getElementById("totals"),
  candidateControls: document.getElementById("candidateControls"),
  donorType: document.getElementById("donorType"),
  sortBy: document.getElementById("sortBy"),
  partySection: document.getElementById("partySection"),
  partyBars: document.getElementById("partyBars"),
  partyHistoryBody: document.getElementById("partyHistoryBody"),
  historyBtn: document.getElementById("historyBtn"),
  donorSection: document.getElementById("donorSection"),
  donorHeading: document.getElementById("donorHeading"),
  donorHead: document.getElementById("donorHead"),
  donorBody: document.getElementById("donorBody"),
  orgSection: document.getElementById("orgSection"),
  orgBody: document.getElementById("orgBody"),
  status: document.getElementById("status"),
};

let searchMode = "politicians";
let selected = null;
let profileCache = null;

els.searchBtn.addEventListener("click", () => search({ selectFirst: false }));
els.query.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    search({ selectFirst: true });
  }
});
els.cycleSelect.addEventListener("change", () => loadProfile());
els.donorType.addEventListener("change", () => loadProfile());
els.sortBy.addEventListener("change", () => {
  if (searchMode === "politicians") renderDonors();
  else renderPacGifts();
});
els.modePoliticians.addEventListener("click", () => setMode("politicians"));
els.modePacs.addEventListener("click", () => setMode("pacs"));
els.historyBtn.addEventListener("click", () => loadProfile({ includeHistory: true }));

function setMode(mode) {
  searchMode = mode;
  els.modePoliticians.classList.toggle("active", mode === "politicians");
  els.modePacs.classList.toggle("active", mode === "pacs");
  els.searchLabel.textContent =
    mode === "politicians" ? "Search a politician" : "Search a PAC";
  els.query.placeholder =
    mode === "politicians" ? "e.g. Nancy Pelosi" : "e.g. EMILY's List";
  els.results.hidden = true;
  els.results.innerHTML = "";
  els.profile.hidden = true;
  selected = null;
  profileCache = null;
  setStatus("");
}

async function search({ selectFirst = false } = {}) {
  const q = els.query.value.trim();
  if (q.length < 2) {
    setStatus("Enter at least 2 characters.");
    return;
  }

  setStatus(searchMode === "politicians" ? "Searching politicians…" : "Searching PACs…");
  try {
    const path =
      searchMode === "politicians"
        ? `/candidates/search?q=${encodeURIComponent(q)}`
        : `/pacs/search?q=${encodeURIComponent(q)}`;
    const rows = await api(path);
    els.results.hidden = false;
    els.results.innerHTML = "";
    if (!rows.length) {
      setStatus("No results found.");
      return;
    }

    rows.forEach((row) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.appendChild(createPhotoNode(row, "sm"));
      const label = document.createElement("span");
      label.className = "result-label";
      if (searchMode === "politicians") {
        label.innerHTML = `<span>${escapeHtml(displayName(row.name))}</span>
          <small>${escapeHtml(formatCandidateMeta(row))}</small>`;
        btn.addEventListener("click", () => selectCandidate(row));
      } else {
        label.innerHTML = `<span>${escapeHtml(titleish(row.name))}</span>
          <small>${escapeHtml(formatPacMeta(row))}</small>`;
        btn.addEventListener("click", () => selectPac(row));
      }
      btn.appendChild(label);
      li.appendChild(btn);
      els.results.appendChild(li);
    });

    setStatus("");
    if (selectFirst) {
      if (searchMode === "politicians") await selectCandidate(rows[0]);
      else await selectPac(rows[0]);
    }
  } catch (error) {
    setStatus(error.message);
  }
}

async function selectCandidate(candidate) {
  selected = { kind: "candidate", ...candidate };
  els.results.hidden = true;
  els.profile.hidden = false;
  els.candidateControls.hidden = false;
  els.partySection.hidden = true;
  els.historyBtn.hidden = true;
  els.orgSection.hidden = false;
  els.summaryHeading.textContent = "Financial summary";
  els.donorHeading.textContent = "Top donors";
  els.donorHead.innerHTML = `<tr><th>Name</th><th>Type</th><th>Amount</th><th>#</th></tr>`;
  els.candidateName.textContent = displayName(candidate.name);
  els.candidateMeta.textContent = formatCandidateMeta(candidate);
  setProfilePhoto(candidate);
  fillCycles(candidate.cycles);
  await loadProfile();
}

async function selectPac(pac) {
  selected = { kind: "pac", ...pac };
  els.results.hidden = true;
  els.profile.hidden = false;
  els.candidateControls.hidden = true;
  els.partySection.hidden = false;
  els.historyBtn.hidden = false;
  els.orgSection.hidden = true;
  els.summaryHeading.textContent = "Giving summary";
  els.donorHeading.textContent = "Donations to politicians";
  els.donorHead.innerHTML = `<tr><th>Recipient</th><th>Party</th><th>Amount</th><th>#</th></tr>`;
  els.candidateName.textContent = titleish(pac.name);
  els.candidateMeta.textContent = formatPacMeta(pac);
  setProfilePhoto(pac);
  fillCycles(pac.cycles);
  await loadProfile();
}

function fillCycles(cycles) {
  const sorted = [...(cycles || [])].sort((a, b) => b - a);
  els.cycleSelect.innerHTML = sorted
    .map((cycle) => `<option value="${cycle}">${cycle}</option>`)
    .join("");
  if (sorted.length) els.cycleSelect.value = String(sorted[0]);
}

async function loadProfile({ includeHistory = false } = {}) {
  if (!selected) return;
  const cycle = els.cycleSelect.value;
  els.llmSummary.textContent = "Generating short summary…";
  setStatus("Loading donation data…");

  try {
    if (selected.kind === "pac") {
      const profile = await api(
        `/pacs/${selected.committee_id}/profile?cycle=${cycle}&limit=15&include_history=${includeHistory}`
      );
      profileCache = profile;
      if (profile.pac) {
        selected = { kind: "pac", ...selected, ...profile.pac };
        setProfilePhoto(selected);
      }
      els.llmSummary.textContent = profile.llm_summary || "No summary available.";
      renderPacTotals(profile.totals);
      renderParty(profile.party_breakdown, profile.party_history || []);
      els.historyBtn.hidden = includeHistory || (profile.party_history || []).length > 1;
      renderPacGifts();
      setStatus("");
      return;
    }

    const donorType = els.donorType.value;
    const profile = await api(
      `/candidates/${selected.candidate_id}/profile?cycle=${cycle}&donor_type=${donorType}`
    );
    profileCache = profile;
    if (profile.candidate) {
      selected = { kind: "candidate", ...selected, ...profile.candidate };
      setProfilePhoto(selected);
    }
    els.llmSummary.textContent = profile.llm_summary || "No summary available.";
    renderTotals(profile.totals);
    renderDonors();
    renderOrgs(profile.top_organizations || []);
    setStatus("");
  } catch (error) {
    setStatus(error.message);
    els.llmSummary.textContent = "Could not load summary.";
  }
}

function renderPacTotals(totals) {
  if (!totals) {
    els.totals.innerHTML = "<p class='hint'>No totals for this cycle.</p>";
    return;
  }
  const stats = [
    ["Receipts", totals.receipts],
    ["Disbursements", totals.disbursements],
    ["To candidates/committees", totals.fed_candidate_committee_contributions],
    ["Cash on hand", totals.cash_on_hand],
  ];
  els.totals.innerHTML = stats
    .map(
      ([label, value]) =>
        `<div class="stat"><span>${label}</span><strong>${money(value)}</strong></div>`
    )
    .join("");
}

function renderParty(current, history) {
  const breakdown = current || { democratic: 0, republican: 0, other: 0, unknown: 0 };
  const dem = breakdown.democratic || 0;
  const rep = breakdown.republican || 0;
  const other = (breakdown.other || 0) + (breakdown.unknown || 0);
  const max = Math.max(dem, rep, other, 1);

  els.partyBars.innerHTML = [
    ["Democratic", dem, "dem"],
    ["Republican", rep, "rep"],
    ["Other / unk.", other, "other"],
  ]
    .map(
      ([label, value, cls]) => `<div class="party-row">
        <span>${label}</span>
        <div class="party-track"><div class="party-fill ${cls}" style="width:${(value / max) * 100}%"></div></div>
        <strong>${money(value)}</strong>
      </div>`
    )
    .join("");

  const rows = (history || []).length ? history : current ? [current] : [];
  els.partyHistoryBody.innerHTML = rows.length
    ? rows
        .map(
          (row) => `<tr>
            <td>${row.cycle}</td>
            <td class="amount">${money(row.democratic)}</td>
            <td class="amount">${money(row.republican)}</td>
            <td class="amount">${money((row.other || 0) + (row.unknown || 0))}</td>
          </tr>`
        )
        .join("")
    : `<tr><td colspan="4">No party history available.</td></tr>`;
}

function renderPacGifts() {
  if (!profileCache) return;
  let rows = [...(profileCache.politician_gifts || [])];
  const sortBy = els.sortBy?.value || "total_desc";
  rows.sort((a, b) => {
    if (sortBy === "total_asc") return a.total - b.total;
    if (sortBy === "name_asc") return a.name.localeCompare(b.name);
    return b.total - a.total;
  });

  els.donorBody.innerHTML = rows.length
    ? rows
        .map((row) => {
          const partyClass =
            row.party === "DEM" || row.party === "DFL"
              ? "dem"
              : row.party === "REP"
                ? "rep"
                : "";
          return `<tr>
            <td>${escapeHtml(row.name)}${
              row.office ? `<div class="hint">${escapeHtml(row.office)}</div>` : ""
            }</td>
            <td><span class="badge ${partyClass}">${escapeHtml(row.party || "—")}</span></td>
            <td class="amount">${money(row.total)}</td>
            <td>${row.count ?? "—"}</td>
          </tr>`;
        })
        .join("")
    : `<tr><td colspan="4">No politician gifts found for this cycle.</td></tr>`;
}

function setProfilePhoto(entity) {
  const url = entity?.photo_url;
  if (url) {
    els.candidatePhoto.hidden = false;
    els.candidatePhoto.referrerPolicy = "no-referrer";
    els.candidatePhoto.src = url;
    els.candidatePhoto.alt = displayName(entity.name || "") || titleish(entity.name || "");
  } else {
    els.candidatePhoto.hidden = true;
    els.candidatePhoto.removeAttribute("src");
  }
}

function createPhotoNode(entity, size) {
  if (entity.photo_url) {
    const img = document.createElement("img");
    img.className = size === "lg" ? "photo photo-lg" : "photo";
    img.src = entity.photo_url;
    img.alt = "";
    img.loading = "lazy";
    img.referrerPolicy = "no-referrer";
    img.onerror = () => {
      img.replaceWith(createInitialsFallback(entity));
    };
    return img;
  }
  return createInitialsFallback(entity);
}

function createInitialsFallback(entity) {
  const fallback = document.createElement("span");
  fallback.className = "photo-fallback";
  const label = entity.name?.includes(",")
    ? displayName(entity.name)
    : titleish(entity.name || "?");
  fallback.textContent = initials(label);
  return fallback;
}

function initials(name) {
  const parts = name.split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function renderTotals(totals) {
  if (!totals) {
    els.totals.innerHTML = "<p class='hint'>No totals for this cycle.</p>";
    return;
  }
  const stats = [
    ["Contributions", totals.contributions],
    ["Individuals", totals.individual_contributions],
    ["PAC / committees", totals.other_political_committee_contributions],
    ["Cash on hand", totals.cash_on_hand],
    ["Disbursements", totals.disbursements],
    ["Party committees", totals.political_party_committee_contributions],
  ];
  els.totals.innerHTML = stats
    .map(
      ([label, value]) =>
        `<div class="stat"><span>${label}</span><strong>${money(value)}</strong></div>`
    )
    .join("");
}

function renderDonors() {
  if (!profileCache) return;
  const type = els.donorType.value;
  els.donorHeading.textContent =
    type === "organization"
      ? "Top organizations"
      : type === "superpac"
        ? "Super PAC independent expenditures"
        : "Top donors";

  let rows = [...(profileCache.top_donors || [])];
  const sortBy = els.sortBy.value;
  rows.sort((a, b) => {
    if (sortBy === "total_asc") return a.total - b.total;
    if (sortBy === "name_asc") return a.name.localeCompare(b.name);
    return b.total - a.total;
  });

  els.donorBody.innerHTML = rows.length
    ? rows
        .map(
          (row) => `<tr>
            <td>${escapeHtml(row.name)}${row.detail ? `<div class="hint">${escapeHtml(row.detail)}</div>` : ""}</td>
            <td><span class="badge">${escapeHtml(row.donor_type)}</span></td>
            <td class="amount">${money(row.total)}</td>
            <td>${row.count ?? "—"}</td>
          </tr>`
        )
        .join("")
    : `<tr><td colspan="4">No donors in this view.</td></tr>`;
}

function renderOrgs(rows) {
  const sorted = [...rows].sort((a, b) => b.total - a.total);
  els.orgBody.innerHTML = sorted.length
    ? sorted
        .map(
          (row) => `<tr>
            <td>${escapeHtml(row.name)}</td>
            <td class="amount">${money(row.total)}</td>
            <td>${row.count ?? "—"}</td>
          </tr>`
        )
        .join("")
    : `<tr><td colspan="3">No organization totals found.</td></tr>`;
}

async function api(path) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`);
  } catch {
    throw new Error("Backend unreachable. Start it with: python main.py");
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed (${response.status})`);
  }
  return response.json();
}

function money(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);
}

function displayName(raw) {
  if (!raw) return "";
  if (raw.includes(",")) {
    const [last, first] = raw.split(",", 2).map((part) => part.trim());
    return `${titleish(first)} ${titleish(last)}`;
  }
  return titleish(raw);
}

function titleish(value) {
  if (!value) return "";
  return value === value.toUpperCase()
    ? value.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())
    : value;
}

function formatCandidateMeta(row) {
  return [
    row.office_full || row.office,
    row.party_full || row.party,
    [row.state, row.district].filter(Boolean).join("-"),
  ]
    .filter(Boolean)
    .join(" · ");
}

function formatPacMeta(row) {
  return [
    row.committee_type_full || row.committee_type || "PAC",
    row.designation_full || row.designation,
    row.party_full || row.party,
    row.state,
  ]
    .filter(Boolean)
    .join(" · ");
}

function setStatus(message) {
  els.status.textContent = message || "";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
