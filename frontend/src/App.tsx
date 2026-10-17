import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { BenchmarkRow, Plan, RunIndexItem, RunRecord } from './types'
import { parseRun } from './types'

const screens = [
  ['A', 'Overview'], ['B', 'Sources'], ['C', 'Windows'], ['D', 'Beliefs'],
  ['E', 'Planner'], ['F', 'Comparison'], ['G', 'Method'],
] as const
type Screen = typeof screens[number][0]

async function getJson<T>(url: string): Promise<T> {
  let lastError: unknown
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const response = await fetch(url, { headers: { Accept: 'application/json' } })
      if (!response.ok) throw new Error(response.status === 404 ? 'Artifact is not available yet.' : `Request failed (${response.status}).`)
      return await response.json() as T
    } catch (error) {
      lastError = error
      if (attempt < 2) await new Promise((resolve) => window.setTimeout(resolve, 180 * (attempt + 1)))
    }
  }
  throw lastError
}

function fmt(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return 'Unavailable'
  return new Intl.NumberFormat('en-CA', { maximumFractionDigits: digits }).format(value)
}
function utc(value: string | undefined): string { return value ? `${value.replace(/\.\d+(?=Z$)/, '').replace('T', ' ').replace(/Z$/, '')}Z` : '—' }
function shortHash(value: string | undefined): string { return value ? value.slice(0, 12) : 'Unavailable' }
function byTime<T extends { state_time_utc?: string; time_utc?: string; created_at_sim_utc?: string }>(a: T, b: T): number {
  return Date.parse(a.state_time_utc ?? a.time_utc ?? a.created_at_sim_utc ?? '') - Date.parse(b.state_time_utc ?? b.time_utc ?? b.created_at_sim_utc ?? '')
}
function Provenance({ kind }: { kind: string }) {
  const labels: Record<string, string> = { REAL_OBSERVATION: 'OBS', MODEL_INFERENCE: 'MODEL', SIMULATED_OBSERVATION: 'SIM', SIMULATED_GROUND_TRUTH: 'TRUTH' }
  return <span className={`tag tag-${kind.toLowerCase()}`} aria-label={kind.replaceAll('_', ' ')}>{labels[kind] ?? kind}</span>
}
function Empty({ title, detail, action }: { title: string; detail: string; action?: () => void }) {
  return <div className="empty-state"><span className="empty-mark" aria-hidden="true">—</span><h3>{title}</h3><p>{detail}</p>{action && <button className="button quiet" onClick={action}>Retry loading</button>}</div>
}
function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>
}
function SectionTitle({ eyebrow, title, description, right }: { eyebrow: string; title: string; description: string; right?: ReactNode }) {
  return <div className="section-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{right && <div className="section-actions">{right}</div>}</div>
}
function DataTable({ headers, children, label }: { headers: string[]; children: React.ReactNode; label: string }) {
  return <div className="table-wrap"><table><caption className="sr-only">{label}</caption><thead><tr>{headers.map((header) => <th key={header} scope="col">{header}</th>)}</tr></thead><tbody>{children}</tbody></table></div>
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('A')
  const [runs, setRuns] = useState<RunIndexItem[]>([])
  const [run, setRun] = useState<RunRecord | null>(null)
  const [runId, setRunId] = useState(new URLSearchParams(location.search).get('run') ?? '')
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading')
  const [loadError, setLoadError] = useState('')
  const [benchmarks, setBenchmarks] = useState<BenchmarkRow[]>([])
  const [benchmarkState, setBenchmarkState] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading')

  const loadRun = useCallback(async (id: string) => {
    if (!id) { setRun(null); setRunId(''); setLoadState('empty'); return }
    setLoadState('loading'); setLoadError('')
    try {
      const value = parseRun(await getJson<unknown>(`/api/runs/${encodeURIComponent(id)}`))
      setRun(value); setRunId(value.run_id); setLoadState('ready')
      const url = new URL(location.href); url.searchParams.set('run', value.run_id); history.replaceState(null, '', url)
    } catch (error) {
      setRun(null); setLoadState('error'); setLoadError(error instanceof Error ? error.message : 'Could not load run artifact.')
    }
  }, [])

  const refresh = useCallback(async () => {
    setLoadState('loading')
    try {
      const index = await getJson<RunIndexItem[]>('/api/runs')
      if (!Array.isArray(index) || index.some((item) => !item || typeof item.run_id !== 'string' || typeof item.policy_id !== 'string')) throw new Error('Run index response has an invalid shape.')
      setRuns(index)
      const wanted = runId || new URLSearchParams(location.search).get('run') || index[0]?.run_id || ''
      if (wanted) await loadRun(wanted)
      else {
        try {
          const example = parseRun(await getJson<unknown>('/api/example'))
          setRun(example); setRunId(example.run_id); setLoadState('ready')
        } catch {
          setRun(null); setLoadState('empty')
        }
      }
    } catch (error) {
      setRun(null); setLoadState('error'); setLoadError(error instanceof Error ? error.message : 'Run archive is unavailable.')
    }
  }, [loadRun, runId])

  useEffect(() => { void refresh() }, []) // initial archive load only
  useEffect(() => {
    let alive = true
    getJson<BenchmarkRow[]>('/api/benchmark-results.csv').then((rows) => {
      if (!Array.isArray(rows) || rows.some((row) => !row || typeof row !== 'object' || Object.values(row).some((value) => typeof value !== 'string'))) throw new Error('Benchmark response has an invalid shape.')
      if (alive) { setBenchmarks(rows); setBenchmarkState(rows.length ? 'ready' : 'empty') }
    }).catch(() => { if (alive) setBenchmarkState('empty') })
    return () => { alive = false }
  }, [])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement || event.target instanceof HTMLTextAreaElement) return
      const index = Number(event.key) - 1
      if (index >= 0 && index < screens.length) setScreen(screens[index][0])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const content = run ? <ScreenContent screen={screen} run={run} benchmarks={benchmarks} benchmarkState={benchmarkState} /> : null
  const currentPlan = run?.plans.at(-1)
  const status = currentPlan?.solver_status ?? '—'

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="topbar">
      <a className="brand" href="#overview" onClick={(event) => { event.preventDefault(); setScreen('A') }} aria-label="AETHER research console overview">
        <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><span>AETHER<small>RESEARCH CONSOLE</small></span>
      </a>
      <div className="topbar-center"><span className="live-dot" /> READ ONLY <span className="topbar-divider">/</span> OFFLINE ARTIFACTS</div>
      <div className="topbar-right"><span className="avatar">R</span><span>Research workspace</span></div>
    </header>
    <div className="mission-banner"><span className="banner-symbol" aria-hidden="true">◉</span><strong>SIMULATED MISSION</strong><span>All spacecraft and acquisitions in this console are virtual.</span><span className="banner-end">NO REAL SATELLITE TASKING</span></div>
    <div className="workspace">
      <aside className="sidebar" aria-label="Console navigation">
        <div className="side-label">WORKSPACE</div>
        <nav>{screens.map(([key, label]) => <button key={key} onClick={() => setScreen(key)} className={`nav-item ${screen === key ? 'active' : ''}`} aria-current={screen === key ? 'page' : undefined}><span className="nav-key">{key}</span><span>{label}</span>{key === 'G' && <span className="nav-meta">INFO</span>}</button>)}</nav>
        <div className="sidebar-spacer" />
        <div className="side-label">ARTIFACT</div>
        <label className="run-label" htmlFor="run-select">SELECT RUN</label>
      <select id="run-select" value={runId} onChange={(event) => { setRunId(event.target.value); void loadRun(event.target.value) }} aria-label="Select archived run">
          <option value="">No run selected</option>{runId && !runs.some((item) => item.run_id === runId) && <option value={runId}>{runId} · example artifact</option>}{runs.map((item) => <option key={item.run_id} value={item.run_id}>{item.run_id} · {item.policy_id}</option>)}
        </select>
        <button className="refresh-button" onClick={() => void refresh()}><span aria-hidden="true">↻</span> Refresh archive</button>
        <div className="sidebar-foot"><span className="foot-square" /> P0 · LOCAL ARCHIVE</div>
      </aside>
      <main id="main-content" tabIndex={-1}>
        {loadState === 'loading' && <div className="loading-panel"><div className="skeleton skeleton-title" /><div className="skeleton-grid">{[1, 2, 3, 4].map((x) => <div className="skeleton skeleton-card" key={x} />)}</div><div className="skeleton skeleton-body" /><p>Reading run archive…</p></div>}
        {loadState === 'empty' && <Empty title="No run artifacts found" detail="The read only console loads validated run.json files from the local archive. Add a completed run artifact to begin exploring windows, beliefs and plans." action={() => void refresh()} />}
        {loadState === 'error' && <Empty title="Run archive could not be loaded" detail={`${loadError} Start the artifact API or choose a run from a reachable archive, then retry.`} action={() => void refresh()} />}
        {loadState === 'ready' && run && content}
      </main>
    </div>
    <footer className="statusbar"><div><span className="status-indicator" />{run ? 'REPLAY' : 'ARCHIVE'} <span className="status-sep">·</span><span className="mono">{run?.run_id ?? 'NO RUN SELECTED'}</span></div><div>SCENARIO <span className="mono">{shortHash(run?.model_config_hash)}</span></div><div>UTC <span className="mono">{run?.plans.at(-1) ? utc(run.plans.at(-1)?.created_at_sim_utc) : '—'}</span></div><div>SOLVER <span className={`solver-pill ${status.toLowerCase()}`}>{status}</span></div></footer>
  </div>
}

