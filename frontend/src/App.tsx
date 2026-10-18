import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { ScreenContent } from './ArchiveViews'
import { RunManifest } from './ArtifactEvidence'
import LiveContext from './LiveContext'
import type { BenchmarkProtocol, BenchmarkReport, BenchmarkRow, ProjectSnapshot, RunIndexItem, RunRecord } from './types'
import { parseRun } from './types'
import './mission-control.css'

export { readInterval } from './ArchiveViews'

const views = [
  ['overview', 'Mission overview', 'grid'], ['live', 'Satellite context', 'satellite'],
  ['sources', 'Sources & observations', 'pin'], ['windows', 'Observation windows', 'calendar'],
  ['planner', 'Mission planner', 'route'], ['beliefs', 'Belief history', 'wave'],
  ['comparison', 'Policy comparison', 'bars'], ['configuration', 'Scenario & instruments', 'satellite'], ['evidence', 'Evidence & exports', 'shield'],
] as const
type View = typeof views[number][0]
type LiveSummary = { status: string; computed_at_utc: string; satellites: { name: string }[]; feeds: { id: string; stale: boolean; retrieved_at_utc: string }[] }
type Performance = { run_id: string; measured: boolean; total_run_wall_s: number; windows_source: string }
type Research = { protocol_locked: boolean; capacity: { verdict: string; failing_pass: string } | null; synthetic_discriminability_pilot: { overall_passed: boolean } | null }
const policyName = (id: string) => ({ adaptive_eig: 'Adaptive information gain', largest_first: 'Largest source first', greedy_eig: 'Greedy information gain' }[id] ?? id.replaceAll('_', ' '))
const format = (value: number | undefined, digits = 0) => value === undefined || !Number.isFinite(value) ? '—' : new Intl.NumberFormat('en', { maximumFractionDigits: digits }).format(value)
const utc = (value: string | undefined) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toISOString().replace('T', ' ').replace('.000Z', ' UTC') : 'Unavailable'

function Icon({ name, className = '' }: { name: string; className?: string }) {
  const paths: Record<string, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    satellite: <><path d="m9 9 6 6m-9-3-3 3 6 6 3-3m0-12 3-3 6 6-3 3M8 8l8 8-4 4-8-8z" /><path d="M16 17a5 5 0 0 0 5-5" /></>,
    pin: <><path d="M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 0 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4m8-4v4M7 14h3m4 0h3m-10 4h3" /></>,
    route: <><circle cx="5" cy="5" r="2" /><circle cx="19" cy="19" r="2" /><path d="M5 7v8a4 4 0 0 0 4 4h8M7 5h8a4 4 0 0 1 4 4v3m-3-3 3 3 3-3" /></>,
    wave: <path d="M2 12h4l3-8 5 16 3-8h5" />,
    bars: <><path d="M4 21V11m8 10V3m8 18V7" /><path d="M2 21h20" /></>,
    shield: <><path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6z" /><path d="m8 12 3 3 5-6" /></>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" /></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6 6a8 8 0 0 1 14 6M4 12a8 8 0 0 0 14 6" /></>,
  }
  return <svg className={className} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.grid}</svg>
}

