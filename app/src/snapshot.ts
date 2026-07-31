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
}

export async function loadSnapshot(): Promise<Snapshot> {
  const res = await fetch("/snapshot.json")
  if (!res.ok) throw new Error(`snapshot.json: HTTP ${res.status}`)
  return res.json()
}

/* dense ribbed comb for the hero chart; tooltips always carry the month's
   ACTUAL value — interpolated bar heights are shape, not data */
export function ribbed(values: number[], months: string[], steps = 6) {
  const out: { x: number; h: number; month: string; actual: number }[] = []
  for (let i = 0; i < values.length - 1; i++) {
    for (let s = 0; s < steps; s++) {
      const t = s / steps
      const mi = t < 0.5 ? i : i + 1
      out.push({ x: i * steps + s, h: values[i] + (values[i + 1] - values[i]) * t,
                 month: months[mi], actual: values[mi] })
    }
  }
  const last = values.length - 1
  out.push({ x: last * steps, h: values[last], month: months[last], actual: values[last] })
  return out
}