function ScreenContent({ screen, run, benchmarks, benchmarkState }: { screen: Screen; run: RunRecord; benchmarks: BenchmarkRow[]; benchmarkState: string }) {
  switch (screen) {
    case 'A': return <Overview run={run} />
    case 'B': return <SourceMap run={run} />
    case 'C': return <Windows run={run} />
    case 'D': return <Beliefs run={run} />
    case 'E': return <Planner run={run} />
    case 'F': return <Comparison run={run} benchmarks={benchmarks} state={benchmarkState} />
    case 'G': return <Method run={run} />
  }
}

function Overview({ run }: { run: RunRecord }) {
  const accepted = run.windows.filter((item) => item.feasible).length
  const rejected = run.windows.length - accepted
  const valid = run.acquisitions.filter((item) => item.outcome === 'DETECTION' || item.outcome === 'VALID_NON_DETECTION').length
  const plan = run.plans.at(-1)
  const policies = [...new Set(run.plans.map((item) => item.policy_id))]
  const spacecraft = [...new Set(run.windows.map((item) => item.spacecraft_id))]
  return <div className="page">
    <SectionTitle eyebrow="A / RUN OVERVIEW" title={run.scenario_id.replaceAll('_', ' ')} description="A traceable replay of one simulated observation planning run." right={<Provenance kind="SIMULATED_OBSERVATION" />} />
    <div className="run-strip"><div><span className="eyebrow">RUN IDENTIFIER</span><strong className="mono">{run.run_id}</strong></div><div><span className="eyebrow">POLICY</span><strong>{run.policy_id}</strong></div><div><span className="eyebrow">SCENARIO FAMILY</span><strong>{run.family}</strong></div><div><span className="eyebrow">SEED</span><strong className="mono">{run.seed}</strong></div></div>
    <div className="metrics-grid">
      <Metric label="SOURCES" value={fmt(run.sources.length, 0)} note="hypotheses in this run" />
      <Metric label="WINDOWS" value={fmt(run.windows.length, 0)} note={`${accepted} feasible · ${rejected} rejected`} />
      <Metric label="ACQUISITIONS" value={fmt(run.acquisitions.length, 0)} note={`${valid} valid outcomes / ${run.acquisitions.length} attempts`} />
      <Metric label="PLAN REVISIONS" value={fmt(run.plans.length, 0)} note={plan ? `latest ${plan.solver_status}` : 'no plan recorded'} />
    </div>
    <div className="overview-grid">
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">EXECUTION</div><h2>Run record</h2></div><span className="status-pill">REPLAY</span></div><dl className="key-values"><dt>Current plan</dt><dd>{plan ? `Revision ${plan.revision} · ${plan.solver_status}` : 'Unavailable'}</dd><dt>Last plan cause</dt><dd>{plan?.cause ?? 'No plan recorded'}</dd><dt>Independent validation</dt><dd>{run.validations.at(-1) ? (run.validations.at(-1)?.ok ? 'Passed' : 'Violations recorded') : 'Unavailable'}</dd><dt>Recorded events</dt><dd className="mono">{run.events.length}</dd></dl></section>
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">POLICY CONTEXT</div><h2>Recorded policy runs</h2></div><span className="count-badge">{policies.length}</span></div>{policies.length ? <div className="policy-list">{policies.map((policy) => <div className="policy-row" key={policy}><span className="policy-glyph">↗</span><span>{policy}</span><span className="policy-note">from plan history</span></div>)}</div> : <p className="muted">No policy plans were recorded.</p>}<p className="fine-print">A single run record contains one policy. Cross-policy comparison requires benchmark output.</p></section>
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">OBSERVATION CONTEXT</div><h2>Inputs attached to run</h2></div></div><dl className="key-values"><dt>Virtual spacecraft</dt><dd>{spacecraft.length ? spacecraft.join(', ') : 'Unavailable'}</dd><dt>Historic detections</dt><dd>Not included in this run record</dd><dt>Spacecraft profiles</dt><dd>Unavailable in this artifact</dd></dl><p className="fine-print">Historic observations and spacecraft profiles are shown only when their source artifacts are attached.</p></section>
    </div>
    <div className="section-footer"><span>MODEL CONFIG <code>{shortHash(run.model_config_hash)}</code></span><span>CODE <code>{run.code_version}</code></span><span>TRUTH CONFIG HASH <code>{shortHash(run.truth_config_hash)}</code> · EVALUATOR METADATA ONLY</span></div>
  </div>
}

