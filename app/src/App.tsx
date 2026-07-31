import { useEffect, useMemo, useState } from "react"
import NumberFlow from "@number-flow/react"
import { Area, AreaChart, Bar, ComposedChart, Line, XAxis, YAxis } from "recharts"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table"
import { ChartContainer, ChartTooltip } from "@/components/ui/chart"
import type { ChartConfig } from "@/components/ui/chart"
import { loadSnapshot, ribbed, type Snapshot } from "@/snapshot"

const chartConfig = { h: { label: "Share", color: "var(--peri)" } } satisfies ChartConfig
const STEPS = 6

const fmtDelta = (d: number | null, unit = "") =>
  d === null ? "—" : `${d > 0 ? "+" : ""}${d}${unit}`

function AnnotDot({ index, cx, cy, marks }: {
  index?: number; cx?: number; cy?: number
  marks: Record<number, [string, string]>
}) {
  const m = index !== undefined ? marks[index] : undefined
  if (!m || cx === undefined || cy === undefined) return <g key={`d${index}`} />
  const keys = Object.keys(marks).map(Number)
  const end = index === Math.max(...keys)
  const anchor = end ? "end" : index === 0 ? "start" : "middle"
  return (
    <g key={`d${index}`}>
      <circle cx={cx} cy={cy} r={end ? 5.5 : 4} fill={end ? "#f4f4f2" : "#0c0c0e"}
        stroke={end ? "none" : "#a2a2a8"} strokeWidth={1.4}
        style={end ? { filter: "drop-shadow(0 0 8px rgba(244,244,242,.8))" } : {}} />
      <text x={cx} y={cy - 32} textAnchor={anchor} fill="#a2a2a8"
        style={{ font: "11px Geist Mono, monospace", letterSpacing: "0.1em" }}>{m[0]}</text>
      <text x={cx} y={cy - 16} textAnchor={anchor} fill="#f4f4f2" fontWeight={600}
        style={{ font: "12px Geist Mono, monospace", letterSpacing: "0.08em" }}>{m[1]}</text>
    </g>
  )
}

function RibbedTooltip({ active, payload, mode }: {
  active?: boolean; payload?: Array<{ payload: { month: string; actual: number } }>
  mode: "share" | "volume"
}) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="micro rounded-sm border bg-popover px-2.5 py-1.5 text-popover-foreground">
      {p.month} · {mode === "share" ? `${p.actual.toFixed(1)}%` : `${p.actual.toLocaleString("en")} searches`}
    </div>
  )
}

function HeroChart({ snap, mode }: { snap: Snapshot; mode: "share" | "volume" }) {
  const series = mode === "share" ? snap.shares[snap.focus_brand] : snap.category_volume_total
  const data = useMemo(() => ribbed(series, snap.months, STEPS), [series, snap.months])
  const top = Math.max(...series)
  const domain: [number, number] = [0, Math.ceil(top * 1.22)]
  const marks = useMemo(() => {
    if (mode !== "share") return {}
    const n = series.length
    const idx = [0, n >= 13 ? n - 13 : Math.floor(n / 2), n - 1]
    const out: Record<number, [string, string]> = {}
    for (const i of idx) out[i * STEPS] = [snap.months[i].toUpperCase(), `${series[i].toFixed(1)}%`]
    return out
  }, [mode, series, snap.months])
  return (
    <ChartContainer config={chartConfig} className="h-[360px] w-full">
      <ComposedChart data={data} margin={{ top: 48, right: 14, left: 14, bottom: 0 }} barCategoryGap="22%">
        <defs>
          <linearGradient id="rib" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor="#2f2b7e" stopOpacity={0.55} />
            <stop offset="55%" stopColor="#6f6ae8" stopOpacity={0.9} />
            <stop offset="100%" stopColor="#c9c8ff" stopOpacity={1} />
          </linearGradient>
        </defs>
        <XAxis dataKey="x" hide />
        <YAxis domain={domain} hide />
        <ChartTooltip content={<RibbedTooltip mode={mode} />} cursor={{ fill: "rgba(255,255,255,.05)" }} />
        <Bar dataKey="h" fill="url(#rib)" maxBarSize={5} isAnimationActive={false} />
        {mode === "share" && (
          <Line dataKey="h" stroke="none" isAnimationActive={false} activeDot={false}
            dot={<AnnotDot marks={marks} />} />
        )}
      </ComposedChart>
    </ChartContainer>
  )
}

