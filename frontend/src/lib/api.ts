export type ReportListItem = {
  iso_week: string;
  file: string;
  size_bytes: number;
};

export type ReportPayload = {
  iso_week: string;
  markdown: string;
  html: string;
};

export async function fetchJson<T>(
  url: string,
  options: RequestInit & { cache?: RequestCache } = {},
): Promise<T> {
  const { cache = "default", ...init } = options;
  const res = await fetch(url, { ...init, cache });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    const detail = data.detail;
    let msg = res.statusText;
    if (Array.isArray(detail)) {
      msg = detail
        .map((x: { msg?: string }) => x.msg || JSON.stringify(x))
        .join("; ");
    } else if (typeof detail === "string") {
      msg = detail;
    } else if (detail && typeof detail === "object") {
      msg = JSON.stringify(detail);
    }
    throw new Error(msg);
  }
  return data as T;
}