function SourceMap({ run }: { run: RunRecord }) {
  const coords = run.sources
  const minLon = Math.min(...coords.map((s) => s.lon), -104.5), maxLon = Math.max(...coords.map((s) => s.lon), -101)
  const minLat = Math.min(...coords.map((s) => s.lat), 30.8), maxLat = Math.max(...coords.map((s) => s.lat), 33.5)
  const lonSpan = Math.max(maxLon - minLon, 0.001), latSpan = Math.max(maxLat - minLat, 0.001)
  return <div className="page"><SectionTitle eyebrow="B / SOURCE HYPOTHESES" title="Geographic context" description="Locations are source hypotheses from this run. The map is paired with a keyboard accessible source table." />
    <div className="map-layout"><div className="map-panel" aria-label="Schematic source location plot">
      <svg viewBox="0 0 720 390" role="img" aria-labelledby="map-title map-desc"><title id="map-title">Source hypothesis locations</title><desc id="map-desc">Schematic longitude and latitude plot of source hypotheses. No basemap or facility attribution is included.</desc>
        <rect x="0" y="0" width="720" height="390" fill="#f6f7f4" />
        {[0, 1, 2, 3, 4].map((i) => <g key={i}><line x1={70 + i * 140} x2={70 + i * 140} y1="24" y2="344" className="map-grid"/><line x1="70" x2="630" y1={24 + i * 80} y2={24 + i * 80} className="map-grid" /></g>)}
        <text x="70" y="372" className="map-axis">{fmt(minLon, 2)}°W</text><text x="570" y="372" className="map-axis">{fmt(maxLon, 2)}°W</text><text x="18" y="33" className="map-axis">{fmt(maxLat, 2)}°N</text><text x="18" y="345" className="map-axis">{fmt(minLat, 2)}°N</text>
        {coords.map((source, i) => { const x = 70 + ((source.lon - minLon) / lonSpan) * 560; const y = 344 - ((source.lat - minLat) / latSpan) * 320; return <g key={source.id}><circle cx={x} cy={y} r="7" className="source-dot"/><text x={x + 10} y={y + 4} className="source-label">{i + 1}</text></g> })}
      </svg><div className="map-legend"><span><i className="legend-dot" /> MODEL <span className="muted">source hypothesis</span></span><span className="map-note">schematic coordinates · no basemap</span></div>
    </div><section className="panel source-panel"><div className="panel-head"><div><div className="eyebrow">SOURCE INDEX</div><h2>{coords.length} hypotheses</h2></div></div>
      {coords.length ? <DataTable label="Source hypothesis coordinates" headers={['SOURCE', 'LONGITUDE', 'LATITUDE', 'STATUS']}><>{coords.map((s, i) => <tr key={s.id}><td><strong>{String(i + 1).padStart(2, '0')}</strong><span className="subcell">{s.id}</span></td><td className="mono">{fmt(s.lon, 4)}°</td><td className="mono">{fmt(s.lat, 4)}°</td><td><Provenance kind="MODEL_INFERENCE" /></td></tr>)}</></DataTable> : <Empty title="No source locations" detail="This run contains no source hypotheses." />}
    </section></div>
  </div>
}

