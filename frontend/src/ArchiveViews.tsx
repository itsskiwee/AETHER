import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { BeliefSnapshot, BenchmarkComparison, BenchmarkProtocol, BenchmarkReport, BenchmarkRow, Plan, RunRecord } from './types'
import { DevelopmentTiming, HistoricalContext, RunManifest } from './ArtifactEvidence'
import { craftName } from './fleet'
import './benchmark.css'
import './project.css'

type Screen = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G'

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

export function ScreenContent({ screen, run, benchmarks, benchmarkState, report, reportState, protocol }: { screen: Screen; run: RunRecord; benchmarks: BenchmarkRow[]; benchmarkState: string; report: BenchmarkReport | null; reportState: string; protocol: BenchmarkProtocol | null }) {
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

function Overview({ run }: { run: RunRecord }) {
  const accepted = run.windows.filter((item) => item.feasible).length
  const rejected = run.windows.length - accepted
  const valid = run.acquisitions.filter((item) => item.outcome === 'DETECTION' || item.outcome === 'VALID_NON_DETECTION').length
  const plan = run.plans.at(-1)
  const policies = [...new Set(run.plans.map((item) => item.policy_id))]
  const spacecraft = [...new Set(run.windows.map((item) => item.spacecraft_id))]
  return <div className="page">
    <SectionTitle eyebrow="RUN OVERVIEW" title={run.scenario_id.replaceAll('_', ' ')} description="A traceable replay of one simulated observation planning run." right={<Provenance kind="SIMULATED_OBSERVATION" />} />
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
  const selectedSource = new URLSearchParams(location.search).get('source')
  useEffect(() => { if (selectedSource) document.getElementById(`source-row-${selectedSource}`)?.scrollIntoView({ block: 'nearest' }) }, [selectedSource])
  const coords = run.sources
  const seededCount = run.input_dataset?.seeded_source_count ?? coords.filter((source) => source.seeded_from_plume_id !== null).length
  const fillCount = run.input_dataset?.uniform_fill_count ?? coords.filter((source) => source.seeded_from_plume_id === null).length
  const minLon = Math.min(...coords.map((s) => s.lon), -104.5), maxLon = Math.max(...coords.map((s) => s.lon), -101)
  const minLat = Math.min(...coords.map((s) => s.lat), 30.8), maxLat = Math.max(...coords.map((s) => s.lat), 33.5)
  const lonSpan = Math.max(maxLon - minLon, 0.001), latSpan = Math.max(maxLat - minLat, 0.001)
  return <div className="page"><SectionTitle eyebrow="SOURCE HYPOTHESES" title="Geographic context" description="Locations are source hypotheses from this run. The map is paired with a keyboard accessible source table." />
    <div className="map-layout"><div className="map-panel" aria-label="Schematic source location plot">
      <svg viewBox="0 0 720 390" role="img" aria-labelledby="map-title map-desc"><title id="map-title">Source hypothesis locations</title><desc id="map-desc">Schematic longitude and latitude plot of source hypotheses. No basemap or facility attribution is included.</desc>
        <rect x="0" y="0" width="720" height="390" fill="#f6f7f4" />
        {[0, 1, 2, 3, 4].map((i) => <g key={i}><line x1={70 + i * 140} x2={70 + i * 140} y1="24" y2="344" className="map-grid"/><line x1="70" x2="630" y1={24 + i * 80} y2={24 + i * 80} className="map-grid" /></g>)}
        <text x="70" y="372" className="map-axis">{fmt(minLon, 2)}°W</text><text x="570" y="372" className="map-axis">{fmt(maxLon, 2)}°W</text><text x="18" y="33" className="map-axis">{fmt(maxLat, 2)}°N</text><text x="18" y="345" className="map-axis">{fmt(minLat, 2)}°N</text>
        {coords.map((source, i) => { const x = 70 + ((source.lon - minLon) / lonSpan) * 560; const y = 344 - ((source.lat - minLat) / latSpan) * 320; return <g key={source.id}>{source.seeded_from_plume_id ? <circle cx={x} cy={y} r="7" className="source-dot"/> : <rect x={x - 6} y={y - 6} width="12" height="12" className="source-fill-dot"/>}<text x={x + 10} y={y + 4} className="source-label">{i + 1}</text></g> })}
      </svg><div className="map-legend"><span><i className="legend-dot" /> Plume-seeded hypothesis</span><span><i className="uniform-fill-legend" /> Uniform-fill hypothesis</span><span className="map-note">schematic coordinates · no basemap</span></div>
    </div><section className="panel source-panel"><div className="panel-head"><div><div className="eyebrow">SOURCE INDEX</div><h2>{coords.length} hypotheses</h2></div></div>
      <p className="source-origin-counts"><span>historical plume seeded: {seededCount}</span><span>uniform synthetic fill: {fillCount}</span></p>
      {coords.length ? <DataTable label="Source hypothesis coordinates" headers={['SOURCE', 'LONGITUDE', 'LATITUDE', 'STATUS', 'LOCATION LINEAGE', 'ATTRIBUTION']}><>{coords.map((s, i) => <tr key={s.id} id={`source-row-${s.id}`} className={selectedSource === s.id ? 'mc-highlighted-source' : undefined}><td><strong>{String(i + 1).padStart(2, '0')}</strong><span className="subcell">{s.id}</span></td><td className="mono">{fmt(s.lon, 4)}°</td><td className="mono">{fmt(s.lat, 4)}°</td><td><Provenance kind="MODEL_INFERENCE" /></td><td>{s.seeded_from_plume_id ? <><span>Seeded from historical plume: {s.seeded_from_plume_id}</span></> : <><span>Uniform simulated fill</span><span className="subcell">No historical plume ID is linked</span></>}</td><td>{s.attribution_status}</td></tr>)}</></DataTable> : <Empty title="No source locations" detail="This run contains no source hypotheses." />}
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
  return <div className="page"><SectionTitle eyebrow="ORBITAL AVAILABILITY" title="Observation windows" description="Virtual spacecraft opportunities and rejected candidates from the recorded run." right={<button className={`button ${showRejected ? 'selected' : ''}`} onClick={() => setShowRejected(!showRejected)}>{showRejected ? 'Hide rejected' : `Show rejected · ${rejected.length}`}</button>} />
    {!run.windows.length ? <Empty title="No windows in this run" detail="The run artifact contains no candidate windows." /> : <>
      <div className="timeline-panel"><div className="timeline-heading"><div><span className="eyebrow">WINDOW TIMELINE</span><h2>Pass opportunity by virtual spacecraft</h2></div><div className="timeline-legend"><span><i className="line-swatch feasible"/>FEASIBLE</span><span><i className="line-swatch rejected"/>REJECTED</span></div></div>
        <div className="timeline-axis"><span>{utc(new Date(start).toISOString())}</span><span>{utc(new Date(finish).toISOString())}</span></div>
        {Object.entries(groupBy(run.windows, (w) => w.spacecraft_id)).map(([sat, windows]) => <div className="timeline-row" key={craftName(sat)}><div className="timeline-label"><span className="satellite-mark">▤</span><strong>{craftName(sat)}</strong></div><div className="timeline-track">{(windows ?? []).filter((w) => showRejected || w.feasible).map((w) => { const left = (Date.parse(w.start_utc) - start) / span * 100; const width = Math.max((Date.parse(w.end_utc) - Date.parse(w.start_utc)) / span * 100, 0.45); return <button key={w.id} className={`window-mark ${w.feasible ? 'ok' : 'no'}`} style={{ left: `${left}%`, width: `${Math.max(width, 0.45)}%` }} title={`${w.id} · ${w.feasible ? 'feasible' : w.rejection_reasons.join(', ')}`} aria-label={`${w.id}, ${w.feasible ? 'feasible' : `rejected: ${w.rejection_reasons.join(', ')}`}`} /> })}</div></div>)}
      </div>
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">WINDOW REGISTER</div><h2>{showRejected ? 'All candidates' : 'Feasible candidates'}</h2></div><span className="count-badge">{showRejected ? run.windows.length : feasible.length}</span></div>
        <DataTable label="Observation window details" headers={['WINDOW / SOURCE', 'SPACECRAFT', 'START (UTC)', 'OFF-NADIR', 'DURATION', 'STATUS / REASON']}><>{(showRejected ? run.windows : feasible).map((w) => <tr key={w.id}><td><strong className="mono">{w.id}</strong><span className="subcell">{w.source_id} · pass {w.pass_id}</span></td><td>{craftName(w.spacecraft_id)}<span className="subcell">{w.sensor_id}</span></td><td className="mono">{utc(w.start_utc)}</td><td className="numeric">{fmt(w.min_off_nadir_deg)}°</td><td className="numeric">{fmt(w.duration_s, 1)} s</td><td>{w.feasible ? <span className="state-label good">FEASIBLE · {w.options.length} starts</span> : <span className="state-label bad">{w.rejection_reasons.join(' · ')}</span>}</td></tr>)}</></DataTable>
      </section>
    </>}
  </div>
}
function groupBy<T, K extends string>(items: T[], key: (item: T) => K): Record<K, T[]> {
  return items.reduce((acc, item) => { const k = key(item); (acc[k] ??= []).push(item); return acc }, {} as Record<K, T[]>)
}

function Beliefs({ run }: { run: RunRecord }) {
  const sources = run.sources.map((s) => s.id)
  const [sourceId, setSourceId] = useState(new URLSearchParams(location.search).get('source') ?? sources[0] ?? '')
  const selected = run.beliefs.filter((belief) => belief.source_id === (sources.includes(sourceId) ? sourceId : sources[0])).sort(byTime)
  const acquisitions = run.acquisitions.filter((item) => item.source_id === (sources.includes(sourceId) ? sourceId : sources[0])).sort(byTime)
  const firstTime = Date.parse(selected[0]?.state_time_utc ?? '')
  const timeSpan = Math.max(Date.parse(selected.at(-1)?.state_time_utc ?? '') - firstTime, 1)
  const timeX = (belief: BeliefSnapshot) => 42 + (Date.parse(belief.state_time_utc) - firstTime) * 540 / timeSpan
  const points = selected.map((belief) => `${timeX(belief)},${210 - belief.p_active * 170}`).join(' ')
  return <div className="page"><SectionTitle eyebrow="SOURCE SCIENCE" title="Belief history" description="Model-inferred activity probability and evidence sequence. Missing or invalid observations do not count as non-detections." right={<label className="select-control">SOURCE<select aria-label="Select source" value={sourceId} onChange={(e) => setSourceId(e.target.value)}>{sources.map((s) => <option key={s}>{s}</option>)}</select></label>} />
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
  return <div className="page"><SectionTitle eyebrow="PLAN REVIEW" title="Planner decisions" description="Recorded utility values, solver status, and revision causes. This view does not recompute a schedule." right={plans.length > 0 && <label className="select-control">PLAN REVISION<select value={plan?.revision ?? ''} onChange={(e) => setRevision(Number(e.target.value))}>{plans.map((p) => <option key={p.revision} value={p.revision}>Revision {p.revision}</option>)}</select></label>} />
    {!plan ? <Empty title="No plans in this run" detail="Planner decisions are available when plan records are present in run.json." /> : <>
      <div className="plan-summary"><div><span className="eyebrow">POLICY</span><strong>{plan.policy_id}</strong></div><div><span className="eyebrow">SOLVER</span><strong><span className={`solver-pill ${plan.solver_status.toLowerCase()}`}>{plan.solver_status}</span></strong></div><div><span className="eyebrow">OBJECTIVE</span><strong>{plan.objective_value == null ? 'Unavailable' : fmt(plan.objective_value)}</strong></div><div><span className="eyebrow">SOLVE TIME</span><strong>{plan.runtime_s == null ? 'Not recorded' : `${fmt(plan.runtime_s, 3)} s`}</strong></div><div><span className="eyebrow">VALIDATION</span><strong>{plan.validation_ok == null ? 'Unavailable' : plan.validation_ok ? 'Passed' : 'Violations'}</strong></div></div>
      <div className="notice notice-cause"><div className="cause-icon" aria-hidden="true">↻</div><div><span className="eyebrow">REVISION {plan.revision} · CAUSE</span><strong>{plan.cause}</strong><span className="mono cause-time">{utc(plan.created_at_sim_utc)}</span></div></div>
      <div className="notice notice-neutral"><strong>INDEPENDENT CHECKER</strong><span>{validation ? `Revision ${validation.plan_revision}: ${validation.ok ? 'passed' : 'failed'} · ${validation.violations.length} violations · ${validation.checker_version}` : 'No independent validation record for this revision.'} · {run.validations.length} validation records for {run.plans.length} plans.</span></div>
      {forecastEvents.length > 0 && <section className="panel"><details><summary>Recorded forecast events ({forecastEvents.length})</summary><DataTable label="Recorded forecast revisions" headers={['TIME (UTC)', 'EVENT', 'RECORDED PAYLOAD']}><>{forecastEvents.map((event) => <tr key={event.event_id}><td className="mono">{utc(event.event_time_sim_utc)}</td><td>{event.event_type}</td><td><code>{JSON.stringify(event.payload)}</code></td></tr>)}</></DataTable></details></section>}
      {changed && <section className="panel diff-panel"><div className="panel-head"><div><div className="eyebrow">REVISION DIFF</div><h2>Decision changes from revision {previous?.revision}</h2></div><span className="count-badge">{changed.added.length + changed.removed.length} changes</span></div><div className="diff-columns"><div><span className="eyebrow">ADDED</span>{changed.added.length ? changed.added.map((id) => <div className="diff-item added" key={id}>+ {id}</div>) : <span className="muted">No additions</span>}</div><div><span className="eyebrow">REMOVED</span>{changed.removed.length ? changed.removed.map((id) => <div className="diff-item removed" key={id}>− {id}</div>) : <span className="muted">No removals</span>}</div></div></section>}
      <div className="planner-layout"><section className="panel"><div className="panel-head"><div><div className="eyebrow">CANDIDATE UTILITIES</div><h2>{utilities.length} recorded candidates</h2></div></div>{utilities.length ? <DataTable label="Planner candidate utilities" headers={['CANDIDATE', 'EIG', 'P(VALID)', 'UTILITY', 'SELECTION']}><>{utilities.map((u) => <tr key={u.window_id}><td className="mono">{u.window_id}<span className="subcell">{windows.get(u.window_id)?.source_id ?? 'Source unavailable'}</span></td><td className="numeric">{fmt(u.expected_info_gain_bits, 4)} bits</td><td className="numeric">{fmt(u.p_valid_forecast)}</td><td className="numeric">{fmt(u.utility, 4)}</td><td>{selectedIds.has(u.window_id) ? <span className="state-label good">SELECTED</span> : <span className="muted">NOT SELECTED</span>}</td></tr>)}</></DataTable> : <p className="muted panel-padding">No utility records for this revision.</p>}</section>
        <aside className="panel selected-panel"><div className="panel-head"><div><div className="eyebrow">SELECTED SCHEDULE</div><h2>{plan.selections.length} options</h2></div></div>{plan.selections.length ? <ol>{plan.selections.map((selection, index) => { const w = windows.get(selection.window_id); const option = w?.options.find((item) => item.option_id === selection.option_id); return <li key={selection.option_id}><span className="selected-index">{String(index + 1).padStart(2, '0')}</span><div><strong className="mono">{selection.option_id}</strong><span>{w && option ? `${craftName(w.spacecraft_id)} · ${w.source_id} · ${utc(option.start_utc)}` : 'Window details unavailable'}</span></div></li> })}</ol> : <p className="muted">The recorded plan selected no options.</p>}</aside></div>
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
  return <div className="page"><SectionTitle eyebrow="EVALUATION" title="Policy comparison" description="Paired benchmark intervals and the evaluator's recorded protocol verdict, read from evaluator output." />
    <div className="notice notice-neutral"><strong>RUN SCOPE</strong><span>The selected artifact is one run: policy <code>{run.policy_id}</code>, seed <code>{run.seed}</code>. A single run cannot establish comparative performance; the table below comes from the benchmark output.</span></div>
    <BenchmarkPanels {...bench} />
  </div>
}

function Method({ run }: { run: RunRecord }) {
  const copy = async () => { await navigator.clipboard.writeText(`python -m aether.cli simulate --config <pinned-config-path> --policies ${run.policy_id} --seed ${run.seed}`) }
  return <div className="page methodology"><SectionTitle eyebrow="METHODS & PROVENANCE" title="How to read this run" description="Configuration identity, record provenance, and limitations attached to the archived output." />
    <div className="method-grid"><section className="panel"><div className="panel-head"><div><div className="eyebrow">REPRODUCIBILITY</div><h2>Run identity</h2></div></div><dl className="key-values"><dt>Run ID</dt><dd className="mono">{run.run_id}</dd><dt>Scenario</dt><dd>{run.scenario_id} · {run.family}</dd><dt>Seed</dt><dd className="mono">{run.seed}</dd><dt>Model config SHA-256</dt><dd className="mono hash-value">{run.model_config_hash}</dd><dt>Truth config SHA-256</dt><dd className="mono hash-value">{run.truth_config_hash}</dd><dt>Code version</dt><dd className="mono">{run.code_version}</dd></dl><button className="button" onClick={() => void copy()} title="Copies a command template; replace the config placeholder with the pinned file path">Copy reproduction command template</button><p className="fine-print">The run record does not include its config file path or package lock. Replace the placeholder with the pinned config used to create this artifact.</p></section>
      <section className="panel"><div className="panel-head"><div><div className="eyebrow">PROVENANCE CLASSES</div><h2>Evidence labels</h2></div></div><div className="provenance-list"><div><Provenance kind="REAL_OBSERVATION"/><span>Provider-published historical observation. This run links its pinned dataset; inspect the actual records and lineage in Sources & observations.</span></div><div><Provenance kind="MODEL_INFERENCE"/><span>Belief state estimated by the model from admissible evidence.</span></div><div><Provenance kind="SIMULATED_OBSERVATION"/><span>Virtual acquisition generated by the simulator.</span></div><div><Provenance kind="SIMULATED_GROUND_TRUTH"/><span>Evaluator only. Hidden truth is not included in this run record.</span></div></div></section></div>
    <section className="panel method-equations"><div className="panel-head"><div><div className="eyebrow">INTERPRETATION</div><h2>Scope and limitations</h2></div></div><div className="method-columns"><div><h3>What this artifact contains</h3><p>One simulated policy run, candidate windows, recorded solver plans, simulated acquisition outcomes and model belief snapshots. Values are shown from the stored records.</p></div><div><h3>What this artifact does not establish</h3><p>It does not show real satellite tasking, verified source attribution, measured emissions reduction, or comparative policy performance. Hidden simulated truth is scored separately.</p></div><div><h3>Missing values</h3><p>A blank or unavailable value remains unavailable. Invalid acquisitions and unobserved periods are not treated as valid non-detections.</p></div></div></section>
    <RunManifest run={run} />
    <div className="method-citation"><span className="method-mark">i</span><span>Parameter and method references are maintained in <code>Implementation/Parameter_Register.md</code> and the project requirements document. Data license details must accompany any real observation artifact.</span></div>
  </div>
}
