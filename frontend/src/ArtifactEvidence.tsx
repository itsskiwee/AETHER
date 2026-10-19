import { useEffect, useState } from 'react'
import type { InputDatasetRef, RunRecord } from './types'

type JsonObject = Record<string, unknown>
type DatasetSummary = Pick<InputDatasetRef, 'dataset_id' | 'manifest_path' | 'manifest_sha256' | 'normalized_sha256' | 'record_count'>
  & Partial<Pick<InputDatasetRef, 'in_region_count' | 'seeded_source_count' | 'uniform_fill_count'>>
type HistoricalObservation = {
  id: string
  native_id: string
  provenance_class: 'REAL_OBSERVATION'
  acquisition_time_utc: string
  lon: number
  lat: number
  emission_rate_kg_h: number | null
  emission_rate_uncertainty_kg_h: number | null
  missing_rate_reason: string | null
  uncertainty_kind: 'STDDEV' | 'INTERVAL' | 'UNKNOWN'
  quality_flags: string[]
  provider: string
  dataset_version: string
  source: {
    provider: string
    dataset: string
    version: string
    url: string
    license_url: string | null
    citation_text: string
    retrieved_at_utc: string | null
    sha256: string
  }
}
type HistoricalContextData = {
  status: 'pinned' | 'synthetic_only'
  input_dataset: DatasetSummary | null
  manifest: JsonObject | null
  observations: HistoricalObservation[]
}
type Timing = {
  note?: string
  complete_comparison_elapsed_s: number
  runs: { run_id: string; complete_run_elapsed_s: number }[]
}

function object(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function parseInputDataset(value: unknown): DatasetSummary {
  if (!object(value)) throw new Error('Dataset reference must be an object')
  const stringFields = ['dataset_id', 'manifest_path', 'manifest_sha256', 'normalized_sha256'] as const
  const countFields = ['record_count', 'in_region_count', 'seeded_source_count', 'uniform_fill_count'] as const
  if (stringFields.some((key) => typeof value[key] !== 'string')) throw new Error('Dataset reference is missing identity fields')
  if (countFields.some((key) => key in value && (typeof value[key] !== 'number' || !Number.isInteger(value[key]) || value[key] < 0))) throw new Error('Dataset reference has invalid counts')
  if (typeof value.record_count !== 'number' || !Number.isInteger(value.record_count) || value.record_count < 0) throw new Error('Dataset reference has no valid record count')
  return value as unknown as DatasetSummary
}

function parseHistoricalContext(value: unknown): HistoricalContextData {
  if (!object(value) || !Array.isArray(value.observations)) throw new Error('Historical context response has an invalid shape')
  if (value.status === 'synthetic_only') {
    if (value.input_dataset !== null || value.manifest !== null || value.observations.length !== 0) throw new Error('Synthetic-only response contains dataset records')
    return value as unknown as HistoricalContextData
  }
  if (value.status !== 'pinned' || !object(value.manifest)) throw new Error('Historical context status is invalid')
  parseInputDataset(value.input_dataset)
  for (const item of value.observations) {
    if (!object(item) || item.provenance_class !== 'REAL_OBSERVATION' || typeof item.id !== 'string'
      || typeof item.native_id !== 'string' || typeof item.acquisition_time_utc !== 'string'
      || !Number.isFinite(item.lon) || !Number.isFinite(item.lat)
      || (item.emission_rate_kg_h !== null && !Number.isFinite(item.emission_rate_kg_h))
      || (item.emission_rate_uncertainty_kg_h !== null && !Number.isFinite(item.emission_rate_uncertainty_kg_h))
      || (item.missing_rate_reason !== null && typeof item.missing_rate_reason !== 'string')
      || !['STDDEV', 'INTERVAL', 'UNKNOWN'].includes(String(item.uncertainty_kind))
      || !Array.isArray(item.quality_flags) || !object(item.source)) {
      throw new Error('Historical observation has an invalid shape')
    }
    if (typeof item.source.url !== 'string' || typeof item.source.sha256 !== 'string'
      || typeof item.source.provider !== 'string') throw new Error('Historical source lineage is incomplete')
  }
  return value as unknown as HistoricalContextData
}

function parseTiming(value: unknown): Timing {
  if (!object(value) || !Array.isArray(value.runs)
    || typeof value.complete_comparison_elapsed_s !== 'number' || !Number.isFinite(value.complete_comparison_elapsed_s)
    || value.complete_comparison_elapsed_s <= 0
    || (value.note !== undefined && typeof value.note !== 'string')) throw new Error('Timing artifact has an invalid shape')
  for (const item of value.runs) {
    if (!object(item) || typeof item.run_id !== 'string' || typeof item.complete_run_elapsed_s !== 'number'
      || !Number.isFinite(item.complete_run_elapsed_s) || item.complete_run_elapsed_s <= 0) {
      throw new Error('Timing artifact contains an invalid run measurement')
    }
  }
  return value as unknown as Timing
}

function parseObject(value: unknown): JsonObject {
  if (!object(value)) throw new Error('Artifact must be a JSON object')
  return value
}

function useArtifact<T>(url: string, parse: (value: unknown) => T) {
  const [state, setState] = useState<{ url: string; data: T | null; status: string }>({ url, data: null, status: 'Loading artifact…' })
  useEffect(() => {
    const controller = new AbortController()
    setState({ url, data: null, status: 'Loading artifact…' })
    const load = async () => {
      let lastError: unknown
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const response = await fetch(url, { signal: controller.signal, headers: { Accept: 'application/json' } })
          if (!response.ok) {
            let detail = ''
            try {
              const body: unknown = await response.json()
              if (object(body) && typeof body.detail === 'string') detail = body.detail
            } catch { /* the status still explains an unavailable artifact */ }
            throw new Error(response.status === 404 ? 'Artifact unavailable.' : `Artifact could not be validated or read (${response.status})${detail ? `: ${detail}` : '.'}`)
          }
          const data = parse(await response.json() as unknown)
          if (!controller.signal.aborted) setState({ url, data, status: '' })
          return
        } catch (error) {
          lastError = error
          if (attempt < 2 && !controller.signal.aborted) await new Promise((resolve) => window.setTimeout(resolve, 180 * (attempt + 1)))
        }
      }
      if (!controller.signal.aborted) setState({ url, data: null, status: lastError instanceof Error ? lastError.message : 'Artifact unavailable.' })
    }
    void load()
    return () => controller.abort()
  }, [url, parse])
  return state.url === url ? state : { url, data: null, status: 'Loading artifact…' }
}

