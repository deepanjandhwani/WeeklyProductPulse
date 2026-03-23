/**
 * Weekly pulse dashboard — loads /api/reports and renders HTML.
 */

const $ = (sel) => document.querySelector(sel);

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
    btn.dataset.originalText = btn.textContent || "Send email";
    btn.textContent = "Sending email...";
    btn.classList.add("loading");
    btn.disabled = true;
  } else {
    btn.textContent = btn.dataset.originalText || "Send email";
    btn.classList.remove("loading");
    btn.disabled = false;
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
    opt.textContent = r.iso_week;
    sel.appendChild(opt);
  }
  if (weeks.length) {
    sel.value = weeks[weeks.length - 1].iso_week;
  }
  return weeks.length ? weeks[weeks.length - 1].iso_week : null;
}

async function loadReport(isoWeek) {
  const endpoint = isoWeek ? `/api/reports/${encodeURIComponent(isoWeek)}` : "/api/reports/latest";
  const data = await fetchJson(endpoint);
  $("#meta-week").textContent = data.iso_week;
  $("#meta-file").textContent = `Ready for week ${data.iso_week}`;
  const article = $("#report");
  article.innerHTML = data.html;
  article.classList.add("prose");
  hideStatus();
}

async function init() {
  try {
    const latest = await loadReportList();
    await loadReport(latest || undefined);
  } catch (e) {
    $("#report").innerHTML = `<p class="placeholder">Could not load report: ${escapeHtml(e.message)}</p>`;
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
      const w = $("#week-select").value;
      await loadReport(w || undefined);
      showStatus("Report refreshed.", "ok");
    } catch (e) {
      showStatus(e.message, "error");
    }
  });

  $("#btn-email").addEventListener("click", async () => {
    const raw = $("#email-recipients").value.trim();
    if (!raw) {
      showStatus("Enter at least one recipient email address.", "error");
      return;
    }
    /** Split on comma, semicolon, or whitespace / newlines */
    const recipients = raw
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!recipients.length) {
      showStatus("Enter at least one valid-looking email address.", "error");
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
    showStatus("Sending email...", "ok");
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
      showStatus(`Sent full report for ${data.iso_week} → ${(data.recipients || []).join(", ")}`, "ok");
    } catch (e) {
      showStatus(e.message, "error");
    } finally {
      setEmailSendingState(false);
    }
  });
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

init();
