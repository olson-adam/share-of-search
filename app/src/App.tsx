import { useEffect, useMemo, useState } from "react"
import NumberFlow from "@number-flow/react"
import { Area, AreaChart, Bar, ComposedChart, Line, XAxis, YAxis } from "recharts"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table"
import { ChartContainer, ChartTooltip } from "@/components/ui/chart"
import type { ChartConfig } from "@/components/ui/chart"
import { loadSnapshot, niceCap, ribbed, type Snapshot } from "@/snapshot"

const chartConfig = { h: { label: "Share", color: "var(--peri)" } } satisfies ChartConfig
const STEPS = 6

const fmtDelta = (d: number | null, unit = "") =>
  d === null ? "—" : `${d > 0 ? "+" : ""}${d.toFixed(1)}${unit}`

/* > 0 gain, < 0 loss, 0 or missing = neutral — never paint zero as bad news */
const deltaClass = (d: number | null, focusCard = false) =>
  d === null || d === 0 ? (focusCard ? "text-[#54565a]" : "text-faint")
    : d > 0 ? (focusCard ? "text-[#3f7d20]" : "text-acid") : "text-coral"

const cleanCategory = (c: string) => c.replace(/\s*\(.*?\)\s*/g, " ").trim()
const cleanSite = (s: string) =>
  s.replace(/^sc-domain:/, "").replace(/^https?:\/\//, "").replace(/\/+$/, "")

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
      <line x1={cx} y1={40} x2={cx} y2={cy - (end ? 9 : 7)}
        stroke="rgba(255,255,255,.14)" strokeDasharray="3 4" />
      <circle cx={cx} cy={cy} r={end ? 5.5 : 4} fill={end ? "#f4f4f2" : "#0c0c0e"}
        stroke={end ? "none" : "#a2a2a8"} strokeWidth={1.4}
        style={end ? { filter: "drop-shadow(0 0 8px rgba(244,244,242,.8))" } : {}} />
      <text x={cx} y={16} textAnchor={anchor} fill="#a2a2a8"
        style={{ font: "11px Geist Mono, monospace", letterSpacing: "0.1em" }}>{m[0]}</text>
      <text x={cx} y={33} textAnchor={anchor} fill="#f4f4f2" fontWeight={600}
        style={{ font: "12.5px Geist Mono, monospace", letterSpacing: "0.08em" }}>{m[1]}</text>
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
  const domain: [number, number] = [0, niceCap(Math.max(...series))]
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
      <ComposedChart data={data} margin={{ top: 64, right: 18, left: 18, bottom: 0 }} barCategoryGap="22%">
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
  const fs = snap.shares[snap.focus_brand]
  let spikeMonth: string | null = null
  if (f.delta_quarter !== null && Math.abs(f.delta_quarter) >= 1 && n >= 4) {
    const moves = [1, 2, 3].map((k) => ({ m: months[n - k], d: fs[n - k] - fs[n - k - 1] }))
    const biggest = moves.reduce((a, b) => (Math.abs(b.d) > Math.abs(a.d) ? b : a))
    if (Math.abs(biggest.d) >= 0.7 * Math.abs(f.delta_quarter)) spikeMonth = biggest.m.toLowerCase()
  }
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
        <span className="micro text-faint">{cleanCategory(snap.category)} · {snap.as_of}</span>
      </header>

      <Card className="gap-0 overflow-hidden rounded-md py-0">
        <CardContent className="px-11 pt-11 pb-0">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[15px] text-muted-foreground">Share of category demand</div>
              <div className="py-1 text-[clamp(84px,11vw,140px)] leading-[1.02] font-normal tracking-[-0.04em] tabular-nums">
                <NumberFlow value={f.share} suffix="%" trend={1} locales="en-US" format={{ minimumFractionDigits: 1, maximumFractionDigits: 1 }} />
              </div>
              <p className="max-w-[46ch] text-[16px] text-muted-foreground">
                Of everyone searching for a {cleanCategory(snap.category).toLowerCase().replace(/s$/, "")} brand,{" "}
                <b className="font-medium text-foreground">{f.share.toFixed(1)}% searched for {snap.focus_brand}</b>
                {f.delta_year !== null && <> — {fmtDelta(f.delta_year)} points in a year{onlyGainer ? ", the only brand gaining" : ""}</>}.
              </p>
              <div className="flex flex-wrap gap-5 pt-4 pb-6">
                <span className={`micro ${deltaClass(f.delta_quarter)}`}>
                  {(f.delta_quarter ?? 0) > 0 ? "↗" : (f.delta_quarter ?? 0) < 0 ? "↘" : "→"} {fmtDelta(f.delta_quarter, " pts")} this quarter{spikeMonth ? ` · mostly ${spikeMonth}` : ""}
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
          ? `axis 0–${niceCap(Math.max(...snap.shares[snap.focus_brand]))}% · shares sum to 100% across the ${f.of} brands`
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
                {b.share.toFixed(1)}%
              </div>
              <div className={`text-[12.5px] tabular-nums ${b.is_focus ? "text-[#54565a]" : "text-muted-foreground"}`}>
                <span className={deltaClass(b.delta_quarter, b.is_focus)}>
                  {fmtDelta(b.delta_quarter)} q
                </span>{" · "}
                <span className={deltaClass(b.delta_year, b.is_focus)}>
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
            <h3 className="pb-1 text-[14.5px] font-medium">Generic demand <span className="micro pl-1 text-faint">owned by no one</span></h3>
            <div className="flex items-baseline gap-6 pt-1">
              <div>
                <div className="text-[30px] font-normal tracking-[-0.02em] tabular-nums">{snap.generic_share_of_total[n - 1]}%</div>
                <div className="micro text-faint">of category search</div>
              </div>
              <div>
                <div className="text-[30px] font-normal tracking-[-0.02em] tabular-nums">{(snap.category_volume_total[n - 1] - snap.branded_volume_total[n - 1]).toLocaleString("en")}</div>
                <div className="micro text-faint">unbranded searches / mo</div>
              </div>
            </div>
            <div className="pt-3"><BrandSpark values={snap.generic_share_of_total} you={false} id="generic" /></div>
            <div className="micro flex justify-between pt-1 text-faint">
              <span>{months[0].toLowerCase()}</span>
              <span>buyers still deciding — unowned demand</span>
              <span>{months[n - 1].toLowerCase()}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {(snap.capture || snap.yield) && (
        <>
          <div className="micro flex items-center gap-3 px-1 pt-8 pb-3 text-faint">
            <span>from results page to your site</span>
            <span className="h-px flex-1 bg-border" />
            <span>not the market · {snap.capture ? cleanSite(snap.capture.site) : snap.yield?.property}</span>
          </div>
          <div className="grid grid-cols-2 gap-4 max-[960px]:grid-cols-1">
            {snap.capture && (() => {
              const c = snap.capture
              const fb = c.brands[snap.focus_brand]
              const m = c.months.length - 1
              const empty = !fb || fb.impressions.every((v) => v === 0)
              if (empty) return (
                <Card className="gap-0 rounded-md py-0">
                  <CardContent className="px-7 py-6">
                    <h3 className="pb-1 text-[14.5px] font-medium">In the search results <span className="micro pl-1 text-faint">your brand queries · google search console</span></h3>
                    <p className="max-w-[46ch] pt-3 text-[14px] leading-relaxed text-muted-foreground">
                      No search data in this property yet. Your traffic may live on another
                      Search Console property — list what you have access to with
                      <span className="font-mono text-[12.5px]"> gsc_capture.py --list-sites</span>.
                    </p>
                    <p className="micro pt-4 text-faint">property checked: {cleanSite(c.site)}</p>
                  </CardContent>
                </Card>
              )
              return (
                <Card className="gap-0 rounded-md py-0">
                  <CardContent className="px-7 py-6">
                    <h3 className="pb-1 text-[14.5px] font-medium">In the search results <span className="micro pl-1 text-faint">your brand queries · google search console</span></h3>
                    <div className="flex items-baseline gap-6 pt-1">
                      <div>
                        <div className="text-[30px] font-normal tracking-[-0.02em] tabular-nums">{fb ? fb.impressions[m].toLocaleString("en") : "—"}</div>
                        <div className="micro whitespace-nowrap text-faint">branded impressions · {c.months[m].toLowerCase()}</div>
                      </div>
                      <div>
                        <div className="text-[30px] font-normal tracking-[-0.02em] tabular-nums">{fb ? fb.clicks[m].toLocaleString("en") : "—"}</div>
                        <div className="micro text-faint">branded clicks</div>
                      </div>
                      <div>
                        <div className="text-[30px] font-normal tracking-[-0.02em] tabular-nums">{c.branded_share_of_site_impressions[m]}%</div>
                        <div className="micro text-faint">of site impressions</div>
                      </div>
                      {fb && m >= 12 && fb.impressions[m - 12] > 0 && (
                        <div>
                          <div className={`text-[30px] font-normal tracking-[-0.02em] tabular-nums ${fb.impressions[m] >= fb.impressions[m - 12] ? "text-acid" : "text-coral"}`}>
                            {fb.impressions[m] >= fb.impressions[m - 12] ? "+" : ""}{Math.round(100 * (fb.impressions[m] - fb.impressions[m - 12]) / fb.impressions[m - 12])}%
                          </div>
                          <div className="micro text-faint">impressions Δ year</div>
                        </div>
                      )}
                    </div>
                    {fb && <div className="pt-3"><BrandSpark values={fb.impressions} you={false} id="capture" /></div>}
                    <div className="micro flex justify-between pt-1 text-faint">
                      <span>{c.months[0].toLowerCase()}</span>
                      <span>branded queries landing on your site</span>
                      <span>{c.months[m].toLowerCase()}</span>
                    </div>
                  </CardContent>
                </Card>
              )
            })()}
            {snap.yield && (() => {
              const y = snap.yield
              const m = y.months.length - 1
              return (
                <Card className="gap-0 rounded-md py-0">
                  <CardContent className="px-7 py-6">
                    <h3 className="pb-1 text-[14.5px] font-medium">On your site <span className="micro pl-1 text-faint">organic search visitors · ga4</span></h3>
                    <div className="flex items-baseline gap-6 pt-1">
                      <div>
                        <div className="text-[30px] font-normal tracking-[-0.02em] tabular-nums">{y.sessions[m].toLocaleString("en")}</div>
                        <div className="micro whitespace-nowrap text-faint">sessions · {y.months[m].toLowerCase()}</div>
                      </div>
                      <div>
                        <div className="text-[30px] font-normal tracking-[-0.02em] tabular-nums">{y.engaged_sessions[m].toLocaleString("en")}</div>
                        <div className="micro text-faint">engaged</div>
                      </div>
                      <div>
                        <div className="text-[30px] font-normal tracking-[-0.02em] tabular-nums">{y.key_events[m].toLocaleString("en")}</div>
                        <div className="micro text-faint">key events</div>
                      </div>
                      {m >= 12 && y.sessions[m - 12] > 0 && (
                        <div>
                          <div className={`text-[30px] font-normal tracking-[-0.02em] tabular-nums ${y.sessions[m] >= y.sessions[m - 12] ? "text-acid" : "text-coral"}`}>
                            {y.sessions[m] >= y.sessions[m - 12] ? "+" : ""}{Math.round(100 * (y.sessions[m] - y.sessions[m - 12]) / y.sessions[m - 12])}%
                          </div>
                          <div className="micro text-faint">sessions Δ year</div>
                        </div>
                      )}
                    </div>
                    <div className="pt-3"><BrandSpark values={y.sessions} you={false} id="yield" /></div>
                    <div className="micro flex justify-between pt-1 text-faint">
                      <span>{y.months[0].toLowerCase()}</span>
                      <span>all organic search · not query-level</span>
                      <span>{y.months[m].toLowerCase()}</span>
                    </div>
                  </CardContent>
                </Card>
              )
            })()}
          </div>
        </>
      )}

      <footer className="micro flex flex-wrap justify-between gap-3 px-1 pt-7 text-faint">
        <span>
          <span className={v.errors.length === 0 ? "text-acid" : "text-coral"}>
            {v.errors.length === 0 ? "✓ validated" : "✗ validation failed"}
          </span>
          {" · "}{v.stats.months} months continuous · {v.stats.rows} rows
          {v.warnings.length > 0 ? ` · ${v.warnings.length} warning(s)` : " · 0 warnings"}
        </span>
        <span>{snap.source} · geo {snap.geo.toLowerCase()} · basket {snap.basket.version} · {snap.basket.keywords} kw · data as of {snap.as_of.toLowerCase()}</span>
      </footer>

    </div>
  )
}