function BrandSpark({ values, you, id }: { values: number[]; you: boolean; id: string }) {
  const lo = Math.min(...values), hi = Math.max(...values)
  const data = values.map((v, i) => ({ i, v: (v - lo) / (hi - lo || 1) }))
  const stroke = you ? "#7d940f" : "#6a6a78"
  return (
    <ChartContainer config={chartConfig} className="h-16 w-full">
      <AreaChart data={data} margin={{ top: 6, bottom: 2, left: 2, right: 2 }}>
        <defs>
          <linearGradient id={`spark-${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity={you ? 0.35 : 0.22} />
            <stop offset="100%" stopColor={stroke} stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis domain={[-0.15, 1.15]} hide />
        <XAxis dataKey="i" hide />
        <Area type="natural" dataKey="v" stroke={stroke} strokeWidth={1.8}
          fill={`url(#spark-${id})`} fillOpacity={1} dot={false} isAnimationActive={false} />
      </AreaChart>
    </ChartContainer>
  )
}

export default function App() {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<"share" | "volume">("share")
  useEffect(() => { loadSnapshot().then(setSnap).catch((e) => setError(String(e))) }, [])

  if (error) return <div className="micro p-10 text-coral">could not load snapshot.json — {error}</div>
  if (!snap) return null

  const f = snap.focus
  const months = snap.months
  const n = months.length
  const catNow = snap.category_volume_total[n - 1]
  const catYoY = n >= 13
    ? Math.round(100 * (catNow - snap.category_volume_total[n - 13]) / snap.category_volume_total[n - 13])
    : null
  const gainers = snap.brands.filter((b) => (b.delta_year ?? 0) > 0)
  const onlyGainer = gainers.length === 1 && gainers[0].is_focus
  const axisMonths = [0, 3, 6, 9, 12, 15, n - 1].filter((i) => i < n)
    .map((i) => months[i].toLowerCase())
  const v = snap.validation

  return (
    <div className="mx-auto max-w-[1180px] px-8 pb-20">

      <header className="flex items-center justify-between py-6">
        <div className="flex items-center gap-2 text-[14.5px] font-medium">
          <span className="text-[17px] text-acid">✳</span> share-of-search
        </div>
        <span className="micro text-faint">{snap.category} · {snap.as_of}</span>
      </header>

      <Card className="gap-0 overflow-hidden rounded-md py-0">
        <CardContent className="px-11 pt-11 pb-0">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[15px] text-muted-foreground">Share of category demand</div>
              <div className="py-1 text-[clamp(84px,11vw,140px)] leading-[1.02] font-normal tracking-[-0.04em] tabular-nums">
                <NumberFlow value={f.share} suffix="%" trend={1} locales="en-US" />
              </div>
              <p className="max-w-[46ch] text-[16px] text-muted-foreground">
                Of everyone searching for a {snap.category.toLowerCase().replace(/s$/, "")} brand,{" "}
                <b className="font-medium text-foreground">{f.share}% searched for {snap.focus_brand}</b>
                {f.delta_year !== null && <> — {fmtDelta(f.delta_year)} points in a year{onlyGainer ? ", the only brand gaining" : ""}</>}.
              </p>
              <div className="flex flex-wrap gap-5 pt-4 pb-2">
                <span className={`micro ${(f.delta_quarter ?? 0) > 0 ? "text-acid" : "text-coral"}`}>
                  {(f.delta_quarter ?? 0) > 0 ? "↗" : "↘"} {fmtDelta(f.delta_quarter, " pts")} this quarter
                </span>
                <span className="micro text-faint">
                  rank {f.rank} of {f.of}{f.gap_to_2 !== null ? ` · gap to #2: ${f.gap_to_2}` : ""}
                </span>
                <span className="micro text-faint">
                  category demand {catNow.toLocaleString("en")}/mo{catYoY !== null ? ` · ${catYoY > 0 ? "+" : ""}${catYoY}%` : ""}
                </span>
              </div>
            </div>
            <Tabs value={tab} onValueChange={(x) => setTab(x as "share" | "volume")} className="pt-2">
              <TabsList className="rounded-sm bg-secondary">
                <TabsTrigger className="micro rounded-sm" value="share">Share</TabsTrigger>
                <TabsTrigger className="micro rounded-sm" value="volume">Volume</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
          <HeroChart snap={snap} mode={tab} />
          <div className="micro flex justify-between px-1 pt-2 pb-5 text-faint">
            {axisMonths.map((m, i) => <span key={i}>{m}</span>)}
          </div>
        </CardContent>
      </Card>
      <p className="micro px-1 pt-3 text-faint">
        {tab === "share"
          ? `axis 0–${Math.ceil(Math.max(...snap.shares[snap.focus_brand]) * 1.22)}% · shares sum to 100% across the ${f.of} brands`
          : "total branded + generic searches per month"} · {n} months · hover for monthly values
      </p>

      <div className="mt-5 grid grid-cols-4 gap-4 max-[960px]:grid-cols-2">
        {snap.brands.map((b) => (
          <Card key={b.name} className={`gap-0 rounded-md py-0 ${b.is_focus ? "border-transparent bg-light text-[#141416]" : ""}`}>
            <CardContent className="px-6 pt-6 pb-4">
              <div className="flex items-baseline gap-2 text-[14.5px] font-medium">
                {b.name}
                {b.is_focus && <Badge variant="outline" className="micro rounded-[3px] border-[#141416] px-1.5 py-0 text-[9.5px] text-[#141416]">you</Badge>}
              </div>
              <div className="pt-2 pb-0.5 text-[40px] font-normal tracking-[-0.03em] tabular-nums">
                {b.share}%
              </div>
              <div className={`text-[12.5px] tabular-nums ${b.is_focus ? "text-[#54565a]" : "text-muted-foreground"}`}>
                <span className={(b.delta_quarter ?? 0) > 0 ? (b.is_focus ? "text-[#3f7d20]" : "text-acid") : "text-coral"}>
                  {fmtDelta(b.delta_quarter)} q
                </span>{" · "}
                <span className={(b.delta_year ?? 0) > 0 ? (b.is_focus ? "text-[#3f7d20]" : "text-acid") : "text-coral"}>
                  {fmtDelta(b.delta_year)} y
                </span>
              </div>
              <div className="pt-3">
                <BrandSpark values={snap.shares[b.name]} you={b.is_focus} id={b.name} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 max-[960px]:grid-cols-1">
        <Card className="gap-0 rounded-md py-0">
          <CardContent className="px-7 py-6">
            <h3 className="pb-2 text-[14.5px] font-medium">Keyword movers <span className="micro pl-1 text-faint">Δ year</span></h3>
            <Table>
              <TableBody>
                {snap.movers.slice(0, 5).map((m) => (
                  <TableRow key={m.keyword} className="border-border hover:bg-transparent">
                    <TableCell className="px-0 text-[13.5px]">
                      {m.keyword} <span className="text-[12px] text-faint">· {m.type.toLowerCase()}</span>
                    </TableCell>
                    <TableCell className={`px-0 text-right tabular-nums ${m.delta_y_pct > 0 ? "text-acid" : "text-coral"}`}>
                      {m.delta_y_pct > 0 ? "+" : ""}{m.delta_y_pct}%
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
        <Card className="relative gap-0 overflow-hidden rounded-md py-0">
          <CardContent className="px-7 py-6">
            <h3 className="pb-2 text-[14.5px] font-medium">Method</h3>
            <p className="max-w-[58ch] text-[13.5px] leading-relaxed text-muted-foreground">
              Share of branded search demand — a leading indicator correlated with market-share
              movement (Binet, IPA 2020), not a measurement of it. Generic demand
              ({snap.generic_share_of_total[n - 1]}% of category search) belongs to no one and is
              tracked separately. Basket {snap.basket.version} · {snap.basket.keywords} keywords ·
              versioned with this snapshot.
            </p>
            <div aria-hidden className="pointer-events-none absolute right-4 bottom-4 h-[120px] w-[190px] opacity-50"
              style={{ background:
                "repeating-linear-gradient(to right, transparent 0 23px, rgba(143,143,250,.35) 23px 24px)," +
                "repeating-linear-gradient(to bottom, transparent 0 23px, rgba(143,143,250,.35) 23px 24px)" }} />
          </CardContent>
        </Card>
      </div>

      <footer className="micro flex flex-wrap justify-between gap-3 px-1 pt-7 text-faint">
        <span>
          <span className={v.errors.length === 0 ? "text-acid" : "text-coral"}>
            {v.errors.length === 0 ? "✓ validated" : "✗ validation failed"}
          </span>
          {" · "}{v.stats.months}/{v.stats.months} months · {v.stats.rows} rows
          {v.warnings.length > 0 ? ` · ${v.warnings.length} warning(s)` : " · 0 warnings"}
        </span>
        <span>{snap.source} · geo {snap.geo.toLowerCase()} · data as of {snap.as_of.toLowerCase()}</span>
      </footer>

    </div>
  )
}
