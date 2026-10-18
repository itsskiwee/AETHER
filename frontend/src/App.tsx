import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ScreenContent } from './ArchiveViews'
import { RunManifest } from './ArtifactEvidence'
import type { BenchmarkProtocol, BenchmarkReport, BenchmarkRow, ProjectSnapshot, RunIndexItem, RunRecord } from './types'
import { parseRun } from './types'
import { craftName } from './fleet'
import './console.css'

export { readInterval } from './ArchiveViews'

// UI-11 console. Pages are grouped by what they show: REAL provider data (EMIT records, NASA
// catalogue, CelesTrak passes) or the SIMULATED mission (virtual fleet, planner, beliefs, tests).
const views = [
  ['overview', 'Overview', 'grid', 'real'],
  ['observations', 'Real observations', 'pin', 'real'],
  ['passes', 'Real satellite passes', 'calendar', 'real'],
  ['planner', 'Planner', 'route', 'sim'],
  ['beliefs', 'Beliefs', 'wave', 'sim'],
  ['comparison', 'Policy test', 'bars', 'sim'],
  ['setup', 'Setup', 'satellite', 'sim'],
  ['evidence', 'Evidence & exports', 'shield', 'sim'],
] as const
type View = typeof views[number][0]
const LEGACY: Record<string, View> = { live: 'passes', sources: 'observations', windows: 'passes', configuration: 'setup' }

type RealSat = { norad_id: number; name: string; role: string; retrieved_at_utc?: string; refresh_status: string; omm?: { EPOCH: string } }
type EmitRecord = { id: string; native_id: string; acquisition_time_utc: string; lat: number; lon: number; emission_rate_kg_h: number | null; emission_rate_uncertainty_kg_h: number | null; missing_rate_reason: string | null; provider: string; dataset_version: string }
type Granule = { title: string; time_start: string; updated: string; data_url: string | null }
type Pass = { norad_id: number; satellite: string; start_utc: string; end_utc: string; closest_utc: string; sites_in_swath: string[]; min_ground_distance_km: number; sun_elevation_deg: number; daylit: boolean }
type RealBundle = {
  built_at_utc: string
  real_satellites: RealSat[]
  emit_records: EmitRecord[]
  emit_recent: { url: string; retrieved_at_utc?: string; refresh_status: string; granules: Granule[] }
  real_passes: { from_utc: string; lookahead_hours: number; swath_km: Record<string, number>; note: string; passes: Pass[] }
}

const policyName = (id: string) => ({ adaptive_eig: 'Adaptive information gain', largest_first: 'Largest source first', greedy_eig: 'Greedy information gain', random_feasible: 'Random (reference)', oracle: 'Oracle-informed reference' }[id] ?? id.replaceAll('_', ' '))
const num = (value: number | null | undefined, digits = 0) => value === null || value === undefined || !Number.isFinite(value) ? '—' : new Intl.NumberFormat('en', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value)
const parse = (iso: string) => Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)
const utc = (iso: string | undefined) => iso && Number.isFinite(parse(iso)) ? new Date(parse(iso)).toISOString().replace('T', ' ').slice(0, 16) + ' UTC' : '—'
const day = (iso: string) => new Date(parse(iso)).toISOString().slice(0, 10)
function relative(ms: number) {
  const m = Math.round(Math.abs(ms) / 60000)
  const text = m < 60 ? `${m} min` : m < 48 * 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${Math.round(m / 1440)} days`
  return ms >= 0 ? `in ${text}` : `${text} ago`
}

function Icon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    satellite: <><path d="m9 9 6 6m-9-3-3 3 6 6 3-3m0-12 3-3 6 6-3 3M8 8l8 8-4 4-8-8z" /><path d="M16 17a5 5 0 0 0 5-5" /></>,
    pin: <><path d="M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 0 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4m8-4v4" /></>,
    route: <><circle cx="5" cy="5" r="2" /><circle cx="19" cy="19" r="2" /><path d="M5 7v8a4 4 0 0 0 4 4h8M7 5h8a4 4 0 0 1 4 4v3" /></>,
    wave: <path d="M2 12h4l3-8 5 16 3-8h5" />,
    bars: <><path d="M4 21V11m8 10V3m8 18V7" /><path d="M2 21h20" /></>,
    shield: <><path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6z" /><path d="m8 12 3 3 5-6" /></>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    download: <path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" />,
  }
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.grid}</svg>
}

async function get<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, cache: 'no-store', headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`)
  return response.json() as Promise<T>
}
function currentView(): View {
  const value = new URLSearchParams(location.search).get('view') ?? ''
  if (value in LEGACY) return LEGACY[value]
  return views.some(([key]) => key === value) ? value as View : 'overview'
}

