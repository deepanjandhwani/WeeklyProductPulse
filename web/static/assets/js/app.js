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

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

async function loadReportList() {
  const data = await fetchJson("/api/reports");
  const sel = $("#week-select");
  sel.innerHTML = "";
  const weeks = data.reports || [];
  for (const r of weeks) {
    const opt = document.createElement("option");
    opt.value = r.iso_week;
    opt.textContent = formatWeekLabel(r.iso_week);
    sel.appendChild(opt);
  }
  if (weeks.length) {
    sel.value = weeks[weeks.length - 1].iso_week;
  }
  return weeks.length ? weeks[weeks.length - 1].iso_week : null;
}

async function loadReport(isoWeek) {
  setLoadingState(true);
  try {
    const endpoint = isoWeek ? `/api/reports/${encodeURIComponent(isoWeek)}` : "/api/reports/latest";
    const data = await fetchJson(endpoint);
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
      const latest = await loadReportList();
      if (latest) {
        await loadReport(latest);
        showStatus("Report refreshed.", "ok");
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