function Windows({ run }: { run: RunRecord }) {
  const feasible = run.windows.filter((w) => w.feasible)
  const rejected = run.windows.filter((w) => !w.feasible)
  const start = Math.min(...run.windows.map((w) => Date.parse(w.start_utc)), Date.now())
  const finish = Math.max(...run.windows.map((w) => Date.parse(w.end_utc)), start + 1)
  const span = Math.max(finish - start, 1)
  const [showRejected, setShowRejected] = useState(false)
  return <div className="page"><SectionTitle eyebrow="C / ORBITAL AVAILABILITY" title="Observation windows" description="Virtual spacecraft opportunities and rejected candidates from the recorded run." right={<button className={`button ${showRejected ? 'selected' : ''}`} onClick={() => setShowRejected(!showRejected)}>{showRejected ? 'Hide rejected' : `Show rejected · ${rejected.length}`}</button>} />
    {!run.windows.length ? <Empty title="No windows in this run" detail="The run artifact contains no candidate windows." /> : <>
      <div className="timeline-panel"><div className="timeline-heading"><div><span className="eyebrow">WINDOW TIMELINE</span><h2>Pass opportunity by virtual spacecraft</h2></div><div className="timeline-legend"><span><i className="line-swatch feasible"/>FEASIBLE</span><span><i className="line-swatch rejected"/>REJECTED</span></div></div>
        <div className="timeline-axis"><span>{utc(new Date(start).toISOString())}</span><span>{utc(new Date(finish).toISOString())}</span></div>
        {Object.entries(groupBy(run.windows, (w) => w.spacecraft_id)).map(([sat, windows]) => <div className="timeline-row" key={sat}><div className="timeline-label"><span className="satellite-mark">▤</span><strong>{sat}</strong></div><div className="timeline-track">{(windows ?? []).filter((w) => showRejected || w.feasible).map((w) => { const left = (Date.parse(w.start_utc) - start) / span * 100; const width = Math.max((Date.parse(w.end_utc) - Date.parse(w.start_utc)) / span * 100, 0.45); return <button key={w.id} className={`window-mark ${w.feasible ? 'ok' : 'no'}`} style={{ left: `${left}%`, width: `${Math.max(width, 0.45)}%` }} title={`${w.id} · ${w.feasible ? 'feasible' : w.rejection_reasons.join(', ')}`} aria-label={`${w.id}, ${w.feasible ? 'feasible' : `rejected: ${w.rejection_reasons.join(', ')}`}`} /> })}</div></div>)}
      </div>
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">WINDOW REGISTER</div><h2>{showRejected ? 'All candidates' : 'Feasible candidates'}</h2></div><span className="count-badge">{showRejected ? run.windows.length : feasible.length}</span></div>
        <DataTable label="Observation window details" headers={['WINDOW / SOURCE', 'SPACECRAFT', 'START (UTC)', 'OFF-NADIR', 'DURATION', 'STATUS / REASON']}><>{(showRejected ? run.windows : feasible).map((w) => <tr key={w.id}><td><strong className="mono">{w.id}</strong><span className="subcell">{w.source_id} · pass {w.pass_id}</span></td><td>{w.spacecraft_id}<span className="subcell">{w.sensor_id}</span></td><td className="mono">{utc(w.start_utc)}</td><td className="numeric">{fmt(w.min_off_nadir_deg)}°</td><td className="numeric">{fmt(w.duration_s, 1)} s</td><td>{w.feasible ? <span className="state-label good">FEASIBLE · {w.options.length} starts</span> : <span className="state-label bad">{w.rejection_reasons.join(' · ')}</span>}</td></tr>)}</></DataTable>
      </section>
    </>}
  </div>
}
function groupBy<T, K extends string>(items: T[], key: (item: T) => K): Record<K, T[]> {
  return items.reduce((acc, item) => { const k = key(item); (acc[k] ??= []).push(item); return acc }, {} as Record<K, T[]>)
}

