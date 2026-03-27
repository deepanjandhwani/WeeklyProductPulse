/**
 * Weekly pulse dashboard — loads /api/reports and renders HTML.
 */

const $ = (sel) => document.querySelector(sel);

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function isoWeekToDateRange(isoWeek) {
  const m = isoWeek.match(/^(\d{4})-W(\d{2})$/);
  if (!m) return isoWeek;
  const year = parseInt(m[1]);
  const week = parseInt(m[2]);

  const jan4 = new Date(year, 0, 4);
  const dow = jan4.getDay() || 7;
  const week1Mon = new Date(jan4);
  week1Mon.setDate(jan4.getDate() - dow + 1);

  const mon = new Date(week1Mon);
  mon.setDate(week1Mon.getDate() + (week - 1) * 7);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);

  const sM = MONTHS[mon.getMonth()], eM = MONTHS[sun.getMonth()];
  const sD = mon.getDate(), eD = sun.getDate();
  const sY = mon.getFullYear(), eY = sun.getFullYear();

  if (sY !== eY) return `${sM} ${sD}, ${sY} – ${eM} ${eD}, ${eY}`;
  if (sM !== eM) return `${sM} ${sD} – ${eM} ${eD}, ${sY}`;
  return `${sM} ${sD} – ${eD}, ${sY}`;
}

function formatWeekLabel(isoWeek) {
  return isoWeekToDateRange(isoWeek);
}

/** ISO-8601 week string for a date (YYYY-Wnn), matches server report filenames. */
function toIsoWeekString(date = new Date()) {
  const target = new Date(date.valueOf());
  const dayNr = (date.getDay() + 6) % 7;
  target.setDate(target.getDate() - dayNr + 3);
  const firstThursday = target.valueOf();
  target.setMonth(0, 1);
  if (target.getDay() !== 4) {
    target.setMonth(0, 1 + ((4 - target.getDay() + 7) % 7));
  }
  const week = 1 + Math.round((firstThursday - target.valueOf()) / 604800000);
  const isoYear = target.getFullYear();
  return `${isoYear}-W${String(week).padStart(2, "0")}`;
}

function compareIsoWeek(a, b) {
  const ma = a.match(/^(\d{4})-W(\d{2})$/);
  const mb = b.match(/^(\d{4})-W(\d{2})$/);
  if (!ma || !mb) return 0;
  const ya = parseInt(ma[1], 10);
  const yb = parseInt(mb[1], 10);
  if (ya !== yb) return ya - yb;
  return parseInt(ma[2], 10) - parseInt(mb[2], 10);
}

/**
 * Prefer the report for the current ISO week if it exists; otherwise the newest
 * report whose week is not after the current week; else the newest file (edge cases).
 */
function preferredIsoWeekFromList(weeks) {
  if (!weeks.length) return null;
  const ids = weeks.map((r) => r.iso_week);
  const current = toIsoWeekString(new Date());
  if (ids.includes(current)) return current;
  let best = null;
  for (const iso of ids) {
    if (compareIsoWeek(iso, current) <= 0) best = iso;
  }
  return best || ids[ids.length - 1];
}

function showStatus(message, kind = "ok") {
  const el = $("#status");
  el.textContent = message;
  el.className = `status ${kind}`;
  el.classList.remove("hidden");
  if (kind === "ok") {
    setTimeout(() => el.classList.add("hidden"), 6000);
  }
}

function hideStatus() {
  $("#status").classList.add("hidden");
}

function setEmailSendingState(isSending) {
  const btn = $("#btn-email");
  if (!btn) return;
  if (isSending) {
    btn.dataset.originalText = btn.textContent || "Send report";
    btn.textContent = "Sending…";
    btn.classList.add("loading");
    btn.disabled = true;
  } else {
    btn.textContent = btn.dataset.originalText || "Send report";
    btn.classList.remove("loading");
    btn.disabled = false;
  }
}

function setLoadingState(isLoading) {
  const report = $("#report");
  const meta = $("#meta-panel");
  if (isLoading) {
    report.innerHTML = `<div class="loading-skeleton"><div class="skel-line w80"></div><div class="skel-line w60"></div><div class="skel-line w90"></div><div class="skel-line w45"></div><div class="skel-line w70"></div></div>`;
    meta?.classList.add("is-loading");
  } else {
    meta?.classList.remove("is-loading");
  }
}