const Tag = ({ kind }: { kind: 'real' | 'sim' }) => <span className={`cx-tag ${kind}`}>{kind === 'real' ? 'REAL DATA' : 'SIMULATION'}</span>
function Page({ kind, kicker, title, intro, children }: { kind: 'real' | 'sim'; kicker: string; title: string; intro: ReactNode; children: ReactNode }) {
  return <div className="cx-page"><header className="cx-page-head"><div><Tag kind={kind} /><span className="cx-kicker">{kicker}</span></div><h1>{title}</h1><p>{intro}</p></header>{children}</div>
}
const Card = ({ title, aside, children, className = '' }: { title?: string; aside?: ReactNode; children: ReactNode; className?: string }) => <section className={`cx-card ${className}`}>{(title || aside) && <div className="cx-card-head">{title && <h2>{title}</h2>}{aside}</div>}{children}</section>
const Stat = ({ label, value, note, kind }: { label: string; value: string; note: string; kind: 'real' | 'sim' }) => <div className={`cx-stat ${kind}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></div>

export default function App() {
  const [view, setView] = useState<View>(currentView)
  const [menu, setMenu] = useState(false)
  const [index, setIndex] = useState<RunIndexItem[]>([])
  const [runId, setRunId] = useState(new URLSearchParams(location.search).get('run') ?? '')
  const [run, setRun] = useState<RunRecord | null>(null)
  const [runError, setRunError] = useState('')
  const [project, setProject] = useState<ProjectSnapshot | null>(null)
  const [rows, setRows] = useState<BenchmarkRow[]>([])
  const [report, setReport] = useState<BenchmarkReport | null>(null)
  const [protocol, setProtocol] = useState<BenchmarkProtocol | null>(null)
  const [real, setReal] = useState<RealBundle | null>(null)
  const [realError, setRealError] = useState('')
  const [now, setNow] = useState(() => Date.now())
  const [failed, setFailed] = useState<string[]>([])
  const [evaluationLoaded, setEvaluationLoaded] = useState(false)
  const needsRealData = view === 'overview' || view === 'observations' || view === 'passes'
  const needsRunData = view === 'overview' || view === 'planner' || view === 'beliefs' || view === 'comparison' || view === 'evidence'
  const needsEvaluation = view === 'beliefs' || view === 'comparison' || view === 'evidence'
  const needsProject = view === 'setup'
  const needsClock = view === 'overview' || view === 'passes'
  const projectFailed = failed.includes('project')
  const fail = (what: string) => setFailed(f => f.includes(what) ? f : [...f, what])

  const navigate = useCallback((next: View) => {
    setView(next); setMenu(false)
    const url = new URL(location.href); url.searchParams.set('view', next); url.searchParams.delete('source')
    history.pushState(null, '', url)
    document.getElementById('cx-main')?.focus()
  }, [])

  useEffect(() => {
    if (!needsRealData || real || realError) return
    const controller = new AbortController()
    get<RealBundle>('/globe/globe-data.json', controller.signal)
      .then(value => { if (!controller.signal.aborted) setReal(value) })
      .catch(error => { if (!controller.signal.aborted) setRealError(String(error.message ?? error)) })
    return () => controller.abort()
  }, [needsRealData, real, realError])

  useEffect(() => {
    if (!needsRunData || index.length > 0 || runError) return
    const controller = new AbortController()
    get<RunIndexItem[]>('/api/runs', controller.signal).then(runs => {
      if (controller.signal.aborted) return
      setIndex(runs)
      setRunId(previous => previous || runs.find(item => item.policy_id === 'adaptive_eig')?.run_id || runs[0]?.run_id || '')
      if (!runs.length) setRunError('No recorded simulation runs in this deployment.')
    }).catch(() => {
      if (!controller.signal.aborted) setRunError('The simulation archive is unavailable. Real-data pages still work.')
    })
    return () => controller.abort()
  }, [needsRunData, index.length, runError])

  useEffect(() => {
    if (!needsProject || project || projectFailed) return
    const controller = new AbortController()
    get<ProjectSnapshot>('/api/project', controller.signal).then(value => {
      if (controller.signal.aborted) return
      if (value?.scenario?.id) setProject(value)
      else fail('project')
    }).catch(() => { if (!controller.signal.aborted) fail('project') })
    return () => controller.abort()
  }, [needsProject, project, projectFailed])

  useEffect(() => {
    if (!needsEvaluation || evaluationLoaded) return
    const controller = new AbortController()
    const { signal } = controller
    Promise.allSettled([
      get<BenchmarkRow[]>('/api/benchmark-results.csv', signal),
      get<BenchmarkReport>('/api/benchmark-confidence-intervals.json', signal),
      get<BenchmarkProtocol>('/api/benchmark-protocol', signal),
    ]).then(([rowResult, reportResult, protocolResult]) => {
      if (signal.aborted) return
      if (rowResult.status === 'fulfilled') setRows(Array.isArray(rowResult.value) ? rowResult.value : [])
      else fail('benchmark')
      if (reportResult.status === 'fulfilled') {
        setReport(Array.isArray(reportResult.value?.comparisons) ? reportResult.value : null)
      } else fail('benchmark')
      if (protocolResult.status === 'fulfilled') {
        setProtocol(Array.isArray(protocolResult.value?.primary_comparison) ? protocolResult.value : null)
      }
      setEvaluationLoaded(true)
    })
    return () => controller.abort()
  }, [needsEvaluation, evaluationLoaded])

  useEffect(() => {
    if (!needsRunData || !runId || run?.run_id === runId) return
    const controller = new AbortController()
    setRun(null)
    setRunError('')
    get<unknown>(`/api/runs/${encodeURIComponent(runId)}`, controller.signal).then(value => {
      if (!controller.signal.aborted) setRun(parseRun(value))
    }).catch(error => { if (!controller.signal.aborted) setRunError(error.message) })
    return () => controller.abort()
  }, [needsRunData, runId, run])

  useEffect(() => {
    if (!needsClock) return
    const id = window.setInterval(() => setNow(Date.now()), 30000)
    return () => window.clearInterval(id)
  }, [needsClock])
  useEffect(() => { const onPop = () => setView(currentView()); window.addEventListener('popstate', onPop); return () => window.removeEventListener('popstate', onPop) }, [])
  useEffect(() => { document.title = `${views.find(([key]) => key === view)?.[1]} · AETHER` }, [view])

  const selected = views.find(([key]) => key === view)!
  const kind = selected[3]
  const chooseRun = (id: string) => { setRunId(id); const url = new URL(location.href); url.searchParams.set('run', id); history.replaceState(null, '', url) }
  const runPicker = index.length > 0 && <label className="cx-run-picker"><span>Recorded simulation run</span><select value={runId} onChange={e => chooseRun(e.target.value)}>{index.map(item => <option key={item.run_id} value={item.run_id}>{policyName(item.policy_id)} · seed {item.seed}</option>)}</select></label>
  const needRun = (body: (r: RunRecord) => ReactNode) => run ? body(run) : <div className="cx-empty">{runError || 'Loading the recorded simulation…'}</div>

  return (
    <div className={`cx-shell ${menu ? 'menu-open' : ''}`}>
      <a className="skip-link" href="#cx-main">Skip to content</a>
      <aside className="cx-sidebar" aria-label="Navigation">
        <a className="cx-brand" href="/?view=globe"><b>AETHER</b><span>Earth observation planning research</span></a>
        <a className="cx-globe-link" href="/?view=globe"><Icon name="globe" /><span>3D globe</span></a>
        {(['real', 'sim'] as const).map(group => <nav key={group} aria-label={group === 'real' ? 'Real data' : 'Simulation'}>
          <div className={`cx-nav-group ${group}`}>{group === 'real' ? 'Real data' : 'Simulation'}</div>
          {views.filter(v => v[3] === group).map(([key, label, icon]) => <button key={key} className={`cx-nav ${view === key ? 'active' : ''}`} aria-current={view === key ? 'page' : undefined} onClick={() => navigate(key)}><Icon name={icon} /><span>{label}</span></button>)}
        </nav>)}
        <p className="cx-sidebar-note">Real data comes from NASA EMIT, NASA CMR and CelesTrak. Every planning decision is made in a reproducible simulation. AETHER does not task real satellites.</p>
      </aside>
      <div className="cx-workspace">
        <header className={`cx-strip ${kind}`}>
          <button className="cx-menu" onClick={() => setMenu(m => !m)} aria-label="Toggle navigation" aria-expanded={menu}>☰</button>
          <Tag kind={kind} />
          <span>{kind === 'real' ? 'Provider records and modelled satellite positions. No live telemetry.' : 'Virtual spacecraft, simulated outcomes, recorded and reproducible. No real satellite tasking.'}</span>
          {kind === 'sim' && runPicker}
        </header>
        <main id="cx-main" className="cx-main" tabIndex={-1}>
          {view === 'overview' && <Overview real={real} realError={realError} run={run} now={now} navigate={navigate} />}
          {view === 'observations' && <Observations real={real} realError={realError} />}
          {view === 'passes' && <Passes real={real} realError={realError} now={now} />}
          {view === 'planner' && needRun(r => <PlannerStory run={r} />)}
          {view === 'beliefs' && needRun(r => <Page kind="sim" kicker="How the planner's knowledge changes" title="Beliefs" intro={<>For every source, the model keeps a probability that it is emitting now and a range for how much. A detection pushes the probability up, a valid non-detection pushes it down, and a missing or cloudy look changes nothing. Pick a source below to follow its history.</>}><div className="cx-legacy"><ScreenContent screen="D" run={r} benchmarks={rows} benchmarkState={rows.length ? 'ready' : 'empty'} report={report} reportState={report ? 'ready' : 'empty'} protocol={protocol} /></div></Page>)}
          {view === 'comparison' && needRun(r => <PolicyTest run={r} rows={rows} report={report} protocol={protocol} failed={failed.includes('benchmark')} />)}
          {view === 'setup' && <Setup project={project} failed={failed.includes('project')} />}
          {view === 'evidence' && needRun(r => <Page kind="sim" kicker="Reproducibility" title="Evidence & exports" intro="Every recorded run can be downloaded as a hashed archive and re-verified offline. The manifest lists every input file and its SHA-256."><a className="cx-primary" href={`/api/runs/${encodeURIComponent(r.run_id)}/export`}><Icon name="download" /> Download verified run export</a><div className="cx-legacy"><ScreenContent screen="G" run={r} benchmarks={rows} benchmarkState={rows.length ? 'ready' : 'empty'} report={report} reportState={report ? 'ready' : 'empty'} protocol={protocol} /><RunManifest run={r} /></div></Page>)}
          <footer className="cx-footer"><span>AETHER · research prototype</span><span>Times in UTC · real-data bundle built {utc(real?.built_at_utc)}</span></footer>
        </main>
      </div>
    </div>
  )
}

function snapshotAge(real: RealBundle, now: number) {
  const built = parse(real.real_passes.from_utc)
  return { hours: (now - built) / 3600000, expired: now > built + real.real_passes.lookahead_hours * 3600000 }
}
function Freshness({ real, now }: { real: RealBundle; now: number }) {
  const age = snapshotAge(real, now)
  if (age.hours < 6) return null
  return <div className="cx-warn" role="status">{age.expired ? 'These pass predictions have expired' : `These pass predictions are ${num(age.hours)} h old`}. Run <code>python -m scripts.build_globe_data</code> and rebuild the console to refresh them.</div>
}

function nextPass(real: RealBundle, now: number) {
  return real.real_passes.passes.find(p => parse(p.closest_utc) > now && p.daylit)
}

function Overview({ real, realError, run, now, navigate }: { real: RealBundle | null; realError: string; run: RunRecord | null; now: number; navigate: (v: View) => void }) {
  const records = real?.emit_records ?? []
  const quantified = records.filter(r => r.emission_rate_kg_h !== null).length
  const latest = real?.emit_recent.granules[0]
  const next = real ? nextPass(real, now) : undefined
  const looks = run?.acquisitions.length ?? 0
  const violations = run ? run.validations.reduce((n, v) => n + v.violations.length, 0) : 0
  return <div className="cx-page">
    <header className="cx-page-head cx-head-row">
      <div><span className="cx-kicker">Permian Basin / methane observation planning</span><h1>Observation planning for the Permian Basin</h1>
        <p>Historical NASA EMIT observations and estimates from real satellite orbits provide the context. A reproducible simulation tests how a planner chooses the next site to observe.</p></div>
      <a className="cx-primary" href="/?view=globe"><Icon name="globe" /> View the globe</a>
    </header>
    {realError && <div className="cx-empty" role="alert">Real-data bundle unavailable: {realError}</div>}
    <section className="cx-stats" aria-label="Research snapshot">
      <Stat kind="real" label="Real EMIT plume observations" value={String(records.length || '—')} note={records.length ? `${quantified} with a provider emission rate · ${day(records.map(r => r.acquisition_time_utc).sort()[0])} to ${day(records.map(r => r.acquisition_time_utc).sort().slice(-1)[0])}` : 'Loading'} />
      <Stat kind="real" label="Newest EMIT plume granule over the Permian" value={latest ? day(latest.time_start) : '—'} note={latest ? `NASA CMR catalogue · ${real?.emit_recent.granules.length} newest listed` : real?.emit_recent.refresh_status ?? 'Loading'} />
      <Stat kind="real" label="Next daylit real pass over a plume site" value={next ? next.satellite : '—'} note={next ? `${relative(parse(next.closest_utc) - now)} · ${next.sites_in_swath.length} of 20 sites in swath` : real && snapshotAge(real, now).expired ? 'Pass snapshot expired: rebuild to refresh' : 'None in the look-ahead window'} />
      <Stat kind="sim" label="Simulated looks by the planner" value={run ? String(looks) : '—'} note={run ? `${policyName(run.policy_id)} · ${violations} schedule-checker violations` : 'Loading'} />
    </section>
    <div className="cx-two cx-overview-sections">
      <section className="cx-overview-section" aria-labelledby="cx-real-inputs">
        <div className="cx-overview-section-head"><div><span className="cx-kicker">Historical and current context</span><h2 id="cx-real-inputs">Real observations and orbits</h2></div></div>
        <ul className="cx-list">
          <li><b>20 EMIT plume records</b> (NASA LP DAAC, V002, 2023–2024), with times, locations and provider-reported rates when available. Each record is pinned by SHA-256. <button className="cx-link" onClick={() => navigate('observations')}>Browse records</button></li>
          <li><b>Recent EMIT plume granules</b> over the Permian Basin, listed in NASA's CMR catalogue.</li>
          <li><b>Satellite positions and passes</b> are propagated from published CelesTrak elements for the ISS, Landsat 8 and 9, and Sentinel-5P. They are estimates, not live telemetry. <button className="cx-link" onClick={() => navigate('passes')}>View passes</button></li>
        </ul>
      </section>
      <section className="cx-overview-section" aria-labelledby="cx-simulation">
        <div className="cx-overview-section-head"><div><span className="cx-kicker">Reproducible test</span><h2 id="cx-simulation">A separate simulated mission</h2></div></div>
        <ul className="cx-list">
          <li><b>Four virtual spacecraft</b> and a modelled sensor form the simulated fleet. They cannot command real satellites.</li>
          <li><b>Emissions and weather are simulated.</b> They provide the ground truth used to score each planner under the same conditions.</li>
          <li><b>The planner and its beliefs</b> are solved with OR-Tools CP-SAT and checked by an independent schedule checker. <button className="cx-link" onClick={() => navigate('planner')}>View the plan</button></li>
        </ul>
      </section>
    </div>
    <section className="cx-overview-status" aria-labelledby="cx-research-status">
      <div className="cx-overview-section-head"><div><span className="cx-kicker">Evidence snapshot / 18 Oct 2026</span><h2 id="cx-research-status">Research status</h2></div><button className="cx-link" onClick={() => navigate('comparison')}>Review evaluation →</button></div>
      <ul className="cx-list cx-status">
        <li><span className="cx-pill ok">Passed</span><span>Data provenance, orbit geometry, independent schedule checks (0 violations), belief updates and byte-identical replay.</span></li>
        <li><span className="cx-pill fail">Failed</span><span>Capacity on the 72 h scenario: one pass supports 2 looks; the minimum is 4.</span></li>
        <li><span className="cx-pill fail">Failed</span><span>Discriminability on the 72 h scenario: a truth-informed reference does not outperform random looks. A 168 h diagnostic fixes capacity but not discriminability (H3).</span></li>
        <li><span className="cx-pill wait">Pending</span><span>Protocol lock and held-out benchmark. No planner superiority claim is supported.</span></li>
      </ul>
    </section>
  </div>
}

function Observations({ real, realError }: { real: RealBundle | null; realError: string }) {
  const records = [...(real?.emit_records ?? [])].sort((a, b) => b.acquisition_time_utc.localeCompare(a.acquisition_time_utc))
  return <Page kind="real" kicker="NASA EMIT · Earth Surface Mineral Dust Source Investigation, on the ISS" title="Real observations" intro="These are real methane plume detections by NASA's EMIT imaging spectrometer. AETHER uses the 20 pinned records to place its source sites; it never treats them as present-day activity or as simulated truth.">
    {realError && <div className="cx-empty" role="alert">{realError}</div>}
    <Card title="20 pinned EMIT plume records, Permian Basin" aside={<span className="cx-chip">EMIT L2B CH4PLM V002 · SHA-256 pinned</span>}>
      <div className="cx-table" tabIndex={0} role="region" aria-label="Pinned EMIT plume records"><table>
        <thead><tr><th>Observed (UTC)</th><th>Plume ID</th><th>Latitude</th><th>Longitude</th><th>Emission rate</th><th>Provider</th></tr></thead>
        <tbody>{records.map(r => <tr key={r.id}><td>{utc(r.acquisition_time_utc)}</td><td className="mono">{r.native_id}</td><td>{num(r.lat, 4)}°</td><td>{num(r.lon, 4)}°</td>
          <td>{r.emission_rate_kg_h === null ? <span className="cx-muted">Not quantified ({(r.missing_rate_reason ?? 'not provided').replaceAll('_', ' ').toLowerCase()})</span> : <>{num(r.emission_rate_kg_h)} kg/h{r.emission_rate_uncertainty_kg_h !== null && <span className="cx-muted"> ± {num(r.emission_rate_uncertainty_kg_h)}</span>}</>}</td><td>{r.provider}</td></tr>)}</tbody>
      </table></div>
      <p className="cx-foot">The provider does not define the "±" value statistically, so AETHER records it as an uncertainty of unknown kind. A missing rate stays missing; it is never read as zero.</p>
    </Card>
    <Card title="Newest EMIT plume granules over the Permian (NASA CMR)" aside={<span className="cx-chip">{real?.emit_recent.refresh_status === 'OK' ? `Retrieved ${utc(real.emit_recent.retrieved_at_utc)}` : real?.emit_recent.refresh_status ?? 'Loading'}</span>}>
      <div className="cx-table" tabIndex={0} role="region" aria-label="Recent EMIT catalogue granules"><table>
        <thead><tr><th>Observed (UTC)</th><th>Granule</th><th>Data</th></tr></thead>
        <tbody>{real?.emit_recent.granules.map(g => <tr key={g.title}><td>{utc(g.time_start)}</td><td className="mono">{g.title}</td><td>{g.data_url ? <a href={g.data_url} target="_blank" rel="noreferrer">NASA file ↗</a> : '—'}</td></tr>)}</tbody>
      </table></div>
      <p className="cx-foot">Catalogue metadata only. A listed granule shows that EMIT reported a plume complex there on that date; downloading files needs a NASA Earthdata login.</p>
    </Card>
  </Page>
}

function Passes({ real, realError, now }: { real: RealBundle | null; realError: string; now: number }) {
  const passes = (real?.real_passes.passes ?? []).filter(p => parse(p.end_utc) > now - 3600000)
  const sats = real?.real_satellites ?? []
  const swath = real?.real_passes.swath_km ?? {}
  return <Page kind="real" kicker="CelesTrak orbital elements · SGP4 / Skyfield" title="Real satellite passes" intro={<>When will real Earth-observation satellites next fly over the 20 EMIT plume sites? A site counts when it falls inside the instrument's swath. Methane imaging in shortwave infrared needs sunlight, so night passes are marked. These are geometric opportunities from published orbits, not acquisitions and not tasking.</>}>
    {realError && <div className="cx-empty" role="alert">{realError}</div>}
    {real && <Freshness real={real} now={now} />}
    <div className="cx-sat-grid">{sats.map(s => {
      const next = passes.find(p => p.norad_id === s.norad_id && parse(p.closest_utc) > now)
      const age = s.omm ? (now - parse(s.omm.EPOCH)) / 3600000 : NaN
      return <Card key={s.norad_id} className="cx-sat"><span className="cx-kicker">{s.role}</span><h3>{s.name}</h3>
        <div className="cx-sat-next">{next ? <><strong>{relative(parse(next.closest_utc) - now)}</strong><span>{utc(next.closest_utc)} · {next.sites_in_swath.length} of 20 sites · {next.daylit ? 'daylight' : 'night'}</span></> : <><strong>No pass</strong><span>No site within {num((swath[String(s.norad_id)] ?? 0) / 2)} km of its ground track in the next {real?.real_passes.lookahead_hours} h</span></>}</div>
        <small className="cx-muted">Swath {num(swath[String(s.norad_id)])} km · elements {Number.isFinite(age) ? `${num(age)} h old` : 'unavailable'} · {s.refresh_status.startsWith('OK') ? 'refreshed' : s.refresh_status.split(':')[0].toLowerCase()}</small></Card>
    })}</div>
    <Card title={`All passes in the next ${real?.real_passes.lookahead_hours ?? 72} h`} aside={<span className="cx-chip">computed {utc(real?.real_passes.from_utc)}</span>}>
      <div className="cx-table" tabIndex={0} role="region" aria-label="Upcoming real satellite passes"><table>
        <thead><tr><th>Satellite</th><th>Closest approach (UTC)</th><th>When</th><th>Sites in swath</th><th>Closest site</th><th>Sun</th></tr></thead>
        <tbody>{passes.map(p => <tr key={`${p.norad_id}-${p.closest_utc}`} className={p.daylit ? '' : 'cx-night'}><td><b>{p.satellite}</b></td><td>{utc(p.closest_utc)}</td><td>{relative(parse(p.closest_utc) - now)}</td><td>{p.sites_in_swath.length} of 20</td><td>{num(p.min_ground_distance_km)} km</td><td>{p.daylit ? `daylight (${num(p.sun_elevation_deg)}°)` : 'night'}</td></tr>)}</tbody>
      </table></div>
      <p className="cx-foot">Whether an instrument actually records a scene is decided by its operators (EMIT follows its own observation plan on the ISS). Swath widths and rules: Parameter Register PR-LIVE02.</p>
    </Card>
  </Page>
}

function PlannerStory({ run }: { run: RunRecord }) {
  const outcomes = useMemo(() => new Map(run.acquisitions.map(a => [a.window_id, a.outcome])), [run])
  const gains = useMemo(() => new Map(run.utilities.map(u => [`${u.plan_revision}|${u.window_id}`, u.expected_info_gain_bits])), [run])
  const sourceNo = useMemo(() => new Map(run.sources.map((s, i) => [s.id, i + 1])), [run])
  const epoch = parse(run.plans[0]?.created_at_sim_utc ?? '')
  // Consecutive re-plans that keep exactly the same selection are shown once, with a count.
  const plans = run.plans.filter(p => p.selected_window_ids.length > 0).reduce<(RunRecord['plans'][number] & { repeats: number })[]>((acc, p) => {
    const last = acc[acc.length - 1]
    const key = [...p.selected_window_ids].sort().join('|')
    if (last && [...last.selected_window_ids].sort().join('|') === key) { last.repeats += 1; return acc }
    acc.push({ ...p, repeats: 1 }); return acc
  }, [])
  const cause = (c: string) => ({ initial: 'Start of mission', informative_acquisition: 'A look returned new evidence', forecast_revision: 'The cloud forecast changed', pass_completed: 'A satellite pass finished', invalid_acquisition: 'A look failed (cloud or geometry)' }[c] ?? c.replaceAll('_', ' '))
  return <Page kind="sim" kicker="Virtual fleet · OR-Tools CP-SAT · independent checker" title="Planner" intro={<>Each time something changes (a look returns evidence, or the forecast changes), the planner re-plans. It weighs every feasible look by how much it is expected to teach about which sources are emitting (expected information gain, in bits), then picks the best schedule the spacecraft can actually fly. An independent checker re-verifies every schedule.</>}>
    <div className="cx-stats">
      <Stat kind="sim" label="Schedule changes" value={String(plans.length)} note={`${run.plans.length} re-plans in total`} />
      <Stat kind="sim" label="Simulated looks executed" value={String(run.acquisitions.length)} note={`${run.acquisitions.filter(a => a.outcome === 'DETECTION').length} detections`} />
      <Stat kind="sim" label="Proven-optimal solves" value={`${run.plans.filter(p => p.solver_status === 'OPTIMAL').length} / ${run.plans.length}`} note="CP-SAT solver status" />
      <Stat kind="sim" label="Checker violations" value={String(run.validations.reduce((n, v) => n + v.violations.length, 0))} note="Independent geometry re-check" />
    </div>
    <Card title="Decision timeline">
      <ol className="cx-timeline">{plans.map(p => {
        const picks = p.selected_window_ids.map(id => ({ id, src: id.split(':')[2], sc: id.split(':')[0], gain: gains.get(`${p.revision}|${id}`), outcome: outcomes.get(id) })).sort((a, b) => (b.gain ?? 0) - (a.gain ?? 0))
        return <li key={p.revision}><div className="cx-tl-head"><span className="mono">T+{num((parse(p.created_at_sim_utc) - epoch) / 3600000, 1)} h</span><b>{cause(p.cause)}</b><span className="cx-muted">considered {p.candidate_window_ids.length} looks · chose {picks.length} · {p.solver_status === 'OPTIMAL' ? 'proven optimal' : p.solver_status.toLowerCase()}{p.repeats > 1 && ` · ${p.repeats - 1} further re-plans kept this schedule`}</span></div>
          <div className="cx-picks">{picks.slice(0, 6).map(k => <span key={k.id} className={`cx-pick ${(k.outcome ?? 'planned').toLowerCase()}`} title={k.id}>site {sourceNo.get(k.src) ?? '?'} · {craftName(k.sc)}{k.gain !== undefined && ` · ${num(k.gain, 2)} bits`}<i>{k.outcome ? k.outcome.replaceAll('_', ' ').toLowerCase() : 'superseded by a later plan'}</i></span>)}{picks.length > 6 && <span className="cx-muted">+{picks.length - 6} more</span>}</div></li>
      })}</ol>
    </Card>
  </Page>
}

function PolicyTest({ run, rows, report, protocol, failed }: { run: RunRecord; rows: BenchmarkRow[]; report: BenchmarkReport | null; protocol: BenchmarkProtocol | null; failed: boolean }) {
  return <Page kind="sim" kicker="Pre-registered benchmark" title="Policy test" intro={<>The question: does the adaptive planner learn the true state of the sources faster than simple rules, like "look at the biggest source first"? Every policy gets the same satellites, the same sources and the same hidden truth. They are scored by Brier score (lower is better). Before any comparison counts, a gate checks that the scenario can tell good planning from random looks at all.</>}>
    <Card title="Where the science stands">
      <ul className="cx-list cx-status">
        <li><span className="cx-pill fail">FAILED</span><b>Discriminability gate, 72 h scenario.</b> In all six test families (30 seeds each), a reference that can see the hidden truth scores almost the same as random looks. Comparing planners there would measure noise, so no comparison is claimed.</li>
        <li><span className="cx-pill fail">DOES NOT SEPARATE</span><b>168 h scenario diagnostic</b> (60 sources, 16 passes, tuning seeds, 18 Oct 2026): capacity is fixed (6.6 or more looks per pass), but the truth-informed reference still scores like random looks. A longer horizon alone does not make the benchmark informative; the next candidate is a denser fleet (decision H3).</li>
        <li><span className="cx-pill wait">PRELIMINARY</span><b>Two-seed comparison below</b>: shows the pipeline works. With 2 seeds it carries no statistical weight.</li>
      </ul>
    </Card>
    {failed && <div className="cx-empty" role="alert">The recorded comparison files could not be loaded from the API, so the table below is incomplete.</div>}
    <div className="cx-legacy"><ScreenContent screen="F" run={run} benchmarks={rows} benchmarkState={rows.length ? 'ready' : 'empty'} report={report} reportState={report ? 'ready' : 'empty'} protocol={protocol} /></div>
  </Page>
}

function Setup({ project, failed }: { project: ProjectSnapshot | null; failed: boolean }) {
  if (!project) return <div className="cx-empty" role={failed ? 'alert' : 'status'}>{failed ? 'The scenario configuration could not be loaded from /api/project. Check that the API server is running.' : 'Loading the scenario configuration…'}</div>
  const s = project.sensors[0]
  return <Page kind="sim" kicker="Scenario" title="Setup" intro={`The simulated mission in one page: ${project.scenario.horizon_hours} hours over the Permian Basin, ${project.scenario.sources_count} source sites placed from the real EMIT records, and a virtual fleet.`}>
    <div className="cx-three">
      <Card title={`${project.spacecraft.length} virtual satellites`}>
        <ul className="cx-list">{project.spacecraft.map(sc => <li key={sc.id}><b>{craftName(sc.id)}</b> <span className="cx-muted">({sc.id})</span> · {String(sc.orbit.altitude_km)} km up · {String(sc.orbit.inclination_deg)}° orbit · up to {sc.resources.max_acquisitions_per_orbit} looks per orbit</li>)}</ul>
      </Card>
      {s && <Card title="One virtual methane sensor">
        <ul className="cx-list"><li>Detects about <b>half</b> of plumes of <b>{s.q50_ref_kg_h} kg/h</b>, and 90% of plumes of {s.q90_ref_kg_h} kg/h, at {s.ref_wind_m_s} m/s wind</li><li>Pixel size {s.gsd_nadir_m} m; needs the sun above {s.min_sun_elevation_deg}°</li><li>Status: {s.calibration_status.replaceAll('_', ' ').toLowerCase()}, an engineering assumption, not a real instrument</li></ul>
      </Card>}
      <Card title="Planner">
        <ul className="cx-list"><li>Looks {project.planner.lookahead_hours} h ahead</li><li>Maximizes expected information gain</li><li>Solver: Google OR-Tools CP-SAT, {String(project.planner.solver.mode)} mode</li><li>Re-plans on: {project.planner.replan_on.map(r => r.replaceAll('_', ' ')).join(', ')}</li></ul>
      </Card>
    </div>
  </Page>
}