function Beliefs({ run }: { run: RunRecord }) {
  const sources = run.sources.map((s) => s.id)
  const [sourceId, setSourceId] = useState(sources[0] ?? '')
  const selected = run.beliefs.filter((belief) => belief.source_id === (sources.includes(sourceId) ? sourceId : sources[0])).sort(byTime)
  const acquisitions = run.acquisitions.filter((item) => item.source_id === (sources.includes(sourceId) ? sourceId : sources[0])).sort(byTime)
  const points = selected.map((belief, index) => `${selected.length === 1 ? 50 : 42 + index * 540 / (selected.length - 1)},${210 - belief.p_active * 170}`).join(' ')
  return <div className="page"><SectionTitle eyebrow="D / SOURCE SCIENCE" title="Belief history" description="Model-inferred activity probability and evidence sequence. Missing or invalid observations do not count as non-detections." right={<label className="select-control">SOURCE<select value={sourceId} onChange={(e) => setSourceId(e.target.value)}>{sources.map((s) => <option key={s}>{s}</option>)}</select></label>} />
    {!sources.length ? <Empty title="No source hypotheses" detail="Belief history is unavailable for this run." /> : <>
      {!selected.length && <div className="notice notice-neutral"><strong>INSUFFICIENT EVIDENCE</strong><span>No belief snapshots were recorded for this source. The source cannot be described as inactive.</span></div>}
      <div className="belief-grid"><section className="panel chart-panel"><div className="panel-head"><div><div className="eyebrow">ACTIVITY PROBABILITY</div><h2>P(active) over time</h2></div><Provenance kind="MODEL_INFERENCE" /></div>
        {selected.length ? <><div className="chart-box"><svg viewBox="0 0 620 250" role="img" aria-label={`Activity probability for ${sourceId}; vertical axis from zero to one`}><line x1="42" x2="600" y1="40" y2="40" className="chart-grid"/><line x1="42" x2="600" y1="125" y2="125" className="chart-grid"/><line x1="42" x2="600" y1="210" y2="210" className="chart-grid"/><text x="3" y="44" className="chart-tick">1.00</text><text x="3" y="129" className="chart-tick">0.50</text><text x="3" y="214" className="chart-tick">0.00</text><polyline points={points} className="belief-line" />{selected.map((belief, i) => { const x = selected.length === 1 ? 42 : 42 + i * 540 / (selected.length - 1); const y = 210 - belief.p_active * 170; const acquisition = acquisitions.find((item) => item.time_utc === belief.state_time_utc); return <g key={`${belief.state_time_utc}-${i}`}><circle cx={x} cy={y} r="4.5" className={acquisition ? `evidence-point ${acquisition.outcome.toLowerCase()}` : 'belief-point'}><title>{`${utc(belief.state_time_utc)} · P(active) ${fmt(belief.p_active)}${acquisition ? ` · ${acquisition.outcome}` : ''}`}</title></circle></g>})}<text x="42" y="240" className="chart-tick">{utc(selected[0]?.state_time_utc)}</text><text x="600" y="240" textAnchor="end" className="chart-tick">{utc(selected.at(-1)?.state_time_utc)}</text></svg></div><p className="chart-axis-note">Probability · 0 to 1 <span>Time · UTC</span></p><div className="chart-table-toggle"><details><summary>View values as table</summary><DataTable label="Belief probability values" headers={['TIME (UTC)', 'P(ACTIVE)', 'EVIDENCE']}><>{selected.map((b, i) => <tr key={`${b.state_time_utc}-${i}`}><td className="mono">{utc(b.state_time_utc)}</td><td className="numeric">{fmt(b.p_active)}</td><td>{b.evidence_ids.length ? b.evidence_ids.join(', ') : 'Prior / prediction'}</td></tr>)}</></DataTable></details></div></> : <div className="chart-empty">No plotted values</div>}
      </section><section className="panel"><div className="panel-head"><div><div className="eyebrow">CURRENT SUMMARY</div><h2>Conditional flux</h2></div></div>{selected.at(-1) ? <><div className="flux-summary"><strong>{fmt(selected.at(-1)?.flux_median_kg_h, 0)}</strong><span>kg CH₄/h · conditional on active</span></div><div className="interval-row"><span>90% credible interval</span><strong>{fmt(selected.at(-1)?.flux_ci90_kg_h[0], 0)}–{fmt(selected.at(-1)?.flux_ci90_kg_h[1], 0)} kg/h</strong></div><div className="interval-track"><i /></div><div className="belief-details"><div><span>P(active)</span><strong>{fmt(selected.at(-1)?.p_active)}</strong></div><div><span>Entropy</span><strong>{fmt(selected.at(-1)?.entropy_bits)} bits</strong></div><div><span>Model version</span><strong>{selected.at(-1)?.model_version}</strong></div><div><span>Regime probabilities</span><strong>{Object.entries(selected.at(-1)?.regime_probs ?? {}).map(([k,v]) => `${k} ${fmt(v)}`).join(' · ')}</strong></div></div></> : <p className="muted">Insufficient evidence. Flux estimates are unavailable.</p>}</section></div>
      <section className="panel ledger"><div className="panel-head"><div><div className="eyebrow">EVIDENCE LEDGER</div><h2>Acquisition outcomes</h2></div><span className="count-badge">{acquisitions.length}</span></div>{acquisitions.length ? <DataTable label="Evidence and acquisition outcomes" headers={['TIME (UTC)', 'OUTCOME', 'FLUX', 'WIND ESTIMATE', 'PROVENANCE']}><>{acquisitions.map((a) => <tr key={a.id}><td className="mono">{utc(a.time_utc)}</td><td><Outcome outcome={a.outcome} /></td><td className="numeric">{a.measured_flux_kg_h == null ? '— (not measured)' : `${fmt(a.measured_flux_kg_h, 0)} kg/h`}</td><td className="numeric">{fmt(a.wind_estimate_m_s)} m/s</td><td><Provenance kind="SIMULATED_OBSERVATION" /></td></tr>)}</></DataTable> : <p className="muted panel-padding">No acquisitions are recorded for this source. No non-detection is inferred.</p>}</section>
    </>}
  </div>
}
function Outcome({ outcome }: { outcome: string }) {
  const copy: Record<string, string> = { DETECTION: 'DETECTION', VALID_NON_DETECTION: 'VALID NON-DETECTION', INVALID_ACQUISITION: 'INVALID ACQUISITION', NOT_OBSERVED: 'NOT OBSERVED' }
  return <span className={`outcome outcome-${outcome.toLowerCase()}`}><i aria-hidden="true" />{copy[outcome] ?? outcome}</span>
}

