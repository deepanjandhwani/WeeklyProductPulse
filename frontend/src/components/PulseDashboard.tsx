"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import DOMPurify from "dompurify";
import {
  fetchJson,
  type ReportListItem,
  type ReportPayload,
} from "@/lib/api";
import {
  formatWeekLabel,
  preferredIsoWeekFromList,
  toIsoWeekString,
} from "@/lib/week";

function ReportSkeleton() {
  return (
    <div className="loading-skeleton">
      <div className="skel-line w80" />
      <div className="skel-line w60" />
      <div className="skel-line w90" />
      <div className="skel-line w45" />
      <div className="skel-line w70" />
    </div>
  );
}

function EmptyDocIcon() {
  return (
    <svg
      width="48"
      height="48"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  );
}

function ErrorIcon() {
  return (
    <svg
      width="48"
      height="48"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg
      className="btn__icon"
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      width="44"
      height="44"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

export function PulseDashboard() {
  const [weeks, setWeeks] = useState<ReportListItem[]>([]);
  const [selectedWeek, setSelectedWeek] = useState<string>("");
  const [safeHtml, setSafeHtml] = useState<string>("");
  const [metaWeek, setMetaWeek] = useState("—");
  const [metaStatus, setMetaStatus] = useState<"loading" | "ready" | "empty">(
    "loading",
  );
  const [reportLoading, setReportLoading] = useState(true);
  const [initError, setInitError] = useState<string | null>(null);
  const [status, setStatus] = useState<{
    message: string;
    kind: "ok" | "error";
  } | null>(null);
  const [recipients, setRecipients] = useState("");
  const [emailSending, setEmailSending] = useState(false);
  const [popup, setPopup] = useState<{
    weekLabel: string;
    recipients: string;
  } | null>(null);
  const [logoFailed, setLogoFailed] = useState(false);

  const popupDismissRef = useRef<HTMLButtonElement>(null);

  const hideStatusSoon = useCallback((kind: "ok" | "error") => {
    if (kind === "ok") {
      window.setTimeout(() => setStatus(null), 6000);
    }
  }, []);

  const showStatus = useCallback(
    (message: string, kind: "ok" | "error" = "ok") => {
      setStatus({ message, kind });
      hideStatusSoon(kind);
    },
    [hideStatusSoon],
  );

  const loadReportList = useCallback(async (bustCache: boolean) => {
    const url = bustCache ? `/api/reports?_=${Date.now()}` : "/api/reports";
    const data = await fetchJson<{ reports: ReportListItem[] }>(url, {
      cache: bustCache ? "no-store" : "default",
    });
    const list = data.reports || [];
    setWeeks(list);
    const preferred = preferredIsoWeekFromList(list);
    if (preferred) setSelectedWeek(preferred);
    return { list, preferred };
  }, []);

  const loadReport = useCallback(
    async (isoWeek: string, bustCache: boolean) => {
      setReportLoading(true);
      try {
        let endpoint = `/api/reports/${encodeURIComponent(isoWeek)}`;
        if (bustCache) {
          endpoint += `?_=${Date.now()}`;
        }
        const data = await fetchJson<ReportPayload>(endpoint, {
          cache: bustCache ? "no-store" : "default",
        });
        setMetaWeek(formatWeekLabel(data.iso_week));
        setMetaStatus("ready");
        setSafeHtml(DOMPurify.sanitize(data.html));
        setInitError(null);
      } finally {
        setReportLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { preferred } = await loadReportList(false);
        if (cancelled) return;
        if (preferred) {
          await loadReport(preferred, false);
        } else {
          setMetaWeek("—");
          setMetaStatus("empty");
          setSafeHtml("");
          setReportLoading(false);
        }
      } catch (e) {
        if (cancelled) return;
        setInitError(e instanceof Error ? e.message : String(e));
        setMetaStatus("empty");
        setReportLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadReport, loadReportList]);

  useEffect(() => {
    if (!popup) return;
    popupDismissRef.current?.focus();
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setPopup(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [popup]);

  const onWeekChange = async (iso: string) => {
    setSelectedWeek(iso);
    try {
      await loadReport(iso, false);
    } catch (e) {
      showStatus(e instanceof Error ? e.message : String(e), "error");
    }
  };

  const onRefresh = async () => {
    try {
      const { preferred } = await loadReportList(true);
      if (preferred) {
        await loadReport(preferred, true);
        const cur = toIsoWeekString(new Date());
        const label =
          preferred === cur
            ? "Latest data loaded for this week."
            : `Latest available report loaded (through ${formatWeekLabel(preferred)}).`;
        showStatus(label, "ok");
      } else {
        setMetaWeek("—");
        setMetaStatus("empty");
        setSafeHtml("");
        showStatus("No reports on the server yet.", "ok");
      }
    } catch (e) {
      showStatus(e instanceof Error ? e.message : String(e), "error");
    }
  };

  const onSendEmail = async () => {
    const raw = recipients.trim();
    if (!raw) {
      showStatus("Please enter at least one recipient email address.", "error");
      return;
    }
    const recs = raw
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!recs.length) {
      showStatus("Please enter a valid email address.", "error");
      return;
    }

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    const body: { recipients: string[]; iso_week?: string } = { recipients: recs };
    if (selectedWeek) body.iso_week = selectedWeek;

    setEmailSending(true);
    showStatus("Sending report…", "ok");
    try {
      const res = await fetch("/api/email/send", {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      const data = (await res.json().catch(() => ({}))) as {
        detail?: unknown;
        iso_week?: string;
        recipients?: string[];
      };
      if (!res.ok) {
        const d = data.detail;
        let msg = res.statusText;
        if (Array.isArray(d)) {
          msg = d
            .map((x: { msg?: string }) => x.msg || JSON.stringify(x))
            .join("; ");
        } else if (typeof d === "string") {
          msg = d;
        } else if (d && typeof d === "object") {
          msg = JSON.stringify(d);
        }
        throw new Error(msg);
      }
      const weekLabel = formatWeekLabel(data.iso_week || selectedWeek);
      const recipientList = (data.recipients || recs).join(", ");
      setStatus(null);
      setPopup({ weekLabel, recipients: recipientList });
    } catch (e) {
      showStatus(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setEmailSending(false);
    }
  };

  const renderReportBody = () => {
    if (initError) {
      return (
        <div className="empty-state">
          <div className="empty-icon error-icon">
            <ErrorIcon />
          </div>
          <h3>Unable to load report</h3>
          <p>{initError}</p>
        </div>
      );
    }
    if (metaStatus === "empty" && !reportLoading) {
      return (
        <div className="empty-state">
          <div className="empty-icon">
            <EmptyDocIcon />
          </div>
          <h3>No reports available yet</h3>
          <p>
            Reports are generated automatically every Sunday evening. Once the
            first pipeline run completes, your weekly pulse will appear here.
          </p>
        </div>
      );
    }
    if (reportLoading) {
      return <ReportSkeleton />;
    }
    return (
      <div
        className="prose"
        // eslint-disable-next-line react/no-danger -- sanitized with DOMPurify
        dangerouslySetInnerHTML={{ __html: safeHtml }}
      />
    );
  };

  return (
    <>
      <a className="skip-link" href="#report">
        Skip to report
      </a>

      <header className="site-nav">
        <div className="site-nav__inner">
          <div className="site-nav__brand">
            {!logoFailed && (
              // eslint-disable-next-line @next/next/no-img-element -- optional brand asset may be absent
              <img
                className="site-nav__logo"
                src="/assets/images/indmoney-logo.png"
                alt=""
                width={28}
                height={28}
                onError={() => setLogoFailed(true)}
              />
            )}
            <span className="site-nav__name">IndMoney</span>
          </div>
          <span className="site-nav__product">Product Pulse</span>
        </div>
      </header>

      <div className="relative">
        <div className="hero-backdrop" aria-hidden />
        <section className="hero hero-inner" aria-labelledby="hero-title">
          <p className="hero__eyebrow">Customer voice</p>
          <h1 id="hero-title" className="hero__title">
            Weekly Product Pulse
          </h1>
          <p className="hero__subtitle">
            Play Store intelligence from a rolling twelve-week window — refined
            weekly into themes, quotes, and actions your team can use.
          </p>
        </section>
      </div>

      <div className="layout">
        <div className="toolbar" role="group" aria-label="Report controls">
          <div className="toolbar__group">
            <label className="toolbar__label" htmlFor="week-select">
              Period
            </label>
            <select
              id="week-select"
              className="toolbar__select"
              aria-label="Select report week"
              value={selectedWeek}
              onChange={(e) => onWeekChange(e.target.value)}
              disabled={!weeks.length}
            >
              {weeks.map((r) => (
                <option key={r.iso_week} value={r.iso_week}>
                  {formatWeekLabel(r.iso_week)}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className="btn btn--ghost"
            aria-label="Refresh report"
            onClick={onRefresh}
          >
            <RefreshIcon />
            Refresh
          </button>
        </div>

        <aside
          className={`meta ${reportLoading ? "is-loading" : ""}`}
          id="meta-panel"
        >
          <div className="meta__inner">
            <span className="meta__label">Viewing</span>
            <span className="meta__value">{metaWeek}</span>
            <span
              id="meta-status"
              className={
                metaStatus === "ready"
                  ? "meta-badge meta-badge--ready"
                  : "meta-badge meta-badge--muted"
              }
            >
              {metaStatus === "ready"
                ? "Report ready"
                : metaStatus === "loading"
                  ? "Loading…"
                  : "No reports yet"}
            </span>
          </div>
        </aside>

        <main className="content">
          {status ? (
            <div className={`status ${status.kind}`} role="status">
              {status.message}
            </div>
          ) : null}
          <article
            id="report"
            className="report"
            aria-live="polite"
            aria-busy={reportLoading}
          >
            {renderReportBody()}
          </article>
        </main>

        <section className="share-section" aria-labelledby="email-panel-title">
          <h2 id="email-panel-title" className="section-heading">
            Share
          </h2>
          <p className="section-lead">
            Deliver the full pulse by email — same rich formatting as on this
            page.
          </p>
          <div className="share-card">
            <label className="field-label" htmlFor="email-recipients">
              Email addresses
            </label>
            <textarea
              id="email-recipients"
              className="field-textarea"
              rows={2}
              autoComplete="email"
              placeholder="name@company.com"
              spellCheck={false}
              value={recipients}
              onChange={(e) => setRecipients(e.target.value)}
            />
            <div className="share-actions">
              <button
                type="button"
                id="btn-email"
                className={`btn btn--primary${emailSending ? " loading" : ""}`}
                disabled={emailSending}
                onClick={onSendEmail}
              >
                Send report
              </button>
            </div>
          </div>
        </section>

        <footer className="site-footer">
          <p>
            WeeklyProductPulse <span className="site-footer__dot">·</span>{" "}
            IndMoney Customer Voice
          </p>
        </footer>
      </div>

      <div
        id="success-popup"
        className={popup ? "popup-overlay" : "popup-overlay hidden"}
        role="dialog"
        aria-modal="true"
        aria-labelledby="popup-title"
        onClick={(e) => {
          if (e.target === e.currentTarget) setPopup(null);
        }}
      >
        <div className="popup-card">
          <div className="popup-icon" aria-hidden>
            <CheckIcon />
          </div>
          <h3 id="popup-title" className="popup-title">
            Email sent
          </h3>
          <p className="popup-detail" id="popup-detail">
            {popup
              ? `Report for ${popup.weekLabel} was sent to ${popup.recipients}`
              : ""}
          </p>
          <button
            type="button"
            className="btn btn--primary popup-dismiss"
            ref={popupDismissRef}
            onClick={() => setPopup(null)}
          >
            Done
          </button>
        </div>
      </div>
    </>
  );
}