async function fetchJson(url, options = {}) {
  const { cache = "default", ...fetchOpts } = options;
  const res = await fetch(url, { ...fetchOpts, cache });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

async function loadReportList(options = {}) {
  const { bustCache = false } = options;
  const url = bustCache ? `/api/reports?_=${Date.now()}` : "/api/reports";
  const data = await fetchJson(url, bustCache ? { cache: "no-store" } : {});
  const sel = $("#week-select");
  sel.innerHTML = "";
  const weeks = data.reports || [];
  for (const r of weeks) {
    const opt = document.createElement("option");
    opt.value = r.iso_week;
    opt.textContent = formatWeekLabel(r.iso_week);
    sel.appendChild(opt);
  }
  const preferred = preferredIsoWeekFromList(weeks);
  if (preferred) {
    sel.value = preferred;
  }
  return preferred;
}

async function loadReport(isoWeek, options = {}) {
  const { bustCache = false } = options;
  setLoadingState(true);
  try {
    let endpoint = isoWeek ? `/api/reports/${encodeURIComponent(isoWeek)}` : "/api/reports/latest";
    if (bustCache) {
      endpoint += endpoint.includes("?") ? `&_=${Date.now()}` : `?_=${Date.now()}`;
    }
    const data = await fetchJson(endpoint, bustCache ? { cache: "no-store" } : {});
    const dateRange = formatWeekLabel(data.iso_week);
    $("#meta-week").textContent = dateRange;
    $("#meta-status").textContent = "Report ready";
    $("#meta-status").className = "meta-badge meta-badge--ready";
    const article = $("#report");
    article.innerHTML = data.html;
    article.classList.add("prose");
    hideStatus();
  } finally {
    setLoadingState(false);
  }
}

async function init() {
  try {
    const latest = await loadReportList();
    if (latest) {
      await loadReport(latest);
    } else {
      setLoadingState(false);
      $("#meta-week").textContent = "—";
      $("#meta-status").textContent = "No reports yet";
      $("#meta-status").className = "meta-badge meta-badge--muted";
      $("#report").innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <polyline points="10 9 9 9 8 9"/>
            </svg>
          </div>
          <h3>No reports available yet</h3>
          <p>Reports are generated automatically every Sunday evening. Once the first pipeline run completes, your weekly pulse will appear here.</p>
        </div>`;
    }
  } catch (e) {
    setLoadingState(false);
    $("#report").innerHTML = `
      <div class="empty-state">
        <div class="empty-icon error-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <h3>Unable to load report</h3>
        <p>${escapeHtml(e.message)}</p>
      </div>`;
    showStatus(e.message, "error");
  }

  $("#week-select").addEventListener("change", async () => {
    const w = $("#week-select").value;
    try {
      await loadReport(w);
    } catch (e) {
      showStatus(e.message, "error");
    }
  });

  $("#btn-refresh").addEventListener("click", async () => {
    try {
      const preferred = await loadReportList({ bustCache: true });
      if (preferred) {
        await loadReport(preferred, { bustCache: true });
        const cur = toIsoWeekString(new Date());
        const label =
          preferred === cur
            ? "Latest data loaded for this week."
            : "Latest available report loaded (through " + formatWeekLabel(preferred) + ").";
        showStatus(label, "ok");
      } else {
        setLoadingState(false);
        $("#meta-week").textContent = "—";
        $("#meta-status").textContent = "No reports yet";
        $("#meta-status").className = "meta-badge meta-badge--muted";
        $("#report").innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <polyline points="10 9 9 9 8 9"/>
            </svg>
          </div>
          <h3>No reports available yet</h3>
          <p>Reports are generated automatically every Sunday evening. Once the first pipeline run completes, your weekly pulse will appear here.</p>
        </div>`;
        showStatus("No reports on the server yet.", "ok");
      }
    } catch (e) {
      showStatus(e.message, "error");
    }
  });

  $("#btn-email").addEventListener("click", async () => {
    const raw = $("#email-recipients").value.trim();
    if (!raw) {
      showStatus("Please enter at least one recipient email address.", "error");
      return;
    }
    const recipients = raw
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!recipients.length) {
      showStatus("Please enter a valid email address.", "error");
      return;
    }

    const headers = { "Content-Type": "application/json" };
    const token = $("#api-token").value.trim();
    if (token) {
      headers["X-Pulse-API-Token"] = token;
    }

    const isoWeek = $("#week-select").value || null;
    const body = {
      recipients,
      ...(isoWeek ? { iso_week: isoWeek } : {}),
    };

    setEmailSendingState(true);
    showStatus("Sending report…", "ok");
    try {
      const res = await fetch("/api/email/send", {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const d = data.detail;
        let msg = res.statusText;
        if (Array.isArray(d)) {
          msg = d.map((x) => x.msg || JSON.stringify(x)).join("; ");
        } else if (typeof d === "string") {
          msg = d;
        } else if (d && typeof d === "object") {
          msg = JSON.stringify(d);
        }
        throw new Error(msg);
      }
      const weekLabel = formatWeekLabel(data.iso_week);
      const recipientList = (data.recipients || []).join(", ");
      hideStatus();
      showSuccessPopup(weekLabel, recipientList);
    } catch (e) {
      showStatus(e.message, "error");
    } finally {
      setEmailSendingState(false);
    }
  });
}

function showSuccessPopup(weekLabel, recipients) {
  const overlay = $("#success-popup");
  $("#popup-detail").textContent = `Report for ${weekLabel} was sent to ${recipients}`;
  overlay.classList.remove("hidden");
  const dismiss = $("#popup-dismiss");
  dismiss.focus();
  dismiss.onclick = () => overlay.classList.add("hidden");
  overlay.onclick = (e) => {
    if (e.target === overlay) overlay.classList.add("hidden");
  };
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

init();