function Planner({ run }: { run: RunRecord }) {
  const [revision, setRevision] = useState<number | null>(null)
  const plans = [...run.plans].sort((a, b) => a.revision - b.revision)
  const plan = plans.find((p) => p.revision === revision) ?? plans.at(-1)
  useEffect(() => { if (plan) setRevision(plan.revision) }, [run.run_id, plans.length])
  const utilities = run.utilities.filter((u) => u.plan_revision === plan?.revision).sort((a, b) => b.utility - a.utility)
  const selectedIds = new Set(plan?.selected_window_ids ?? [])
  const windows = new Map(run.windows.map((w) => [w.id, w]))
  const previous = plan ? plans.find((p) => p.revision === plan.revision - 1) : undefined
  const selectionKeys = (selections: Plan['selections']) => selections.map((selection) => `${selection.window_id} · ${selection.option_id}`)
  const changed = previous ? { added: selectionKeys(plan!.selections).filter((id) => !selectionKeys(previous.selections).includes(id)), removed: selectionKeys(previous.selections).filter((id) => !selectionKeys(plan!.selections).includes(id)) } : null
  return <div className="page"><SectionTitle eyebrow="E / PLAN REVIEW" title="Planner decisions" description="Recorded utility values, solver status, and revision causes. This view does not recompute a schedule." right={plans.length > 0 && <label className="select-control">PLAN REVISION<select value={plan?.revision ?? ''} onChange={(e) => setRevision(Number(e.target.value))}>{plans.map((p) => <option key={p.revision} value={p.revision}>Revision {p.revision}</option>)}</select></label>} />
    {!plan ? <Empty title="No plans in this run" detail="Planner decisions are available when plan records are present in run.json." /> : <>
      <div className="plan-summary"><div><span className="eyebrow">POLICY</span><strong>{plan.policy_id}</strong></div><div><span className="eyebrow">SOLVER</span><strong><span className={`solver-pill ${plan.solver_status.toLowerCase()}`}>{plan.solver_status}</span></strong></div><div><span className="eyebrow">OBJECTIVE</span><strong>{plan.objective_value == null ? 'Unavailable' : fmt(plan.objective_value)} <small>bits-equivalent</small></strong></div><div><span className="eyebrow">SOLVE TIME</span><strong>{fmt(plan.runtime_s, 3)} s</strong></div><div><span className="eyebrow">VALIDATION</span><strong>{plan.validation_ok == null ? 'Unavailable' : plan.validation_ok ? 'Passed' : 'Violations'}</strong></div></div>
      <div className="notice notice-cause"><div className="cause-icon" aria-hidden="true">↻</div><div><span className="eyebrow">REVISION {plan.revision} · CAUSE</span><strong>{plan.cause}</strong><span className="mono cause-time">{utc(plan.created_at_sim_utc)}</span></div></div>
      {changed && <section className="panel diff-panel"><div className="panel-head"><div><div className="eyebrow">REVISION DIFF</div><h2>Decision changes from revision {previous?.revision}</h2></div><span className="count-badge">{changed.added.length + changed.removed.length} changes</span></div><div className="diff-columns"><div><span className="eyebrow">ADDED</span>{changed.added.length ? changed.added.map((id) => <div className="diff-item added" key={id}>+ {id}</div>) : <span className="muted">No additions</span>}</div><div><span className="eyebrow">REMOVED</span>{changed.removed.length ? changed.removed.map((id) => <div className="diff-item removed" key={id}>− {id}</div>) : <span className="muted">No removals</span>}</div></div></section>}
      <div className="planner-layout"><section className="panel"><div className="panel-head"><div><div className="eyebrow">CANDIDATE UTILITIES</div><h2>{utilities.length} recorded candidates</h2></div></div>{utilities.length ? <DataTable label="Planner candidate utilities" headers={['CANDIDATE', 'EIG', 'P(VALID)', 'UTILITY', 'SELECTION']}><>{utilities.map((u) => <tr key={u.window_id}><td className="mono">{u.window_id}<span className="subcell">{windows.get(u.window_id)?.source_id ?? 'Source unavailable'}</span></td><td className="numeric">{fmt(u.expected_info_gain_bits, 4)} bits</td><td className="numeric">{fmt(u.p_valid_forecast)}</td><td className="numeric">{fmt(u.utility, 4)}</td><td>{selectedIds.has(u.window_id) ? <span className="state-label good">SELECTED</span> : <span className="muted">NOT SELECTED</span>}</td></tr>)}</></DataTable> : <p className="muted panel-padding">No utility records for this revision.</p>}</section>
        <aside className="panel selected-panel"><div className="panel-head"><div><div className="eyebrow">SELECTED SCHEDULE</div><h2>{plan.selections.length} options</h2></div></div>{plan.selections.length ? <ol>{plan.selections.map((selection, index) => { const w = windows.get(selection.window_id); const option = w?.options.find((item) => item.option_id === selection.option_id); return <li key={selection.option_id}><span className="selected-index">{String(index + 1).padStart(2, '0')}</span><div><strong className="mono">{selection.option_id}</strong><span>{w && option ? `${w.spacecraft_id} · ${w.source_id} · ${utc(option.start_utc)}` : 'Window details unavailable'}</span></div></li> })}</ol> : <p className="muted">The recorded plan selected no options.</p>}</aside></div>
      <div className="section-footer"><span>OBJECTIVE WEIGHTS <code>{Object.entries(plan.objective_weights).map(([k,v]) => `${k}: ${fmt(v, 3)}`).join(' · ') || 'Unavailable'}</code></span><span>BOUND <code>{plan.best_bound == null ? 'Unavailable' : fmt(plan.best_bound)}</code></span></div>
    </>}
  </div>
}