async function get<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, cache: 'no-store', headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`)
  return response.json() as Promise<T>
}
function currentView(): View {
  const value = new URLSearchParams(location.search).get('view')
  return views.some(([key]) => key === value) ? value as View : 'overview'
}

export default function App() {
  const [view, setView] = useState<View>(currentView)
  const [menu, setMenu] = useState(false)
  const [index, setIndex] = useState<RunIndexItem[]>([])
  const [runId, setRunId] = useState(new URLSearchParams(location.search).get('run') ?? '')
  const [run, setRun] = useState<RunRecord | null>(null)
  const [runLoading, setRunLoading] = useState(true)
  const [runError, setRunError] = useState('')
  const [project, setProject] = useState<ProjectSnapshot | null>(null)
  const [live, setLive] = useState<LiveSummary | null>(null)
  const [rows, setRows] = useState<BenchmarkRow[]>([])
  const [report, setReport] = useState<BenchmarkReport | null>(null)
  const [protocol, setProtocol] = useState<BenchmarkProtocol | null>(null)
  const [performance, setPerformance] = useState<Performance | null>(null)
  const [resourceError, setResourceError] = useState<string[]>([])
  const [refreshing, setRefreshing] = useState(false)
  const [runVersion, setRunVersion] = useState(0)
  const [research, setResearch] = useState<Research | null>(null)

  const navigate = useCallback((next: View, sourceId?: string) => {
    setView(next); setMenu(false)
    const url = new URL(location.href); url.searchParams.set('view', next)
    if (sourceId) url.searchParams.set('source', sourceId)
    else if (next !== 'sources' && next !== 'beliefs') url.searchParams.delete('source')
    history.pushState(null, '', url)
    document.getElementById('mission-main')?.focus()
  }, [])
  const refresh = useCallback(async (signal?: AbortSignal) => {
    setRefreshing(true)
    const endpoints = ['/api/runs', '/api/project', '/api/live-context', '/api/benchmark-results.csv', '/api/benchmark-confidence-intervals.json', '/api/benchmark-protocol', '/api/research-status']
    const results = await Promise.allSettled(endpoints.map(url => get<unknown>(url, signal)))
    if (signal?.aborted) return
    const failures: string[] = []
    results.forEach((result, i) => { if (result.status === 'rejected') failures.push(endpoints[i]) })
    const value = <T,>(i: number): T | null => results[i].status === 'fulfilled' ? (results[i] as PromiseFulfilledResult<T>).value : null
    const runs = value<RunIndexItem[]>(0)
    if (Array.isArray(runs) && runs.every(item => typeof item.run_id === 'string' && typeof item.policy_id === 'string')) {
      setIndex(runs)
      setRunId(previous => previous || runs.find(item => item.policy_id === 'adaptive_eig')?.run_id || runs[0]?.run_id || '')
      if (!runs.length) { setRunLoading(false); setRunError('No recorded runs are available in this deployment.') }
    } else { setRunError('The run archive is unavailable. Satellite context can still be opened.'); setRunLoading(false) }
    const snapshot = value<ProjectSnapshot>(1); setProject(snapshot?.scenario?.id ? snapshot : null)
    const feeds = value<LiveSummary>(2); setLive(feeds && Array.isArray(feeds.satellites) && Array.isArray(feeds.feeds) ? feeds : null)
    const benchmark = value<BenchmarkRow[]>(3); setRows(Array.isArray(benchmark) ? benchmark : [])
    const intervals = value<BenchmarkReport>(4); setReport(intervals && Array.isArray(intervals.comparisons) && typeof intervals.protocol_locked === 'boolean' ? intervals : null)
    const spec = value<BenchmarkProtocol>(5); setProtocol(spec && Array.isArray(spec.primary_comparison) ? spec : null)
    const gates = value<Research>(6); setResearch(gates && typeof gates.protocol_locked === 'boolean' ? gates : null)
    setResourceError(failures); setRefreshing(false); setRunVersion(previous => previous + 1)
  }, [])

  useEffect(() => { const controller = new AbortController(); void refresh(controller.signal); return () => controller.abort() }, [refresh])
  useEffect(() => {
    if (!runId) return
    const controller = new AbortController()
    setRunLoading(true); setRunError(''); setRun(null); setPerformance(null)
    get<unknown>(`/api/runs/${encodeURIComponent(runId)}`, controller.signal).then(value => {
      const parsed = parseRun(value)
      if (!controller.signal.aborted) { setRun(parsed); setRunLoading(false) }
    }).catch(error => { if (!controller.signal.aborted) { setRunError(error.message); setRunLoading(false) } })
    get<Performance>(`/api/runs/${encodeURIComponent(runId)}/performance.json`, controller.signal).then(value => {
      if (!controller.signal.aborted && value.run_id === runId && value.measured === true && Number.isFinite(value.total_run_wall_s)) setPerformance(value)
    }).catch(() => { /* A missing performance sidecar stays unavailable. */ })
    return () => controller.abort()
  }, [runId, runVersion])
  useEffect(() => {
    const onPop = () => { setView(currentView()); const requested = new URLSearchParams(location.search).get('run'); if (requested) setRunId(requested) }
    window.addEventListener('popstate', onPop); return () => window.removeEventListener('popstate', onPop)
  }, [])
  useEffect(() => { document.title = `${views.find(([key]) => key === view)?.[1]} · AETHER` }, [view])
  useEffect(() => { const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenu(false) }; window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close) }, [])
  const chooseRun = (id: string) => {
    setRunId(id)
    const url = new URL(location.href); url.searchParams.set('run', id); history.replaceState(null, '', url)
  }
  const selectedView = views.find(([key]) => key === view)!
  const screen = ({ sources: 'B', windows: 'C', planner: 'E', beliefs: 'D', comparison: 'F', evidence: 'G', configuration: 'A' } as const)[view as Exclude<View, 'overview' | 'live'>]
  const violations = run?.validations.reduce((sum, item) => sum + item.violations.length, 0)
  const feedsReady = !!live?.feeds.length && live.feeds.every(feed => !feed.stale)

  return <div className="mc-shell">
    <a className="skip-link" href="#mission-main">Skip to workspace</a>
    <aside className={`mc-sidebar ${menu ? 'mc-menu-open' : ''}`} aria-label="Workspace navigation">
      <a href="/?view=overview" className="mc-brand" onClick={event => { event.preventDefault(); navigate('overview') }}><span className="mc-brand-symbol">A</span><span>AETHER<small>EARTH OBSERVATION LAB</small></span></a>
      <div className="mc-workspace-label">MISSION WORKSPACE <span>01</span></div>
      <nav>{views.map(([key, label, icon]) => <button key={key} className={`mc-nav ${view === key ? 'is-active' : ''}`} aria-current={view === key ? 'page' : undefined} onClick={() => navigate(key)}><Icon name={icon} /><span>{label}</span>{key === 'live' && <span className="mc-nav-badge">FEEDS</span>}</button>)}</nav>
      <div className="mc-sidebar-bottom"><div className="mc-lab-note"><Icon name="shield" /><strong>Traceable by design</strong><p>Every observation, plan and input keeps its provenance.</p></div><span className="mc-version">RESEARCH PROTOTYPE <span>v{run?.code_version ?? '0.1.0'}</span></span></div>
    </aside>
    <div className="mc-workspace">
      <header className="mc-topbar"><button className="mc-menu-toggle" onClick={() => setMenu(!menu)} aria-label="Toggle navigation" aria-expanded={menu}>☰</button><div className="mc-breadcrumb">Workspace <span>/</span><strong>{selectedView[1]}</strong></div><div className="mc-topbar-actions"><span className={`mc-feed-status ${feedsReady ? 'ready' : ''}`}><span />{feedsReady ? 'Provider cache available' : 'Provider cache unavailable or stale'}</span><button className="mc-icon-button" aria-label="Refresh connected data" disabled={refreshing} onClick={() => void refresh()}><Icon name="refresh" /></button><a className="mc-api-link" href="/api/docs" target="_blank" rel="noreferrer">API ↗</a></div></header>
      <div className={`mc-mode-strip ${view === 'live' ? 'provider' : ''}`}><span>{view === 'live' ? 'REAL PROVIDER INPUTS' : 'SIMULATED MISSION'}</span><p>{view === 'live' ? 'Published orbital elements · modeled positions · catalogue metadata' : run?.input_dataset ? 'Historical EMIT locations · virtual spacecraft · recorded simulation' : 'Unpinned or synthetic source context · virtual spacecraft · recorded simulation'}</p><strong>{view === 'live' ? 'NO LIVE TELEMETRY' : 'NO REAL SATELLITE TASKING'}</strong></div>
      <main id="mission-main" tabIndex={-1} className="mc-main">
        {view === 'live' ? <LiveContext embedded /> : <>
          <div className="mc-run-toolbar"><div><span className="mc-caption">ACTIVE REPLAY</span><label className="sr-only" htmlFor="mission-run">Select simulation policy run</label><select id="mission-run" value={runId} onChange={event => chooseRun(event.target.value)}>{!index.length && <option value="">No recorded runs</option>}{index.map(item => <option key={item.run_id} value={item.run_id}>{policyName(item.policy_id)} · seed {item.seed}</option>)}</select></div><div className="mc-run-meta"><span>{run?.family.replaceAll('_', ' ') ?? 'Loading scenario'}</span><span>{project?.scenario.horizon_hours ?? '—'} h horizon</span>{run && <a className="mc-export" href={`/api/runs/${encodeURIComponent(run.run_id)}/export`}><Icon name="download" />Export evidence</a>}</div></div>
          {runLoading && <div className="mc-loading" role="status"><span className="mc-loading-bar" /><h2>Loading the recorded mission</h2><p>Reading sources, schedules and independent validations.</p></div>}
          {runError && <div className="mc-error" role="alert"><h2>Run could not be loaded</h2><p>{runError}</p><button onClick={() => void refresh()}>Reconnect data</button></div>}
          {!runLoading && run && (view === 'overview' ? <Dashboard run={run} project={project} live={live} performance={performance} report={report} research={research} navigate={navigate} violations={violations ?? 0} resourceError={resourceError} /> : view === 'configuration' ? <Configuration project={project} /> : <div className="mc-archive-view"><ScreenContent screen={screen} run={run} benchmarks={rows} benchmarkState={rows.length ? 'ready' : 'empty'} report={report} reportState={report ? 'ready' : 'empty'} protocol={protocol} />{view === 'evidence' && <><ResearchStatus research={research} /><section className="mc-evidence-actions"><a className="mc-primary" href={`/api/runs/${encodeURIComponent(run.run_id)}/export`}><Icon name="download" />Download verified run export</a><a href={`/api/runs/${encodeURIComponent(run.run_id)}/performance.json`} target="_blank" rel="noreferrer">Measured timing JSON ↗</a></section></>}</div>)}
        </>}
        <footer className="mc-footer"><span>AETHER / Observation planning research</span><span>{view === 'live' ? 'Provider metadata + propagated estimates' : 'Recorded evidence · UTC · reproducible inputs'}</span></footer>
      </main>
    </div>
  </div>
}

function Dashboard({ run, project, live, performance, report, research, navigate, violations, resourceError }: { run: RunRecord; project: ProjectSnapshot | null; live: LiveSummary | null; performance: Performance | null; report: BenchmarkReport | null; research: Research | null; navigate: (view: View, sourceId?: string) => void; violations: number; resourceError: string[] }) {
  const [selected, setSelected] = useState('')
  const source = run.sources.find(item => item.id === selected) ?? run.sources[0]
  const bbox = project?.scenario.region.bbox_wgs84
  const bounds = bbox ?? [Math.min(...run.sources.map(s => s.lon)) - 0.1, Math.min(...run.sources.map(s => s.lat)) - 0.1, Math.max(...run.sources.map(s => s.lon)) + 0.1, Math.max(...run.sources.map(s => s.lat)) + 0.1]
  const latestBelief = source ? [...run.beliefs].reverse().find(item => item.source_id === source.id) : undefined
  const outcomes = ['DETECTION', 'VALID_NON_DETECTION', 'INVALID_ACQUISITION', 'NOT_OBSERVED'] as const
  const counts = outcomes.map(outcome => ({ outcome, count: run.acquisitions.filter(a => a.outcome === outcome).length }))
  const validWindows = run.windows.filter(item => item.feasible).length
  const recentEvents = run.events.slice(-4).reverse()
  return <div className="mc-dashboard">
    <section className="mc-page-heading"><div><div className="mc-kicker">PERMIAN BASIN / MISSION WORKSPACE</div><h1>A clearer view of what to observe next.</h1><p>Follow the evidence from historical methane observations to independently checked simulation plans.</p></div><button className="mc-primary" onClick={() => navigate('planner')}>Open mission planner <Icon name="arrow" /></button></section>
    <section className="mc-stats" aria-label="Recorded mission metrics">
      <Stat title="Plume-seeded locations" value={format(run.input_dataset?.seeded_source_count ?? run.sources.filter(s => s.seeded_from_plume_id !== null).length)} detail={`${format(run.input_dataset?.uniform_fill_count ?? run.sources.filter(s => s.seeded_from_plume_id === null).length)} uniform-fill locations`} kind="real" label="HISTORICAL INPUT" />
      <Stat title="Feasible windows" value={format(validWindows)} detail={`of ${format(run.windows.length)} generated windows`} kind="model" label="MODELED GEOMETRY" />
      <Stat title="Checked plan revisions" value={`${run.validations.length}/${run.plans.length}`} detail={`${violations} recorded checker violations`} kind="sim" label="SIMULATED PLANS" />
      <Stat title="Recorded acquisitions" value={format(run.acquisitions.length)} detail={policyName(run.policy_id)} kind="sim" label="SIMULATED OUTCOMES" />
    </section>
    <div className="mc-main-grid">
      <section className="mc-card mc-source-card"><div className="mc-card-heading"><div><span className="mc-kicker">REGIONAL CONTEXT</span><h2>The sources behind the scenario</h2></div><span className="mc-chip">{run.sources.length} locations</span></div><div className="mc-coordinate-map"><svg viewBox="0 0 760 340" role="group" aria-label="Interactive longitude-latitude source plot; use the source selector below as a table alternative"><rect width="760" height="340" fill="#edf2ed" />{[0, 1, 2, 3, 4, 5, 6].map(i => <g key={i}><line x1={55 + i * 108} x2={55 + i * 108} y1="24" y2="300" stroke="#d7e1d8" /><line x1="55" x2="703" y1={24 + i * 46} y2={24 + i * 46} stroke="#d7e1d8" /></g>)}<text x="62" y="49" className="mc-map-label">PERMIAN BASIN</text><text x="62" y="66" className="mc-map-subtitle">HISTORICAL PLUME-SEEDED HYPOTHESES</text><text x="55" y="325" className="mc-map-axis">{format(bounds[0], 2)}°</text><text x="650" y="325" className="mc-map-axis">{format(bounds[2], 2)}°</text>{run.sources.map((s, i) => { const x = 55 + (s.lon - bounds[0]) / (bounds[2] - bounds[0]) * 648; const y = 300 - (s.lat - bounds[1]) / (bounds[3] - bounds[1]) * 276; return <g key={s.id} role="button" tabIndex={0} aria-label={`Select ${s.id}`} onClick={() => setSelected(s.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelected(s.id) } }} className="mc-map-point">{source?.id === s.id && <circle cx={x} cy={y} r="15" fill="#166b5b" opacity=".12" />}<circle cx={x} cy={y} r={source?.id === s.id ? 6 : 4} fill={source?.id === s.id ? '#125c4f' : '#719586'} stroke="#fff" strokeWidth="2" /><title>{s.id}: {s.lat}°, {s.lon}°</title><text x={x + 9} y={y + 4}>{String(i + 1).padStart(2, '0')}</text></g> })}</svg><div className="mc-map-legend"><span><i />Plume-seeded source hypothesis</span><span>Coordinate plot · no facility attribution</span></div></div><div className="mc-selected-source"><div><label className="mc-caption" htmlFor="overview-source">EXPLORE A SOURCE</label><select id="overview-source" value={source?.id ?? ''} onChange={event => setSelected(event.target.value)}>{run.sources.map(s => <option value={s.id} key={s.id}>{s.id} · {format(s.lat, 3)}°, {format(s.lon, 3)}°</option>)}</select></div><div><span className="mc-caption">FINAL MODEL P(ACTIVE)</span><strong>{latestBelief ? `${format(latestBelief.p_active * 100, 1)}%` : 'Unavailable'}</strong></div><button className="mc-text-button" onClick={() => navigate('sources', source?.id)}>Inspect source lineage <Icon name="arrow" /></button></div></section>
      <aside className="mc-right-stack"><section className="mc-card mc-connection-card"><div className="mc-card-heading"><div><span className="mc-kicker">DATA CONNECTIONS</span><h2>Know where every input comes from</h2></div></div><Connection icon="satellite" title="Satellite orbital context" subtitle={`${live?.satellites.length ?? 0} real spacecraft · propagated positions`} status={live?.status === 'available' ? live.feeds.some(f => f.stale) ? 'Stale cache' : 'Cached' : 'Unavailable'} onClick={() => navigate('live')} /><Connection icon="pin" title="NASA EMIT observations" subtitle={`${run.input_dataset?.record_count ?? '—'} pinned historical records`} status={run.input_dataset ? 'Hash-pinned' : 'Unpinned'} onClick={() => navigate('sources')} /><Connection icon="shield" title="Independent schedule checker" subtitle={`${run.validations.length} recorded validations`} status={violations ? 'Violations' : 'No violations'} onClick={() => navigate('evidence')} /><Connection icon="bars" title="Policy evaluation" subtitle={report ? `${report.n_seeds} seeds · development comparison` : 'Evaluator artifacts unavailable'} status={report ? report.preliminary ? 'Preliminary' : 'Available' : 'Unavailable'} onClick={() => navigate('comparison')} /></section><section className="mc-model-note"><span className="mc-kicker">A NOTE ON INTERPRETATION</span><h3>Real context. Simulated decisions.</h3><p>Historical observations supply locations. Satellite positions are estimates. The mission planner operates on a separate, reproducible virtual scenario.</p><button onClick={() => navigate('evidence')}>Read the method <Icon name="arrow" /></button></section></aside>
    </div>
    <div className="mc-bottom-grid"><section className="mc-card"><div className="mc-card-heading"><div><span className="mc-kicker">RECORDED EVIDENCE</span><h2>Every outcome keeps its meaning</h2></div><button className="mc-text-button" onClick={() => navigate('beliefs')}>Explore beliefs <Icon name="arrow" /></button></div><div className="mc-outcomes">{counts.map(({ outcome, count }) => <div key={outcome}><span className={`mc-outcome-dot ${outcome.toLowerCase()}`} /><strong>{count}</strong><span>{outcome.replaceAll('_', ' ').toLowerCase()}</span></div>)}</div><p className="mc-card-footnote">Invalid and unobserved acquisitions never become negative emission evidence.</p></section><section className="mc-card"><div className="mc-card-heading"><div><span className="mc-kicker">SIMULATION LOG</span><h2>Latest recorded events</h2></div><span className="mc-chip">UTC</span></div><div className="mc-events">{recentEvents.map(event => <div key={event.event_id}><span className="mc-event-mark" /><div><strong>{event.event_type.replaceAll('_', ' ').toLowerCase()}</strong><small>{event.actor}</small></div><time dateTime={event.event_time_sim_utc}>{utc(event.event_time_sim_utc).slice(11, 19)}</time></div>)}</div></section></div>
    <section className="mc-run-receipt"><div><Icon name="shield" /><span>Input manifest <code>{run.input_dataset?.manifest_sha256.slice(0, 16) ?? 'Unavailable'}</code></span></div><div>Measured run time <strong>{performance ? `${format(performance.total_run_wall_s, 1)} s` : 'Unavailable'}</strong></div><button className="mc-text-button" onClick={() => navigate('evidence')}>Open evidence <Icon name="arrow" /></button></section>
    <ResearchStatus research={research} />
    {!!resourceError.length && <details className="mc-resource-errors"><summary>Some connected resources are unavailable ({resourceError.length})</summary><ul>{resourceError.map(url => <li key={url}>{url}</li>)}</ul><p>Missing resources stay unavailable; no replacement scientific values are generated.</p></details>}
    <details className="mc-manifest-details"><summary>Inspect the complete input manifest</summary><RunManifest run={run} /></details>
  </div>
}

function Stat({ title, value, detail, kind, label }: { title: string; value: string; detail: string; kind: string; label: string }) {
  return <article className="mc-stat"><span className="mc-stat-title">{title}</span><strong>{value}</strong><p>{detail}</p><span className={`mc-provenance ${kind}`}>{label}</span></article>
}
function Connection({ icon, title, subtitle, status, onClick }: { icon: string; title: string; subtitle: string; status: string; onClick: () => void }) {
  const tone = status === 'Unavailable' || status === 'Stale cache' ? 'unavailable' : status === 'Preliminary' ? 'preliminary' : status === 'Violations' ? 'failed' : 'connected'
  return <button className="mc-connection" onClick={onClick}><span className="mc-connection-icon"><Icon name={icon} /></span><span className="mc-connection-copy"><strong>{title}</strong><small>{subtitle}</small></span><span className={`mc-connection-status ${tone}`}>{status}</span></button>
}

function ResearchStatus({ research }: { research: Research | null }) {
  return <section className="mc-research-status"><strong>RESEARCH ACCEPTANCE</strong><span>Protocol: {research ? research.protocol_locked ? 'locked' : 'unlocked' : 'unavailable'}</span><span>Recorded capacity gate: {research?.capacity?.verdict ?? 'unavailable'}</span><span>Synthetic discriminability pilot: {research?.synthetic_discriminability_pilot ? research.synthetic_discriminability_pilot.overall_passed ? 'passed' : 'failed' : 'unavailable'}</span><p>Gate artifacts have their own recorded scope. Development comparisons do not establish policy superiority or completed holdout acceptance.</p></section>
}

function Configuration({ project }: { project: ProjectSnapshot | null }) {
  if (!project) return <div className="mc-error"><h2>Project configuration unavailable</h2><p>The recorded run can still be inspected in the other views.</p></div>
  return <div className="mc-archive-view"><div className="section-title"><div><div className="mc-kicker">PROJECT CONFIGURATION</div><h1>Scenario & instruments</h1><p>Current project profiles. Recorded run identity and input hashes remain in Evidence & exports.</p></div></div><section className="mc-card"><div className="mc-card-heading"><div><span className="mc-kicker">VIRTUAL FLEET</span><h2>{project.spacecraft.length} simulated spacecraft profiles</h2></div><span className="mc-provenance sim">VIRTUAL ONLY</span></div><div className="table-wrap" tabIndex={0} role="region" aria-label="Virtual spacecraft configuration"><table><caption className="sr-only">Current configured virtual spacecraft, separate from real Landsat context</caption><thead><tr><th scope="col">Spacecraft</th><th scope="col">Orbit altitude</th><th scope="col">Inclination</th><th scope="col">Sensors</th><th scope="col">Maximum acquisitions / orbit</th></tr></thead><tbody>{project.spacecraft.map(s => <tr key={s.id}><th scope="row">{s.id}</th><td>{String(s.orbit.altitude_km)} km</td><td>{String(s.orbit.inclination_deg)}°</td><td>{s.sensor_ids.join(', ')}</td><td>{s.resources.max_acquisitions_per_orbit}</td></tr>)}</tbody></table></div></section><div className="mc-bottom-grid">{project.sensors.map(sensor => <section className="mc-card" key={sensor.id}><div className="mc-card-heading"><div><span className="mc-kicker">VIRTUAL SENSOR PROFILE</span><h2>{sensor.id}</h2></div><span className="mc-chip">{sensor.calibration_status}</span></div><dl className="key-values"><dt>Reference Q50 / Q90</dt><dd>{sensor.q50_ref_kg_h} / {sensor.q90_ref_kg_h} kg/h</dd><dt>Nadir GSD</dt><dd>{sensor.gsd_nadir_m} m</dd><dt>Exposure</dt><dd>{sensor.exposure_seconds} s</dd><dt>Minimum sun elevation</dt><dd>{sensor.min_sun_elevation_deg}°</dd><dt>Reference wind</dt><dd>{sensor.ref_wind_m_s} m/s</dd></dl></section>)}<section className="mc-card"><div className="mc-card-heading"><div><span className="mc-kicker">PLANNER SETUP</span><h2>Reproducible optimization</h2></div></div><dl className="key-values"><dt>Lookahead</dt><dd>{project.planner.lookahead_hours} h</dd><dt>Utility</dt><dd>{project.planner.utility}</dd><dt>Solver mode</dt><dd>{String(project.planner.solver.mode)}</dd><dt>Replan triggers</dt><dd>{project.planner.replan_on.join(', ')}</dd><dt>Protocol lock</dt><dd>{project.benchmark_protocol.locked ? 'Locked' : 'Unlocked'}</dd></dl></section></div></div>
}
