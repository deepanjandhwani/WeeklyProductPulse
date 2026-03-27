const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

export function isoWeekToDateRange(isoWeek: string): string {
  const m = isoWeek.match(/^(\d{4})-W(\d{2})$/);
  if (!m) return isoWeek;
  const year = parseInt(m[1], 10);
  const week = parseInt(m[2], 10);

  const jan4 = new Date(year, 0, 4);
  const dow = jan4.getDay() || 7;
  const week1Mon = new Date(jan4);
  week1Mon.setDate(jan4.getDate() - dow + 1);

  const mon = new Date(week1Mon);
  mon.setDate(week1Mon.getDate() + (week - 1) * 7);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);

  const sM = MONTHS[mon.getMonth()];
  const eM = MONTHS[sun.getMonth()];
  const sD = mon.getDate();
  const eD = sun.getDate();
  const sY = mon.getFullYear();
  const eY = sun.getFullYear();

  if (sY !== eY) return `${sM} ${sD}, ${sY} – ${eM} ${eD}, ${eY}`;
  if (sM !== eM) return `${sM} ${sD} – ${eM} ${eD}, ${sY}`;
  return `${sM} ${sD} – ${eD}, ${sY}`;
}

export function formatWeekLabel(isoWeek: string): string {
  return isoWeekToDateRange(isoWeek);
}

export function toIsoWeekString(date = new Date()): string {
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

export function compareIsoWeek(a: string, b: string): number {
  const ma = a.match(/^(\d{4})-W(\d{2})$/);
  const mb = b.match(/^(\d{4})-W(\d{2})$/);
  if (!ma || !mb) return 0;
  const ya = parseInt(ma[1], 10);
  const yb = parseInt(mb[1], 10);
  if (ya !== yb) return ya - yb;
  return parseInt(ma[2], 10) - parseInt(mb[2], 10);
}

export function preferredIsoWeekFromList(
  weeks: { iso_week: string }[],
): string | null {
  if (!weeks.length) return null;
  const ids = weeks.map((r) => r.iso_week);
  const current = toIsoWeekString(new Date());
  if (ids.includes(current)) return current;
  let best: string | null = null;
  for (const iso of ids) {
    if (compareIsoWeek(iso, current) <= 0) best = iso;
  }
  return best || ids[ids.length - 1];
}