function fmt(value: number, digits = 3): string {
  return new Intl.NumberFormat('en-CA', { maximumFractionDigits: digits }).format(value)
}

function isWebUrl(value: string): boolean {
  return value.startsWith('https://') || value.startsWith('http://')
}

export function HistoricalContext({ run, summary = false }: { run?: RunRecord; summary?: boolean }) {
  const url = run ? `/api/runs/${encodeURIComponent(run.run_id)}/historical-context` : '/api/project/historical-context'
  const { data, status } = useArtifact(url, parseHistoricalContext)
  const projectMode = run === undefined
  return <section className="panel" aria-busy={!data && status === 'Loading artifact…'}>
    <div className="panel-head"><div><div className="eyebrow">REAL HISTORICAL OBSERVATIONS</div><h2>EMIT plume context</h2></div>
      {data?.status === 'pinned' ? <span className="tag tag-real_observation">REAL_OBSERVATION</span> : <span className="status-pill">NO DATASET PINNED</span>}
    </div>
    <p className="panel-padding">These plume detections provide historical location context. They do not establish activity at the virtual scenario epoch or set simulated truth. A missing plume row is not a non-detection.</p>
    {!data ? <p className="panel-padding" role="status">{status} {projectMode ? 'The configured project dataset could not be read.' : 'This run uses only its own pinned inputs; a current project dataset is not substituted.'}</p>
      : data.status === 'synthetic_only' ? <p className="panel-padding" role="status">{projectMode ? 'The project configuration selects synthetic-only source inputs. No real observation records are substituted.' : 'This run has no pinned historical dataset reference. Historical rows are not inferred from source locations.'}</p>
        : summary ? <div className="historical-dataset-summary"><strong>{data.input_dataset?.dataset_id}</strong><span>{data.observations.length} pinned historical plume records · REAL_OBSERVATION</span><span>Full source details and lineage appear on Sources.</span></div>
        : <>
          <div className="historical-dataset-summary"><strong>{data.input_dataset?.dataset_id}</strong><span>{data.observations.length} pinned plume records</span><span>Manifest SHA-256 <code>{data.input_dataset?.manifest_sha256}</code></span></div>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Historical plume evidence"><table><caption className="sr-only">Historical EMIT records with provider rates, uncertainty semantics, and source lineage</caption><thead><tr>
            {['OBSERVATION / PROVIDER', 'OBSERVED (UTC)', 'LOCATION', 'RATE (kg/h)', 'RATE UNCERTAINTY (kg/h)', 'SOURCE FILE SHA-256', 'QUALITY'].map((heading) => <th scope="col" key={heading}>{heading}</th>)}
          </tr></thead><tbody>{data.observations.map((item) => <tr key={item.id}>
            <td><strong>{item.native_id}</strong><span className="subcell">{item.id} · {item.provider} · V{item.dataset_version}</span>
              {isWebUrl(item.source.url) ? <a className="subcell" href={item.source.url} target="_blank" rel="noreferrer">Provider source ↗</a> : <span className="subcell">Source: {item.source.url}</span>}</td>
            <td className="mono">{item.acquisition_time_utc}</td>
            <td className="numeric">{fmt(item.lon, 5)}°, {fmt(item.lat, 5)}°</td>
            <td className="numeric">{item.emission_rate_kg_h === null ? `Not estimated (${item.missing_rate_reason ?? 'reason unavailable'})` : `${fmt(item.emission_rate_kg_h)} kg/h`}</td>
            <td className="numeric">{item.emission_rate_uncertainty_kg_h === null ? 'Unavailable' : `${fmt(item.emission_rate_uncertainty_kg_h)} kg/h`}
              <span className="subcell">Meaning: {item.uncertainty_kind === 'UNKNOWN' ? 'unknown; no interval or standard deviation is inferred' : item.uncertainty_kind}</span></td>
            <td className="mono hash-cell">{item.source.sha256}</td>
            <td>{item.quality_flags.length ? item.quality_flags.join(', ') : 'Not provided'}</td>
          </tr>)}</tbody></table></div>
          <details className="panel-padding"><summary>Dataset citation, retrieval evidence and input lineage</summary><pre className="artifact-json">{JSON.stringify(data.manifest, null, 2)}</pre></details>
        </>}
  </section>
}

