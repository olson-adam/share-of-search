// The snapshot produced by scripts/sos_calc.py — the app's single source of truth.
export type Brand = {
  name: string; share: number; volume: number; is_focus: boolean;
  delta_quarter: number | null; delta_year: number | null;
}
export type Mover = { keyword: string; type: string; brand: string; delta_y_pct: number }
export type Snapshot = {
  category: string; geo: string; language: string; focus_brand: string;
  as_of: string; source: string;
  months: string[];
  shares: Record<string, number[]>;
  category_volume_total: number[];
  branded_volume_total: number[];
  generic_share_of_total: number[];
  focus: { share: number; delta_quarter: number | null; delta_year: number | null;
           rank: number; of: number; gap_to_2: number | null; volume: number };
  brands: Brand[];
  movers: Mover[];
  basket: { keywords: number; version: string };
  validation: { errors: string[]; warnings: string[];
                stats: { months?: number; rows?: number; first_month?: string; last_month?: string } };
  capture?: {
    site: string; months: string[]; note: string;
    brands: Record<string, { clicks: number[]; impressions: number[]; position: number[] }>;
    site_total: { clicks: number[]; impressions: number[] };
    branded_share_of_site_impressions: number[];
  };
  yield?: {
    property: string; months: string[]; note: string;
    sessions: number[]; engaged_sessions: number[]; key_events: number[];
  };
}

export async function loadSnapshot(): Promise<Snapshot> {
  const res = await fetch("/snapshot.json")
  if (!res.ok) throw new Error(`snapshot.json: HTTP ${res.status}`)
  return res.json()
}

/* dense ribbed comb for the hero chart; tooltips always carry the month's
   ACTUAL value — interpolated bar heights are shape, not data.

   Interpolation is monotone cubic (Fritsch–Carlson): the silhouette is smooth
   but can never overshoot the measured monthly values — no invented peaks. */
export function ribbed(values: number[], months: string[], steps = 6) {
  const n = values.length
  const out: { x: number; h: number; month: string; actual: number }[] = []
  if (n === 0) return out
  if (n === 1) return [{ x: 0, h: values[0], month: months[0], actual: values[0] }]

  const d: number[] = []
  for (let i = 0; i < n - 1; i++) d.push(values[i + 1] - values[i])
  const m: number[] = new Array(n)
  m[0] = d[0]
  m[n - 1] = d[n - 2]
  for (let i = 1; i < n - 1; i++)
    m[i] = Math.sign(d[i - 1]) !== Math.sign(d[i]) ? 0 : (d[i - 1] + d[i]) / 2
  for (let i = 0; i < n - 1; i++) {
    if (d[i] === 0) { m[i] = 0; m[i + 1] = 0; continue }
    const a = m[i] / d[i], b = m[i + 1] / d[i]
    const s2 = a * a + b * b
    if (s2 > 9) { const tau = 3 / Math.sqrt(s2); m[i] = tau * a * d[i]; m[i + 1] = tau * b * d[i] }
  }
  const hermite = (i: number, t: number) => {
    const t2 = t * t, t3 = t2 * t
    return (2 * t3 - 3 * t2 + 1) * values[i] + (t3 - 2 * t2 + t) * m[i]
      + (-2 * t3 + 3 * t2) * values[i + 1] + (t3 - t2) * m[i + 1]
  }
  for (let i = 0; i < n - 1; i++) {
    for (let s = 0; s < steps; s++) {
      const t = s / steps
      const mi = t < 0.5 ? i : i + 1
      out.push({ x: i * steps + s, h: Math.max(0, hermite(i, t)),
                 month: months[mi], actual: values[mi] })
    }
  }
  out.push({ x: (n - 1) * steps, h: values[n - 1], month: months[n - 1], actual: values[n - 1] })
  return out
}

/* nice axis cap: headroom above the max, snapped to a clean step */
export function niceCap(top: number): number {
  const v = top * 1.22
  const step = v <= 14 ? 2 : 5
  return Math.ceil(v / step) * step
}