function Comparison({ run, benchmarks, state }: { run: RunRecord; benchmarks: BenchmarkRow[]; state: string }) {
  const rows = benchmarks
  const cols = rows.length ? Object.keys(rows[0]) : []
  const sampleCount = rows.reduce((max, row) => Math.max(max, Number(row.seed_count ?? row.n_seeds ?? row.seeds ?? 0) || 0), 0)
  return <div className="page"><SectionTitle eyebrow="F / EVALUATION" title="Policy comparison" description="Benchmark summaries are read from evaluator output. No policy ranking is inferred in the browser." />
    <div className="notice notice-neutral"><strong>RUN SCOPE</strong><span>This artifact contains policy <code>{run.policy_id}</code> at seed <code>{run.seed}</code>. A single run cannot establish comparative performance.</span></div>
    {state === 'ready' && rows.length ? <><div className="metrics-grid compare-metrics"><Metric label="POLICY GROUPS" value={fmt(new Set(rows.map((r) => r.policy_id ?? r.policy ?? '')).size, 0)} note="as present in benchmark file"/><Metric label="SEEDS" value={sampleCount ? fmt(sampleCount, 0) : 'Not recorded'} note="maximum declared per row"/><Metric label="COMPARISON STATUS" value={sampleCount < 10 ? 'Insufficient samples' : 'Results available'} note="minimum 10 seeds for inferential display"/><Metric label="RUN FAILURES" value={String(rows.reduce((n, r) => n + (Number(r.failures ?? r.run_failures ?? 0) || 0), 0))} note="reported by evaluator"/></div>
      {sampleCount < 10 && <div className="notice notice-warn"><strong>INSUFFICIENT SAMPLES</strong><span>Fewer than 10 seeds are recorded. Treat these values as descriptive; no inferential conclusion is shown.</span></div>}
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">EVALUATOR ARTIFACT</div><h2>Benchmark results</h2></div><span className="count-badge">{rows.length} rows</span></div><DataTable label="Benchmark result rows" headers={cols.map((c) => c.replaceAll('_', ' ').toUpperCase())}><>{rows.map((row, i) => <tr key={i}>{cols.map((col) => <td key={col} className={/seed|count|n_|runtime|score|brier|latency|rate|recall|coverage/i.test(col) ? 'numeric' : ''}>{row[col] || '—'}</td>)}</tr>)}</></DataTable></section>
    </> : <Empty title="Benchmark results unavailable" detail="No evaluator benchmark-results.csv is present in the artifact archive. Run comparison metrics and confidence intervals will appear here when the evaluator writes them." />}
    <div className="metric-notes"><div><strong>Brier score</strong><span>Lower is better; measures probability error against scored hidden truth.</span></div><div><strong>Corroboration latency</strong><span>Lower is faster corroboration; never-corroborated sources remain right-censored.</span></div><div><strong>Valid acquisition share</strong><span>Higher means a larger fraction of attempts returned usable observations.</span></div></div>
  </div>
}

