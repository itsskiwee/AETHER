import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { BeliefSnapshot, BenchmarkComparison, BenchmarkProtocol, BenchmarkReport, BenchmarkRow, Plan, ProjectSnapshot, RunIndexItem, RunRecord } from './types'
import { parseRun } from './types'
import { DevelopmentTiming, HistoricalContext, RunManifest } from './ArtifactEvidence'
import LiveContext from './LiveContext'
import './benchmark.css'
import './project.css'

const screens = [
  ['A', 'Overview'], ['B', 'Sources'], ['C', 'Windows'], ['D', 'Beliefs'],
  ['E', 'Planner'], ['F', 'Comparison'], ['G', 'Method'],
] as const
const projectScreens = [
  ['A', 'Project'], ['B', 'EMIT context'], ['C', 'Spacecraft'], ['D', 'Science model'],
  ['E', 'Planner setup'], ['F', 'Evaluation'], ['G', 'Provenance'],
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
function utc(value: string | undefined): string { return value ? new Date(value).toISOString().replace(/\.\d+Z$/, 'Z').replace('T', ' ') : '—' }
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
function DataTable({ headers, children, label }: { headers: string[]; children: ReactNode; label: string }) {
  return <div className="table-wrap" tabIndex={0} role="region" aria-label={label}><table><caption className="sr-only">{label}</caption><thead><tr>{headers.map((header) => <th key={header} scope="col">{header}</th>)}</tr></thead><tbody>{children}</tbody></table></div>
}

export default function App() {
  return new URLSearchParams(location.search).get('view') === 'live' ? <LiveContext /> : <ReplayApp />
}

function ReplayApp() {
  const [screen, setScreen] = useState<Screen>('A')
  const [runs, setRuns] = useState<RunIndexItem[]>([])
  const [run, setRun] = useState<RunRecord | null>(null)
  const [runId, setRunId] = useState(new URLSearchParams(location.search).get('run') ?? '')
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'project' | 'empty' | 'error'>('loading')
  const [loadError, setLoadError] = useState('')
  const [project, setProject] = useState<ProjectSnapshot | null>(null)
  const [benchmarks, setBenchmarks] = useState<BenchmarkRow[]>([])
  const [benchmarkState, setBenchmarkState] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading')
  const [benchmarkReport, setBenchmarkReport] = useState<BenchmarkReport | null>(null)
  const [reportState, setReportState] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading')
  const [benchmarkProtocol, setBenchmarkProtocol] = useState<BenchmarkProtocol | null>(null)

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
    let projectLoaded = false
    try {
      const snapshot = await getJson<ProjectSnapshot>('/api/project')
      if (!snapshot?.scenario?.id || !Array.isArray(snapshot.spacecraft)) throw new Error('Project snapshot has an invalid shape.')
      setProject(snapshot)
      projectLoaded = true
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Project configuration is unavailable.')
    }
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
          setRun(null); setLoadState(projectLoaded ? 'project' : 'empty')
        }
      }
    } catch (error) {
      setRun(null)
      if (projectLoaded) setLoadState('project')
      else { setLoadState('error'); setLoadError(error instanceof Error ? error.message : 'Run archive is unavailable.') }
    }
  }, [loadRun, runId])

  useEffect(() => { void refresh() }, []) // initial archive load only
  useEffect(() => {
    let alive = true
    getJson<BenchmarkRow[]>('/api/benchmark-results.csv').then((rows) => {
      if (!Array.isArray(rows) || rows.some((row) => !row || typeof row !== 'object' || Object.values(row).some((value) => typeof value !== 'string'))) throw new Error('Benchmark response has an invalid shape.')
      if (alive) { setBenchmarks(rows); setBenchmarkState(rows.length ? 'ready' : 'empty') }
    }).catch(() => { if (alive) setBenchmarkState('empty') })
    getJson<BenchmarkReport>('/api/benchmark-confidence-intervals.json').then((report) => {
      if (!report || !Array.isArray(report.comparisons) || typeof report.protocol_locked !== 'boolean') throw new Error('Confidence interval response has an invalid shape.')
      if (alive) { setBenchmarkReport(report); setReportState('ready') }
    }).catch(() => { if (alive) setReportState('empty') })
    getJson<BenchmarkProtocol>('/api/benchmark-protocol').then((protocol) => {
      if (!protocol || typeof protocol.primary_metric !== 'string' || !Array.isArray(protocol.primary_comparison)
        || (protocol.families !== undefined && (!Array.isArray(protocol.families) || protocol.families.some((item) => typeof item !== 'string')))
        || (protocol.policies !== undefined && (!Array.isArray(protocol.policies) || protocol.policies.some((item) => typeof item !== 'string')))) throw new Error('Benchmark protocol response has an invalid shape.')
      if (alive) setBenchmarkProtocol(protocol)
    }).catch(() => { if (alive) setBenchmarkProtocol(null) })
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

  const content = run ? <ScreenContent screen={screen} run={run} benchmarks={benchmarks} benchmarkState={benchmarkState} report={benchmarkReport} reportState={reportState} protocol={benchmarkProtocol} /> : null
  const currentPlan = run?.plans.at(-1)
  const status = currentPlan?.solver_status ?? '—'
  const navScreens = loadState === 'project' ? projectScreens : screens

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="topbar">
      <a className="brand" href="#overview" onClick={(event) => { event.preventDefault(); setScreen('A') }} aria-label="AETHER research console overview">
        <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><span>AETHER<small>RESEARCH CONSOLE</small></span>
      </a>
      <div className="topbar-center"><span className="archive-marker" aria-hidden="true" /> READ ONLY <span className="topbar-divider">/</span> OFFLINE ARTIFACTS</div>
      <div className="topbar-right"><a href="/?view=live">Satellite context</a><span className="avatar">R</span><span>Research workspace</span></div>
    </header>
    <div className="mission-banner"><span className="banner-symbol" aria-hidden="true">◉</span><strong>SIMULATED MISSION</strong><span>All spacecraft and acquisitions in this console are virtual.</span><span className="banner-end">NO REAL SATELLITE TASKING</span></div>
    <div className="workspace">
      <aside className="sidebar" aria-label="Console navigation">
        <div className="side-label">WORKSPACE</div>
        <nav>{navScreens.map(([key, label]) => <button key={key} onClick={() => setScreen(key)} className={`nav-item ${screen === key ? 'active' : ''}`} aria-current={screen === key ? 'page' : undefined}><span className="nav-key">{key}</span><span>{label}</span>{key === 'G' && <span className="nav-meta">INFO</span>}</button>)}</nav>
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
        {loadState === 'project' && project && <ProjectWorkspace screen={screen} project={project} bench={{ benchmarks, state: benchmarkState, report: benchmarkReport, reportState, protocol: benchmarkProtocol }} />}
        {loadState === 'empty' && <Empty title="No project data found" detail="The local API did not find a run artifact or the project configuration files." action={() => void refresh()} />}
        {loadState === 'error' && <Empty title="Run archive could not be loaded" detail={`${loadError} Start the artifact API or choose a run from a reachable archive, then retry.`} action={() => void refresh()} />}
        {loadState === 'ready' && run && content}
      </main>
    </div>
    <footer className="statusbar"><div><span className="archive-marker" aria-hidden="true" />{run ? 'REPLAY' : project ? 'PROJECT CONFIG' : 'ARCHIVE'} <span className="status-sep">·</span><span className="mono">{run?.run_id ?? project?.scenario.id ?? 'NO RUN SELECTED'}</span></div><div>SCENARIO <span className="mono">{shortHash(run?.model_config_hash)}</span></div><div>UTC <span className="mono">{run?.plans.at(-1) ? utc(run.plans.at(-1)?.created_at_sim_utc) : project ? utc(project.scenario.epoch_utc) : '—'}</span></div><div>SOLVER <span className={`solver-pill ${status.toLowerCase()}`}>{status}</span></div></footer>
  </div>
}

function ScreenContent({ screen, run, benchmarks, benchmarkState, report, reportState, protocol }: { screen: Screen; run: RunRecord; benchmarks: BenchmarkRow[]; benchmarkState: string; report: BenchmarkReport | null; reportState: string; protocol: BenchmarkProtocol | null }) {
  switch (screen) {
    case 'A': return <Overview run={run} />
    case 'B': return <SourceMap run={run} />
    case 'C': return <Windows run={run} />
    case 'D': return <Beliefs run={run} />
    case 'E': return <Planner run={run} />
    case 'F': return <Comparison run={run} benchmarks={benchmarks} state={benchmarkState} report={report} reportState={reportState} protocol={protocol} />
    case 'G': return <Method run={run} />
  }
}

function ProjectWorkspace({ screen, project, bench }: { screen: Screen; project: ProjectSnapshot; bench: BenchmarkProps }) {
  if (screen === 'B') return <ProjectFixture project={project} />
  if (screen === 'C') return <ProjectSpacecraft project={project} />
  if (screen === 'D') return <ProjectScience project={project} />
  if (screen === 'E') return <ProjectPlanner project={project} />
  if (screen === 'F') return <ProjectEvaluation project={project} bench={bench} />
  if (screen === 'G') return <ProjectProvenance project={project} />
  return <ProjectOverview project={project} />
}

function ProjectOverview({ project }: { project: ProjectSnapshot }) {
  const { scenario, spacecraft, sensors, scenario_families: families } = project
  return <div className="page">
    <SectionTitle eyebrow="A / PROJECT WORKSPACE" title={scenario.id.replaceAll('_', ' ')} description="Project configuration read from repository files. No simulation run has been generated yet." right={<span className="state-pill neutral">CONFIGURATION ONLY</span>} />
    <div className="notice notice-neutral"><strong>PROJECT DATA</strong><span>The values below come from the repository’s scenario YAML, sensor and spacecraft profiles, and pinned data manifests. They are not run results.</span></div>
    <div className="run-strip"><div><span className="eyebrow">REGION</span><strong>{scenario.region.name}</strong></div><div><span className="eyebrow">SIMULATION EPOCH</span><strong className="mono">{utc(scenario.epoch_utc)}</strong></div><div><span className="eyebrow">HORIZON</span><strong>{fmt(scenario.horizon_hours, 0)} h · configured</strong></div><div><span className="eyebrow">SOURCE COUNT</span><strong>{fmt(scenario.sources_count, 0)} · configured</strong></div></div>
    <div className="metrics-grid"><Metric label="VIRTUAL SPACECRAFT" value={fmt(spacecraft.length, 0)} note="profiles present in configs/"/><Metric label="SENSOR PROFILES" value={fmt(sensors.length, 0)} note="assumed virtual response"/><Metric label="SCENARIO FAMILIES" value={fmt(families.length, 0)} note="configuration files present"/><Metric label="RUN ARTIFACTS" value="0" note="no run.json in the archive"/></div>
    <HistoricalContext summary />
    <div className="overview-grid"><section className="panel"><div className="panel-head"><div><div className="eyebrow">SOURCE MODEL CONFIGURATION</div><h2>Configured hypotheses</h2></div><span className="status-pill">NOT GENERATED</span></div><dl className="key-values"><dt>Placement mode</dt><dd>{project.source_model.placement}</dd><dt>Minimum separation</dt><dd>{fmt(project.source_model.min_separation_m, 0)} m</dd><dt>Active flux prior median</dt><dd>{fmt(project.source_model.flux_prior.median_kg_h, 0)} kg/h</dd><dt>Prior range</dt><dd>{fmt(project.source_model.flux_prior.min_kg_h, 0)}–{fmt(project.source_model.flux_prior.max_kg_h, 0)} kg/h</dd><dt>Weather model</dt><dd>{scenario.weather.type}</dd></dl><p className="fine-print">These are configured inputs. No source locations or simulated truth have been generated for a run.</p></section>
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">SCENARIO FAMILY FILES</div><h2>Available configurations</h2></div><span className="count-badge">{families.length}</span></div><div className="family-list">{families.map((family) => <div className="family-row" key={family}><span className="file-mark">YAML</span><strong>{family}</strong><span className="family-kind">configuration</span></div>)}</div></section></div>
    <div className="overview-grid project-lower"><section className="panel"><div className="panel-head"><div><div className="eyebrow">VIRTUAL CONSTELLATION</div><h2>Spacecraft profiles</h2></div></div><div className="spacecraft-cards">{spacecraft.map((sat) => <div className="spacecraft-card" key={sat.id}><div><span className="satellite-mark">▤</span><strong>{sat.id}</strong><span className="tag tag-simulated_observation">VIRTUAL</span></div><span>{sat.orbit.altitude_km} km · {sat.orbit.inclination_deg}° inclination</span><span>Plane {sat.orbit.plane} · LTDN {sat.orbit.ltdn}</span></div>)}</div></section>
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">SYNTHETIC INPUT EXAMPLE</div><h2>Fixture status</h2></div><Provenance kind="SIMULATED_OBSERVATION"/></div><div className="fixture-summary"><strong>{project.fixture.features.length}</strong><span>fabricated GeoJSON feature examples</span></div><p className="fine-print">{project.fixture.manifest?.fixture_status ?? 'Fixture manifest unavailable'}. The fixture is for parser development and is not a NASA observation.</p></section></div>
  </div>
}

function ProjectFixture({ project }: { project: ProjectSnapshot }) {
  const features = project.fixture.features
  const points = features.filter((item) => typeof item.longitude === 'number' && typeof item.latitude === 'number')
  const lons = points.map((p) => p.longitude as number), lats = points.map((p) => p.latitude as number)
  const lon0 = Math.min(...lons, ...project.scenario.region.bbox_wgs84.filter((_, i) => i % 2 === 0))
  const lon1 = Math.max(...lons, ...project.scenario.region.bbox_wgs84.filter((_, i) => i % 2 === 0))
  const lat0 = Math.min(...lats, ...project.scenario.region.bbox_wgs84.filter((_, i) => i % 2 === 1))
  const lat1 = Math.max(...lats, ...project.scenario.region.bbox_wgs84.filter((_, i) => i % 2 === 1))
  return <div className="page"><SectionTitle eyebrow="B / HISTORICAL CONTEXT" title="EMIT observations" description="Provider detections are historical location context; this page keeps them distinct from parser examples and virtual source hypotheses." />
    <HistoricalContext />
    <div className="section-title"><div><div className="eyebrow">PARSER TEST DATA</div><h2>Synthetic GeoJSON fixture</h2><p>This fabricated input tests the adapter and is not a real observation dataset.</p></div><span className="tag tag-simulated_observation">EXAMPLE ONLY · NOT SOURCE VERIFIED</span></div>
    <div className="notice notice-warn"><strong>SYNTHETIC FIXTURE</strong><span>{project.fixture.manifest?.dataset ?? 'Example GeoJSON'} · {project.fixture.manifest?.citation_text ?? 'Fabricated parser input.'}</span></div>
    <div className="map-layout"><div className="map-panel"><svg viewBox="0 0 720 390" role="img" aria-labelledby="fixture-map-title fixture-map-desc"><title id="fixture-map-title">Synthetic fixture coordinates</title><desc id="fixture-map-desc">Schematic coordinates of fabricated GeoJSON parser examples. This is not a real methane observation map.</desc><rect width="720" height="390" fill="#f6f7f4"/>{[0,1,2,3,4].map((i)=><g key={i}><line x1={70+i*140} x2={70+i*140} y1="24" y2="344" className="map-grid"/><line x1="70" x2="630" y1={24+i*80} y2={24+i*80} className="map-grid"/></g>)}{points.map((p,i)=>{const x=70+((p.longitude!-lon0)/Math.max(lon1-lon0,.001))*560;const y=344-((p.latitude!-lat0)/Math.max(lat1-lat0,.001))*320;return <g key={p.id}><circle cx={x} cy={y} r="8" className="fixture-dot"/><text x={x+12} y={y+4} className="source-label">{i+1}</text></g>})}<text x="70" y="372" className="map-axis">{fmt(lon0,2)}°</text><text x="570" y="372" className="map-axis">{fmt(lon1,2)}°</text><text x="18" y="33" className="map-axis">{fmt(lat1,2)}°</text><text x="18" y="345" className="map-axis">{fmt(lat0,2)}°</text></svg><div className="map-legend"><span><i className="fixture-legend"/>Synthetic fixture coordinate</span><span className="map-note">schematic · no basemap</span></div></div>
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">FEATURE LIST</div><h2>{features.length} examples</h2></div></div><DataTable label="Synthetic GeoJSON parser fixture feature values" headers={['FIXTURE ID', 'TIME (UTC)', 'RATE', 'GEOMETRY']}><>{features.map((f)=> <tr key={f.id}><td className="mono">{f.id}</td><td className="mono">{utc(f.time_utc ?? undefined)}</td><td>{f.rate == null || f.rate === 'N/A' ? '— (fixture says N/A)' : `${f.rate} kg/h`}</td><td>{f.geometry_type}</td></tr>)}</></DataTable></section></div>
    <p className="table-footnote">Fixture manifest SHA-256: <code>{project.fixture.manifest?.files[0]?.sha256 ?? 'unavailable'}</code>. Feature rows remain example inputs and are not converted into real plume observations.</p>
  </div>
}

function ProjectSpacecraft({ project }: { project: ProjectSnapshot }) {
  return <div className="page"><SectionTitle eyebrow="C / ORBIT CONFIGURATION" title="Virtual spacecraft" description="Configured orbit and resource profiles. Orbit propagation and candidate windows have not been generated." right={<span className="tag tag-simulated_observation">VIRTUAL ONLY</span>} />
    <div className="notice notice-neutral"><strong>NOT PROPAGATED</strong><span>These rows come from profile YAML files. They are not calculated ground tracks or observation opportunities.</span></div>
    <section className="panel"><DataTable label="Configured virtual spacecraft profiles" headers={['PROFILE', 'PLANE / LTDN', 'ORBIT', 'POINTING', 'RESOURCES', 'CONFIG VERSION']}><>{project.spacecraft.map((sat)=><tr key={sat.id}><td><strong>{sat.id}</strong><span className="subcell">{sat.virtual?'virtual taskable profile':'not virtual'} · {sat.sensor_ids.join(', ')}</span></td><td>Plane {sat.orbit.plane}<span className="subcell">LTDN {sat.orbit.ltdn}</span></td><td className="numeric">{fmt(Number(sat.orbit.altitude_km),0)} km · {fmt(Number(sat.orbit.inclination_deg),2)}°</td><td className="numeric">{fmt(sat.attitude.max_off_nadir_deg,0)}° max · {fmt(sat.attitude.slew_rate_deg_s,2)}°/s</td><td className="numeric">{fmt(sat.resources.storage_bytes/1e9,0)} GB · {fmt(sat.resources.max_acquisitions_per_orbit,0)}/orbit</td><td className="mono">{sat.profile_version}</td></tr>)}</></DataTable></section>
    <section className="panel project-panel"><div className="panel-head"><div><div className="eyebrow">NEXT CALCULATION</div><h2>Orbit windows</h2></div><span className="status-pill">NOT AVAILABLE</span></div><p className="panel-padding">The orbit and window-generation modules are present in the project. This workspace has no generated `windows.json` or run artifact to display yet.</p></section>
  </div>
}

function ProjectScience({ project }: { project: ProjectSnapshot }) {
  return <div className="page"><SectionTitle eyebrow="D / SCIENCE CONFIGURATION" title="Model assumptions" description="Configured virtual sensor response and source persistence priors; no posterior beliefs have been calculated." />
    <div className="notice notice-warn"><strong>ASSUMPTIONS</strong><span>Sensor profiles are labelled simulated. The displayed values are design parameters, not instrument calibration results.</span></div>
    <div className="belief-grid">{project.sensors.map((sensor)=><section className="panel" key={sensor.id}><div className="panel-head"><div><div className="eyebrow">VIRTUAL SENSOR</div><h2>{sensor.id}</h2></div><span className="tag tag-simulated_observation">{sensor.calibration_status}</span></div><dl className="key-values"><dt>Reference Q50 / Q90</dt><dd>{fmt(sensor.q50_ref_kg_h,0)} / {fmt(sensor.q90_ref_kg_h,0)} kg/h</dd><dt>Reference wind</dt><dd>{fmt(sensor.ref_wind_m_s,1)} m/s</dd><dt>Nadir GSD</dt><dd>{fmt(sensor.gsd_nadir_m,0)} m</dd><dt>Exposure</dt><dd>{fmt(sensor.exposure_seconds,1)} s</dd><dt>Minimum sun elevation</dt><dd>{fmt(sensor.min_sun_elevation_deg,0)}°</dd><dt>False-positive assumption</dt><dd>{fmt(sensor.false_positive_prob)} per valid scene</dd><dt>Retrieval success</dt><dd>{fmt(sensor.retrieval_success_prob)}</dd></dl></section>)}
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">SOURCE STATE PRIORS</div><h2>Configured regimes</h2></div></div><DataTable label="Configured source activity regimes" headers={['REGIME', 'WEIGHT', 'MEAN ACTIVE', 'MEAN INACTIVE']}><>{project.source_model.regimes.map((regime)=><tr key={regime.name}><td>{regime.name}</td><td className="numeric">{fmt(regime.weight)}</td><td className="numeric">{fmt(regime.mean_on_hours,0)} h</td><td className="numeric">{fmt(regime.mean_off_hours,0)} h</td></tr>)}</></DataTable><p className="table-footnote">Prior flux median: {fmt(project.source_model.flux_prior.median_kg_h,0)} kg/h conditional on active. No source posterior is available without a run.</p></section></div>
  </div>
}

function ProjectPlanner({ project }: { project: ProjectSnapshot }) {
  const planner = project.planner
  return <div className="page"><SectionTitle eyebrow="E / PLANNER CONFIGURATION" title="Scheduling setup" description="Policy roster and solver settings read from the base scenario configuration. No plan has been solved." />
    <div className="notice notice-neutral"><strong>NO PLAN RUN</strong><span>The controls below describe configuration only. There is no selected schedule or utility ranking to inspect yet.</span></div>
    <div className="overview-grid"><section className="panel"><div className="panel-head"><div><div className="eyebrow">AVAILABLE POLICIES</div><h2>Configured comparison set</h2></div><span className="count-badge">{project.scenario.policies.length}</span></div><div className="policy-list">{project.scenario.policies.map((policy,i)=><div className="policy-row" key={policy}><span className="policy-glyph">{String(i+1).padStart(2,'0')}</span><strong>{policy}</strong><span className="policy-note">configured</span></div>)}</div></section>
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">SOLVER SETTINGS</div><h2>Base scenario</h2></div></div><dl className="key-values"><dt>Lookahead</dt><dd>{fmt(planner.lookahead_hours,0)} h</dd><dt>Objective</dt><dd>{planner.utility}</dd><dt>Weight configuration</dt><dd>{Object.entries(planner.weights).map(([key,value])=>`${key} ${fmt(value,2)}`).join(' · ')}</dd><dt>Max visits / source / solve</dt><dd>{fmt(planner.max_visits_per_source_per_solve,0)}</dd><dt>Solver mode</dt><dd>{String(planner.solver.mode)}</dd><dt>Workers</dt><dd>{String(planner.solver.num_workers)}</dd><dt>Replan triggers</dt><dd>{planner.replan_on.join(', ')}</dd></dl></section></div>
    <section className="panel project-panel"><div className="panel-head"><div><div className="eyebrow">SELECTED WINDOWS</div><h2>Schedule</h2></div><span className="status-pill">NO SOLUTION ARTIFACT</span></div><p className="panel-padding">The CP-SAT and baseline policy modules are present in the repository; the CLI runner has not written a plan for this scenario yet.</p></section>
  </div>
}

function ProjectEvaluation({ project, bench }: { project: ProjectSnapshot; bench: BenchmarkProps }) {
  const hasOutput = bench.report !== null || bench.benchmarks.length > 0
  const protocol = project.benchmark_protocol
  return <div className="page"><SectionTitle eyebrow="F / EVALUATION SETUP" title="Benchmark readiness" description="Registered protocol and available scenario families. These are study inputs, not measured results." />
    {hasOutput ? <BenchmarkPanels {...bench} /> : <div className="notice notice-warn"><strong>NO BENCHMARK RESULTS</strong><span>There is no benchmark-results.csv or paired confidence interval report in the workspace yet.</span></div>}
    <div className="plan-summary"><div><span className="eyebrow">PROTOCOL VERSION</span><strong>v{fmt(protocol.version,0)} · {protocol.locked?'LOCKED':'UNLOCKED'}</strong></div><div><span className="eyebrow">PRIMARY METRIC</span><strong>{protocol.primary_metric ?? 'Not specified'}</strong></div><div><span className="eyebrow">SCENARIO FAMILIES</span><strong>{fmt(protocol.families.length,0)}</strong></div><div><span className="eyebrow">BENCHMARK OUTPUT</span><strong>{hasOutput ? 'Present' : 'Not present'}</strong></div><div><span className="eyebrow">HOLDOUT POLICY</span><strong>{protocol.locked?'Protocol locked':'Holdout gate closed'}</strong></div></div>
    <section className="panel"><div className="panel-head"><div><div className="eyebrow">REGISTERED FAMILIES</div><h2>Protocol scenario set</h2></div></div><div className="family-cloud">{protocol.families.map((family)=><span className="family-chip" key={family}>{family}</span>)}</div></section>
    <section className="panel project-panel"><div className="panel-head"><div><div className="eyebrow">SEED FILES</div><h2>Configured inputs</h2></div></div><div className="family-list">{protocol.seed_files.map((path)=><div className="family-row" key={path}><span className="file-mark">TXT</span><strong className="mono">{path}</strong><span className="family-kind">present in repository</span></div>)}</div></section>
  </div>
}

function ProjectProvenance({ project }: { project: ProjectSnapshot }) {
  const fixture = project.fixture.manifest
  const pinnedItems: { label: string; record: ProjectSnapshot['pinned_data']['earth_orientation'] }[] = [
    { label: 'EARTH ORIENTATION', record: project.pinned_data.earth_orientation },
    { label: 'PLANETARY EPHEMERIS', record: project.pinned_data.planetary_ephemeris },
  ]
  return <div className="page"><SectionTitle eyebrow="G / FILES & PROVENANCE" title="Project data inventory" description="Pinned support data and fixture manifests currently available in the repository." />
    <div className="notice notice-neutral"><strong>PROVENANCE</strong><span>Support files are shown with their repository manifest metadata. The synthetic GeoJSON fixture is explicitly not source verified.</span></div>
    <section className="panel"><div className="panel-head"><div><div className="eyebrow">PARSER FIXTURE</div><h2>{fixture?.dataset ?? 'No fixture manifest'}</h2></div><span className="tag tag-simulated_observation">{fixture?.fixture_status ?? 'UNAVAILABLE'}</span></div>{fixture?.files.length ? <DataTable label="Synthetic parser fixture file manifest" headers={['PATH', 'SIZE', 'SHA-256']}>{fixture.files.map((file)=><tr key={file.path}><td className="mono">{file.path}</td><td className="numeric">{fmt(file.size_bytes,0)} bytes</td><td className="mono hash-cell">{file.sha256}</td></tr>)}</DataTable>:<p className="panel-padding">Fixture manifest unavailable.</p>}</section>
    <div className="overview-grid project-lower">{pinnedItems.map(({ label, record })=><section className="panel" key={label}><div className="panel-head"><div><div className="eyebrow">PINNED SUPPORT DATA</div><h2>{label}</h2></div><span className="status-pill">{record?'PRESENT':'UNAVAILABLE'}</span></div>{record?<dl className="key-values"><dt>File</dt><dd className="mono">{record.filename}</dd><dt>Size</dt><dd>{fmt(record.byte_size/1e6,2)} MB</dd><dt>Retrieved</dt><dd className="mono">{utc(record.retrieved_at_utc)}</dd><dt>SHA-256</dt><dd className="mono hash-cell">{record.sha256}</dd><dt>Source</dt><dd><a href={record.url} target="_blank" rel="noreferrer">Provider manifest link ↗</a></dd></dl>:<p className="panel-padding">No manifest present.</p>}</section>)}</div>
  </div>
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
    <HistoricalContext run={run} summary />
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
  const seededCount = run.input_dataset?.seeded_source_count ?? coords.filter((source) => source.seeded_from_plume_id !== null).length
  const fillCount = run.input_dataset?.uniform_fill_count ?? coords.filter((source) => source.seeded_from_plume_id === null).length
  const minLon = Math.min(...coords.map((s) => s.lon), -104.5), maxLon = Math.max(...coords.map((s) => s.lon), -101)
  const minLat = Math.min(...coords.map((s) => s.lat), 30.8), maxLat = Math.max(...coords.map((s) => s.lat), 33.5)
  const lonSpan = Math.max(maxLon - minLon, 0.001), latSpan = Math.max(maxLat - minLat, 0.001)
  return <div className="page"><SectionTitle eyebrow="B / SOURCE HYPOTHESES" title="Geographic context" description="Locations are source hypotheses from this run. The map is paired with a keyboard accessible source table." />
    <div className="map-layout"><div className="map-panel" aria-label="Schematic source location plot">
      <svg viewBox="0 0 720 390" role="img" aria-labelledby="map-title map-desc"><title id="map-title">Source hypothesis locations</title><desc id="map-desc">Schematic longitude and latitude plot of source hypotheses. No basemap or facility attribution is included.</desc>
        <rect x="0" y="0" width="720" height="390" fill="#f6f7f4" />
        {[0, 1, 2, 3, 4].map((i) => <g key={i}><line x1={70 + i * 140} x2={70 + i * 140} y1="24" y2="344" className="map-grid"/><line x1="70" x2="630" y1={24 + i * 80} y2={24 + i * 80} className="map-grid" /></g>)}
        <text x="70" y="372" className="map-axis">{fmt(minLon, 2)}°W</text><text x="570" y="372" className="map-axis">{fmt(maxLon, 2)}°W</text><text x="18" y="33" className="map-axis">{fmt(maxLat, 2)}°N</text><text x="18" y="345" className="map-axis">{fmt(minLat, 2)}°N</text>
        {coords.map((source, i) => { const x = 70 + ((source.lon - minLon) / lonSpan) * 560; const y = 344 - ((source.lat - minLat) / latSpan) * 320; return <g key={source.id}>{source.seeded_from_plume_id ? <circle cx={x} cy={y} r="7" className="source-dot"/> : <rect x={x - 6} y={y - 6} width="12" height="12" className="source-fill-dot"/>}<text x={x + 10} y={y + 4} className="source-label">{i + 1}</text></g> })}
      </svg><div className="map-legend"><span><i className="legend-dot" /> Plume-seeded hypothesis</span><span><i className="uniform-fill-legend" /> Uniform-fill hypothesis</span><span className="map-note">schematic coordinates · no basemap</span></div>
    </div><section className="panel source-panel"><div className="panel-head"><div><div className="eyebrow">SOURCE INDEX</div><h2>{coords.length} hypotheses</h2></div></div>
      <p className="source-origin-counts"><span>historical plume seeded: {seededCount}</span><span>uniform synthetic fill: {fillCount}</span></p>
      {coords.length ? <DataTable label="Source hypothesis coordinates" headers={['SOURCE', 'LONGITUDE', 'LATITUDE', 'STATUS', 'LOCATION LINEAGE', 'ATTRIBUTION']}><>{coords.map((s, i) => <tr key={s.id}><td><strong>{String(i + 1).padStart(2, '0')}</strong><span className="subcell">{s.id}</span></td><td className="mono">{fmt(s.lon, 4)}°</td><td className="mono">{fmt(s.lat, 4)}°</td><td><Provenance kind="MODEL_INFERENCE" /></td><td>{s.seeded_from_plume_id ? <><span>Seeded from historical plume: {s.seeded_from_plume_id}</span></> : <><span>Uniform simulated fill</span><span className="subcell">No historical plume ID is linked</span></>}</td><td>{s.attribution_status}</td></tr>)}</></DataTable> : <Empty title="No source locations" detail="This run contains no source hypotheses." />}
    </section></div>
    <p className="table-footnote">Every row is a model-inferred virtual source hypothesis. A historical plume seed supplies location context only; it does not indicate present activity or a facility identity.</p>
    <HistoricalContext run={run} />
  </div>
}

function Windows({ run }: { run: RunRecord }) {
  const feasible = run.windows.filter((w) => w.feasible)
  const rejected = run.windows.filter((w) => !w.feasible)
  const start = run.windows.length ? Math.min(...run.windows.map((w) => Date.parse(w.start_utc))) : 0
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
  const firstTime = Date.parse(selected[0]?.state_time_utc ?? '')
  const timeSpan = Math.max(Date.parse(selected.at(-1)?.state_time_utc ?? '') - firstTime, 1)
  const timeX = (belief: BeliefSnapshot) => 42 + (Date.parse(belief.state_time_utc) - firstTime) * 540 / timeSpan
  const points = selected.map((belief) => `${timeX(belief)},${210 - belief.p_active * 170}`).join(' ')
  return <div className="page"><SectionTitle eyebrow="D / SOURCE SCIENCE" title="Belief history" description="Model-inferred activity probability and evidence sequence. Missing or invalid observations do not count as non-detections." right={<label className="select-control">SOURCE<select aria-label="Select source" value={sourceId} onChange={(e) => setSourceId(e.target.value)}>{sources.map((s) => <option key={s}>{s}</option>)}</select></label>} />
    {!sources.length ? <Empty title="No source hypotheses" detail="Belief history is unavailable for this run." /> : <>
      {!selected.length && <div className="notice notice-neutral"><strong>INSUFFICIENT EVIDENCE</strong><span>No belief snapshots were recorded for this source. The source cannot be described as inactive.</span></div>}
      <div className="belief-grid"><section className="panel chart-panel"><div className="panel-head"><div><div className="eyebrow">ACTIVITY PROBABILITY</div><h2>P(active) over time</h2></div><Provenance kind="MODEL_INFERENCE" /></div>
        {selected.length ? <><div className="chart-box"><svg viewBox="0 0 620 250" role="img" aria-label={`Activity probability for ${sourceId}; vertical axis from zero to one`}><line x1="42" x2="600" y1="40" y2="40" className="chart-grid"/><line x1="42" x2="600" y1="125" y2="125" className="chart-grid"/><line x1="42" x2="600" y1="210" y2="210" className="chart-grid"/><text x="3" y="44" className="chart-tick">1.00</text><text x="3" y="129" className="chart-tick">0.50</text><text x="3" y="214" className="chart-tick">0.00</text><polyline points={points} className="belief-line" />{selected.map((belief, i) => { const x = timeX(belief); const y = 210 - belief.p_active * 170; const acquisition = acquisitions.find((item) => item.time_utc === belief.state_time_utc); return <g key={`${belief.state_time_utc}-${i}`}><circle cx={x} cy={y} r="4.5" className={acquisition ? `evidence-point ${acquisition.outcome.toLowerCase()}` : 'belief-point'}><title>{`${utc(belief.state_time_utc)} · P(active) ${fmt(belief.p_active)}${acquisition ? ` · ${acquisition.outcome}` : ''}`}</title></circle></g>})}<text x="42" y="240" className="chart-tick">{utc(selected[0]?.state_time_utc)}</text><text x="600" y="240" textAnchor="end" className="chart-tick">{utc(selected.at(-1)?.state_time_utc)}</text></svg></div><p className="chart-axis-note">Probability · 0 to 1 <span>Time · UTC</span></p><div className="chart-table-toggle"><details><summary>View values as table</summary><DataTable label="Belief probability values" headers={['TIME (UTC)', 'P(ACTIVE)', 'EVIDENCE']}><>{selected.map((b, i) => <tr key={`${b.state_time_utc}-${i}`}><td className="mono">{utc(b.state_time_utc)}</td><td className="numeric">{fmt(b.p_active)}</td><td>{b.evidence_ids.length ? b.evidence_ids.join(', ') : 'Prior / prediction'}</td></tr>)}</></DataTable></details></div></> : <div className="chart-empty">No plotted values</div>}
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
  const validation = run.validations.find((item) => item.plan_revision === plan?.revision)
  const forecastEvents = run.events.filter((event) => event.event_type === 'FORECAST_REVISED')
  const selectionKeys = (selections: Plan['selections']) => selections.map((selection) => `${selection.window_id} · ${selection.option_id}`)
  const changed = previous ? { added: selectionKeys(plan!.selections).filter((id) => !selectionKeys(previous.selections).includes(id)), removed: selectionKeys(previous.selections).filter((id) => !selectionKeys(plan!.selections).includes(id)) } : null
  return <div className="page"><SectionTitle eyebrow="E / PLAN REVIEW" title="Planner decisions" description="Recorded utility values, solver status, and revision causes. This view does not recompute a schedule." right={plans.length > 0 && <label className="select-control">PLAN REVISION<select value={plan?.revision ?? ''} onChange={(e) => setRevision(Number(e.target.value))}>{plans.map((p) => <option key={p.revision} value={p.revision}>Revision {p.revision}</option>)}</select></label>} />
    {!plan ? <Empty title="No plans in this run" detail="Planner decisions are available when plan records are present in run.json." /> : <>
      <div className="plan-summary"><div><span className="eyebrow">POLICY</span><strong>{plan.policy_id}</strong></div><div><span className="eyebrow">SOLVER</span><strong><span className={`solver-pill ${plan.solver_status.toLowerCase()}`}>{plan.solver_status}</span></strong></div><div><span className="eyebrow">OBJECTIVE</span><strong>{plan.objective_value == null ? 'Unavailable' : fmt(plan.objective_value)}</strong></div><div><span className="eyebrow">SOLVE TIME</span><strong>{plan.runtime_s == null ? 'Not recorded' : `${fmt(plan.runtime_s, 3)} s`}</strong></div><div><span className="eyebrow">VALIDATION</span><strong>{plan.validation_ok == null ? 'Unavailable' : plan.validation_ok ? 'Passed' : 'Violations'}</strong></div></div>
      <div className="notice notice-cause"><div className="cause-icon" aria-hidden="true">↻</div><div><span className="eyebrow">REVISION {plan.revision} · CAUSE</span><strong>{plan.cause}</strong><span className="mono cause-time">{utc(plan.created_at_sim_utc)}</span></div></div>
      <div className="notice notice-neutral"><strong>INDEPENDENT CHECKER</strong><span>{validation ? `Revision ${validation.plan_revision}: ${validation.ok ? 'passed' : 'failed'} · ${validation.violations.length} violations · ${validation.checker_version}` : 'No independent validation record for this revision.'} · {run.validations.length} validation records for {run.plans.length} plans.</span></div>
      {forecastEvents.length > 0 && <section className="panel"><details><summary>Recorded forecast events ({forecastEvents.length})</summary><DataTable label="Recorded forecast revisions" headers={['TIME (UTC)', 'EVENT', 'RECORDED PAYLOAD']}><>{forecastEvents.map((event) => <tr key={event.event_id}><td className="mono">{utc(event.event_time_sim_utc)}</td><td>{event.event_type}</td><td><code>{JSON.stringify(event.payload)}</code></td></tr>)}</></DataTable></details></section>}
      {changed && <section className="panel diff-panel"><div className="panel-head"><div><div className="eyebrow">REVISION DIFF</div><h2>Decision changes from revision {previous?.revision}</h2></div><span className="count-badge">{changed.added.length + changed.removed.length} changes</span></div><div className="diff-columns"><div><span className="eyebrow">ADDED</span>{changed.added.length ? changed.added.map((id) => <div className="diff-item added" key={id}>+ {id}</div>) : <span className="muted">No additions</span>}</div><div><span className="eyebrow">REMOVED</span>{changed.removed.length ? changed.removed.map((id) => <div className="diff-item removed" key={id}>− {id}</div>) : <span className="muted">No removals</span>}</div></div></section>}
      <div className="planner-layout"><section className="panel"><div className="panel-head"><div><div className="eyebrow">CANDIDATE UTILITIES</div><h2>{utilities.length} recorded candidates</h2></div></div>{utilities.length ? <DataTable label="Planner candidate utilities" headers={['CANDIDATE', 'EIG', 'P(VALID)', 'UTILITY', 'SELECTION']}><>{utilities.map((u) => <tr key={u.window_id}><td className="mono">{u.window_id}<span className="subcell">{windows.get(u.window_id)?.source_id ?? 'Source unavailable'}</span></td><td className="numeric">{fmt(u.expected_info_gain_bits, 4)} bits</td><td className="numeric">{fmt(u.p_valid_forecast)}</td><td className="numeric">{fmt(u.utility, 4)}</td><td>{selectedIds.has(u.window_id) ? <span className="state-label good">SELECTED</span> : <span className="muted">NOT SELECTED</span>}</td></tr>)}</></DataTable> : <p className="muted panel-padding">No utility records for this revision.</p>}</section>
        <aside className="panel selected-panel"><div className="panel-head"><div><div className="eyebrow">SELECTED SCHEDULE</div><h2>{plan.selections.length} options</h2></div></div>{plan.selections.length ? <ol>{plan.selections.map((selection, index) => { const w = windows.get(selection.window_id); const option = w?.options.find((item) => item.option_id === selection.option_id); return <li key={selection.option_id}><span className="selected-index">{String(index + 1).padStart(2, '0')}</span><div><strong className="mono">{selection.option_id}</strong><span>{w && option ? `${w.spacecraft_id} · ${w.source_id} · ${utc(option.start_utc)}` : 'Window details unavailable'}</span></div></li> })}</ol> : <p className="muted">The recorded plan selected no options.</p>}</aside></div>
      <div className="section-footer"><span>OBJECTIVE WEIGHTS <code>{Object.entries(plan.objective_weights).map(([k,v]) => `${k}: ${fmt(v, 3)}`).join(' · ') || 'Unavailable'}</code></span><span>BOUND <code>{plan.best_bound == null ? 'Unavailable' : fmt(plan.best_bound)}</code></span></div>
    </>}
  </div>
}

type BenchmarkProps = { benchmarks: BenchmarkRow[]; state: string; report: BenchmarkReport | null; reportState: string; protocol: BenchmarkProtocol | null }
const MIN_SEEDS = 10 // UI-05: below this, intervals are shown as descriptive only

// Reads one interval using the evaluator's recorded direction. Never infers a winner from the mean alone.
export function readInterval(item: BenchmarkComparison): { label: string; tone: 'favours-a' | 'favours-b' | 'neutral' | 'insufficient' } {
  const r = item.result
  if (!r) return { label: 'NO INTERVAL', tone: 'insufficient' }
  if (r.n < MIN_SEEDS) return { label: 'INSUFFICIENT SAMPLES', tone: 'insufficient' }
  if (r.lo <= 0 && r.hi >= 0) return { label: 'INTERVAL INCLUDES 0', tone: 'neutral' }
  if (!item.better_direction) return { label: r.lo > 0 ? 'A − B ABOVE 0' : 'A − B BELOW 0', tone: 'neutral' }
  const aBetter = item.better_direction === 'lower' ? r.hi < 0 : r.lo > 0
  return aBetter ? { label: `FAVOURS ${item.a}`, tone: 'favours-a' } : { label: `FAVOURS ${item.b}`, tone: 'favours-b' }
}

function BenchmarkPanels({ benchmarks: rows, state, report, reportState, protocol }: BenchmarkProps) {
  const cols = rows.length ? Object.keys(rows[0]) : []
  const sampleCount = report?.n_seeds ?? rows.reduce((max, row) => Math.max(max, Number(row.n_seeds ?? 0) || 0), 0)
  const verdict = report?.success_verdict
  const holm = report?.holm_primary ?? {}
  const isPrimary = (item: BenchmarkComparison) => Boolean(protocol && item.metric === protocol.primary_metric && item.a === protocol.primary_comparison[0] && item.b === protocol.primary_comparison[1])
  const coveredFamilies = new Set(report?.comparisons.map((item) => item.family) ?? [])
  return <>
    {report && <div className={`notice ${report.protocol_locked ? 'notice-neutral' : 'notice-warn'}`}><strong>{report.protocol_locked ? `LOCKED PROTOCOL · ${report.lock_tag ?? 'TAG UNAVAILABLE'}` : 'PRELIMINARY · UNLOCKED DEVELOPMENT PROTOCOL'}</strong><span>Protocol v{report.protocol_version} · {report.n_seeds} seeds · protocol SHA-256 <code>{shortHash(report.protocol_sha256)}</code>{report.note ? ` · ${report.note}` : ''}</span></div>}
    {sampleCount > 0 && sampleCount < MIN_SEEDS && <div className="notice notice-warn"><strong>INSUFFICIENT SAMPLES · PRELIMINARY</strong><span>Fewer than {MIN_SEEDS} seeds. Intervals are descriptive; no comparison is read from them.</span></div>}
    {verdict ? <section className={`verdict-panel ${verdict.success ? 'verdict-pass' : 'verdict-not-met'}`}><div className="verdict-seal" aria-hidden="true">{verdict.success ? '✓' : '·'}</div><div className="verdict-copy"><span className="eyebrow">RECORDED PROTOCOL VERDICT · {report?.protocol_locked ? 'LOCKED' : 'UNLOCKED, TUNING ONLY'}</span><h2>{verdict.success ? 'Success criterion met' : 'Success criterion not met'}</h2><p>{verdict.reasons.length ? verdict.reasons.join(' · ') : 'The evaluator recorded every pre-registered condition as satisfied.'}</p></div><div className="verdict-meta"><span>CHECKER VIOLATIONS</span><strong>{fmt(report?.total_checker_violations, 0)}</strong><span>PROTOCOL v{report?.protocol_version}</span></div></section>
      : report && <div className="notice notice-neutral"><strong>NO PROTOCOL VERDICT</strong><span>The evaluator did not record a protocol verdict. See the report scope and sample labels above.</span></div>}
    {protocol?.families?.length ? <section className="panel"><div className="panel-head"><div><div className="eyebrow">REGISTERED STUDY SCOPE</div><h2>Family coverage · {protocol.families.filter((family) => coveredFamilies.has(family)).length} / {protocol.families.length}</h2></div></div><p className="panel-padding">Expected families and competitors come from the protocol artifact. Presence below identifies result rows only; it does not certify scientific acceptance or a protocol lock.</p><DataTable label="Registered family artifact coverage" headers={['FAMILY', 'PAIRED INTERVAL ROWS', 'POLICY AGGREGATE ROWS']}><>{protocol.families.map((family) => <tr key={family}><td>{family}</td><td>{coveredFamilies.has(family) ? 'Present' : 'Unavailable'}</td><td>{protocol.policies?.map((policy) => `${policy}: ${rows.some((row) => row.family === family && (row.policy_id ?? row.policy) === policy) ? 'present' : 'unavailable'}`).join(' · ') || 'Expected policy list unavailable'}</td></tr>)}</></DataTable></section> : <div className="notice notice-neutral"><strong>FAMILY COVERAGE UNAVAILABLE</strong><span>The project protocol did not provide its expected family list.</span></div>}
    <div className="comparison-heading"><div><div className="eyebrow">PAIRED COMPARISONS</div><h2>Mean paired difference with bootstrap interval</h2></div><span className="mono">a − b · paired by seed within family</span></div>
    {reportState === 'ready' && report?.comparisons.length ? <section className="panel comparison-panel"><DataTable label="Paired benchmark comparisons with confidence intervals, direction and protocol role" headers={['FAMILY', 'A − B / METRIC', 'MEAN DIFFERENCE', 'CONFIDENCE INTERVAL', 'PAIRED SEEDS', 'READING', 'PROTOCOL ROLE']}><>{report.comparisons.map((item, index) => {
      const result = item.result
      const reading = readInterval(item)
      const h = isPrimary(item) ? holm[item.family] : undefined
      let role = 'Secondary · reported with equal prominence'
      if (isPrimary(item)) role = item.family === 'm0_well_specified' ? (verdict ? (verdict.m0_win ? 'Control: criterion met' : 'Control: criterion not met') : 'Control: no verdict') : h ? `Holm-adjusted p = ${fmt(h.adjusted_p, 3)} · ${h.reject && verdict?.misspecified_wins.includes(item.family) ? 'counted win' : 'not a counted win'}` : 'Primary · outside success criterion'
      const better = item.better_direction ? `${item.better_direction} is better` : 'target value, no direction'
      return <tr key={`${item.family}-${item.a}-${item.b}-${item.metric}-${index}`}><td><strong>{item.family}</strong></td><td>{item.a} − {item.b}<span className="subcell">{item.metric.replaceAll('_', ' ')} · {better}</span></td><td className="numeric">{result ? fmt(result.mean_diff, 4) : '— (no interval)'}</td><td className="numeric">{result ? `[${fmt(result.lo, 4)}, ${fmt(result.hi, 4)}]` : `— (${item.note ?? 'not computed'})`}<span className="subcell">{result ? `${fmt(result.level * 100, 0)}% percentile bootstrap · ${fmt(result.resamples, 0)} resamples` : ''}</span></td><td className="numeric">{item.n_pairs}<span className="subcell">{item.n_excluded_undefined} excluded (metric undefined)</span></td><td><span className={`interval-state ${reading.tone}`}>{reading.label}</span></td><td>{role}</td></tr>
    })}</></DataTable><p className="table-footnote">Each row is the evaluator's recorded interval; this view computes nothing. "Favours" is read only when the whole interval lies on one side of 0, using the metric's recorded direction. Families where adaptive_eig ties or loses are listed like every other.</p></section>
      : <Empty title={reportState === 'loading' ? 'Loading paired intervals…' : 'Paired intervals unavailable'} detail={reportState === 'loading' ? 'Reading the evaluator confidence interval report.' : rows.length ? 'Aggregate results exist, but benchmark-confidence-intervals.json is missing or invalid, so no comparison can be read. Means alone are not comparisons.' : 'The evaluator has not written benchmark-confidence-intervals.json, or it contains no paired comparisons.'} />}
    {state === 'ready' && rows.length > 0 ? <section className="panel aggregate-panel"><div className="panel-head"><div><div className="eyebrow">POLICY AGGREGATES</div><h2>Metric means and denominators</h2></div><span className="count-badge">{rows.length} rows</span></div><DataTable label="Per-policy aggregate metrics with seed counts" headers={cols.map((c) => c.replaceAll('_', ' ').toUpperCase())}><>{rows.map((row, i) => <tr key={i}>{cols.map((col) => <td key={col} className={/seed|n_|mean|sd/i.test(col) ? 'numeric' : ''}>{row[col] || '— (undefined)'}</td>)}</tr>)}</></DataTable><p className="table-footnote"><code>n_seeds</code> is the seed denominator; <code>n_undefined</code> counts seeds where the metric is undefined and excluded.</p></section>
      : report && <div className="notice notice-neutral"><strong>AGGREGATES UNAVAILABLE</strong><span>benchmark-results.csv is missing; paired intervals above are still the evaluator's record.</span></div>}
    <DevelopmentTiming />
    <div className="metric-notes"><div><strong>Brier score</strong><span>Lower is better; squared probability error against hidden simulated truth, every 6 h.</span></div><div><strong>High-impact recall at 5</strong><span>Higher is better; undefined on seeds with no high-impact source, which are excluded and counted.</span></div><div><strong>Corroboration time</strong><span>Lower is faster; sources never corroborated are right-censored at the horizon.</span></div></div>
  </>
}

function Comparison({ run, ...bench }: { run: RunRecord } & BenchmarkProps) {
  return <div className="page"><SectionTitle eyebrow="F / EVALUATION" title="Policy comparison" description="Paired benchmark intervals and the evaluator's recorded protocol verdict, read from evaluator output." />
    <div className="notice notice-neutral"><strong>RUN SCOPE</strong><span>The selected artifact is one run: policy <code>{run.policy_id}</code>, seed <code>{run.seed}</code>. A single run cannot establish comparative performance; the table below comes from the benchmark output.</span></div>
    <BenchmarkPanels {...bench} />
  </div>
}

function Method({ run }: { run: RunRecord }) {
  const copy = async () => { await navigator.clipboard.writeText(`python -m aether.cli simulate --config <pinned-config-path> --policies ${run.policy_id} --seed ${run.seed}`) }
  return <div className="page methodology"><SectionTitle eyebrow="G / METHODS & PROVENANCE" title="How to read this run" description="Configuration identity, record provenance, and limitations attached to the archived output." />
    <div className="method-grid"><section className="panel"><div className="panel-head"><div><div className="eyebrow">REPRODUCIBILITY</div><h2>Run identity</h2></div></div><dl className="key-values"><dt>Run ID</dt><dd className="mono">{run.run_id}</dd><dt>Scenario</dt><dd>{run.scenario_id} · {run.family}</dd><dt>Seed</dt><dd className="mono">{run.seed}</dd><dt>Model config SHA-256</dt><dd className="mono hash-value">{run.model_config_hash}</dd><dt>Truth config SHA-256</dt><dd className="mono hash-value">{run.truth_config_hash}</dd><dt>Code version</dt><dd className="mono">{run.code_version}</dd></dl><button className="button" onClick={() => void copy()} title="Copies a command template; replace the config placeholder with the pinned file path">Copy reproduction command template</button><p className="fine-print">The run record does not include its config file path or package lock. Replace the placeholder with the pinned config used to create this artifact.</p></section>
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">PROVENANCE CLASSES</div><h2>Evidence labels</h2></div></div><div className="provenance-list"><div><Provenance kind="REAL_OBSERVATION"/><span>Provider published historic observation. No real plume records are included in this run contract.</span></div><div><Provenance kind="MODEL_INFERENCE"/><span>Belief state estimated by the model from admissible evidence.</span></div><div><Provenance kind="SIMULATED_OBSERVATION"/><span>Virtual acquisition generated by the simulator.</span></div><div><Provenance kind="SIMULATED_GROUND_TRUTH"/><span>Evaluator only. Hidden truth is not included in this run record.</span></div></div></section></div>
    <section className="panel method-equations"><div className="panel-head"><div><div className="eyebrow">INTERPRETATION</div><h2>Scope and limitations</h2></div></div><div className="method-columns"><div><h3>What this artifact contains</h3><p>One simulated policy run, candidate windows, recorded solver plans, simulated acquisition outcomes and model belief snapshots. Values are shown from the stored records.</p></div><div><h3>What this artifact does not establish</h3><p>It does not show real satellite tasking, verified source attribution, measured emissions reduction, or comparative policy performance. Hidden simulated truth is scored separately.</p></div><div><h3>Missing values</h3><p>A blank or unavailable value remains unavailable. Invalid acquisitions and unobserved periods are not treated as valid non-detections.</p></div></div></section>
    <RunManifest run={run} />
    <div className="method-citation"><span className="method-mark">i</span><span>Parameter and method references are maintained in <code>Implementation/Parameter_Register.md</code> and the project requirements document. Data license details must accompany any real observation artifact.</span></div>
  </div>
}