export function RunManifest({ run }: { run: RunRecord }) {
  const { data, status } = useArtifact<JsonObject>(`/api/runs/${encodeURIComponent(run.run_id)}/manifest.json`, parseObject)
  return <section className="panel"><div className="panel-head"><h2>Archived input manifest</h2></div>{data ? <details className="panel-padding"><summary>Inspect input hashes, package versions, and dataset identity</summary><pre className="artifact-json">{JSON.stringify(data, null, 2)}</pre></details> : <p className="panel-padding" role="status">{status} Run record data remains available.</p>}</section>
}

export function DevelopmentTiming() {
  const { data, status } = useArtifact('/api/development-timing.json', parseTiming)
  return <section className="panel"><div className="panel-head"><h2>Measured development wall time</h2></div>
    <p className="panel-padding">Complete run and comparison elapsed times come from a separate performance artifact. Solver runtime is unavailable here. These measurements depend on the machine and workload.</p>
    {!data ? <p className="panel-padding" role="status">{status} Timing is unavailable; no zero is substituted.</p> : <>
      <p className="panel-padding">Complete comparison: {fmt(data.complete_comparison_elapsed_s)} s. {data.note ?? ''}</p>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Measured development timing"><table><caption className="sr-only">Measured development timing</caption><thead><tr><th scope="col">RUN ID</th><th scope="col">COMPLETE RUN ELAPSED (s)</th></tr></thead><tbody>{data.runs.map((item) => <tr key={item.run_id}><td>{item.run_id}</td><td className="numeric">{fmt(item.complete_run_elapsed_s)}</td></tr>)}</tbody></table></div>
    </>}
  </section>
}