function Method({ run }: { run: RunRecord }) {
  const copy = async () => { await navigator.clipboard.writeText(`python -m aether.cli simulate --config <pinned-config-path> --policies ${run.policy_id} --seed ${run.seed}`) }
  return <div className="page methodology"><SectionTitle eyebrow="G / METHODS & PROVENANCE" title="How to read this run" description="Configuration identity, record provenance, and limitations attached to the archived output." />
    <div className="method-grid"><section className="panel"><div className="panel-head"><div><div className="eyebrow">REPRODUCIBILITY</div><h2>Run identity</h2></div></div><dl className="key-values"><dt>Run ID</dt><dd className="mono">{run.run_id}</dd><dt>Scenario</dt><dd>{run.scenario_id} · {run.family}</dd><dt>Seed</dt><dd className="mono">{run.seed}</dd><dt>Model config SHA-256</dt><dd className="mono hash-value">{run.model_config_hash}</dd><dt>Truth config SHA-256</dt><dd className="mono hash-value">{run.truth_config_hash}</dd><dt>Code version</dt><dd className="mono">{run.code_version}</dd></dl><button className="button" onClick={() => void copy()} title="Copies a command template; replace the config placeholder with the pinned file path">Copy reproduction command template</button><p className="fine-print">The run record does not include its config file path or package lock. Replace the placeholder with the pinned config used to create this artifact.</p></section>
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">PROVENANCE CLASSES</div><h2>Evidence labels</h2></div></div><div className="provenance-list"><div><Provenance kind="REAL_OBSERVATION"/><span>Provider published historic observation. No real plume records are included in this run contract.</span></div><div><Provenance kind="MODEL_INFERENCE"/><span>Belief state estimated by the model from admissible evidence.</span></div><div><Provenance kind="SIMULATED_OBSERVATION"/><span>Virtual acquisition generated by the simulator.</span></div><div><Provenance kind="SIMULATED_GROUND_TRUTH"/><span>Evaluator only. Hidden truth is not included in this run record.</span></div></div></section></div>
    <section className="panel method-equations"><div className="panel-head"><div><div className="eyebrow">INTERPRETATION</div><h2>Scope and limitations</h2></div></div><div className="method-columns"><div><h3>What this artifact contains</h3><p>One simulated policy run, candidate windows, recorded solver plans, simulated acquisition outcomes and model belief snapshots. Values are shown from the stored records.</p></div><div><h3>What this artifact does not establish</h3><p>It does not show real satellite tasking, verified source attribution, measured emissions reduction, or comparative policy performance. Hidden simulated truth is scored separately.</p></div><div><h3>Missing values</h3><p>A blank or unavailable value remains unavailable. Invalid acquisitions and unobserved periods are not treated as valid non-detections.</p></div></div></section>
    <div className="method-citation"><span className="method-mark">i</span><span>Parameter and method references are maintained in <code>Implementation/Parameter_Register.md</code> and the project requirements document. Data license details must accompany any real observation artifact.</span></div>
  </div>
}
