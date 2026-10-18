import { useCallback, useEffect, useState } from 'react'
import './live-context.css'

type Satellite = { name: string; norad_id: number; epoch_utc: string; latitude_deg: number | null; longitude_deg: number | null; altitude_km: number | null; error: string | null }
type Feed = { id: string; source_url: string; retrieved_at_utc: string; sha256: string; age_s: number; stale: boolean }
type Granule = { id: string; title: string; observed_at_utc: string | null; catalog_updated_at_utc: string | null; source_url: string }
type Context = { status: string; computed_at_utc: string; error: string | null; satellites: Satellite[]; feeds: Feed[]; granules: Granule[] }

function timestamp(value: string | null): string {
  const date = value ? new Date(value) : null
  return date && Number.isFinite(date.getTime()) ? date.toISOString().replace('T', ' ') : 'Unavailable'
}
function number(value: number | null): string { return value !== null && Number.isFinite(value) ? value.toFixed(2) : 'Unavailable' }

export default function LiveContext({ embedded = false }: { embedded?: boolean }) {
  const [data, setData] = useState<Context | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const refresh = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError('')
    try {
      const response = await fetch('/api/live-context', { signal, cache: 'no-store' })
      if (!response.ok) throw new Error(`Current-data context unavailable (HTTP ${response.status}).`)
      const value: Context = await response.json()
      if (!value || typeof value.computed_at_utc !== 'string' || !Array.isArray(value.satellites) || !Array.isArray(value.feeds) || !Array.isArray(value.granules)) throw new Error('Invalid context response.')
      if (!signal?.aborted) setData(value)
    } catch (reason) {
      if (!signal?.aborted) setError(reason instanceof Error ? reason.message : 'Could not load provider context.')
    } finally { if (!signal?.aborted) setLoading(false) }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    void refresh(controller.signal)
    return () => controller.abort()
  }, [refresh])

  const Container = embedded ? 'section' : 'main'
  return <div className="live-context">
    {!embedded && <><a className="skip-link" href="#live-main">Skip to content</a><header className="topbar"><a className="brand" href="/">AETHER<small>SATELLITE CONTEXT</small></a><a className="button quiet" href="/">Open planning replay</a></header></>}
    <Container id="live-main" className="live-main" tabIndex={-1}>
      <div className="section-title"><div><div className="eyebrow">PUBLIC PROVIDER INPUTS · READ ONLY</div><h1>Current satellite context</h1><p>Real published orbital elements and NASA catalogue metadata. Satellite positions are propagated estimates, not telemetry. These inputs do not change the recorded planning experiment.</p></div><button className="button" disabled={loading} onClick={() => void refresh()}>{loading ? 'Loading…' : 'Update position estimates'}</button></div>
      <p className="live-notice">No satellite commanding. No live methane measurement is claimed. Catalogue retrieval time and observation time are different. Upstream refresh is limited to once every two hours.</p>
      <div role="status" aria-live="polite">{error || (data ? `Position calculation UTC: ${timestamp(data.computed_at_utc)}` : 'Loading provider context…')}</div>
      {data?.error && <p role="alert">Provider refresh stopped: {data.error}. Any retained data below remain labelled with their original retrieval time.</p>}
      {data?.status === 'unavailable' && <section className="panel live-panel"><h2>No provider snapshot available</h2><p>The deployment has not fetched current inputs. The planning replay remains available.</p></section>}
      {!!data?.satellites.length && <section className="panel live-panel"><div className="eyebrow">CELESTRAK GP · SGP4 / SKYFIELD</div><h2>Real Earth-observation spacecraft</h2><p>Landsat 8 and 9 provide orbital context here. AETHER does not claim access to their sensors or use these positions as virtual planner windows.</p>
        <svg className="live-orbit-map" viewBox="0 0 720 360" role="img" aria-label="Schematic longitude-latitude plot of propagated satellite subpoints; exact values are in the following table">
          <rect x="0" y="0" width="720" height="360" fill="#eef2ed" />
          {[90, 180, 270].map(y => <line key={`y${y}`} x1="0" y1={y} x2="720" y2={y} stroke="#bcc8c0" />)}
          {[180, 360, 540].map(x => <line key={`x${x}`} x1={x} y1="0" x2={x} y2="360" stroke="#bcc8c0" />)}
          {data.satellites.map(s => s.latitude_deg !== null && s.longitude_deg !== null && <g key={s.norad_id}><circle cx={(s.longitude_deg + 180) * 2} cy={(90 - s.latitude_deg) * 2} r="6" fill="#185e51" /><text x={(s.longitude_deg + 180) * 2} y={(90 - s.latitude_deg) * 2 - 12} textAnchor={s.longitude_deg > 120 ? 'end' : s.longitude_deg < -120 ? 'start' : 'middle'} fontSize="14">{s.name}</text></g>)}
        </svg><p>Schematic coordinate grid; no coverage footprint or pass feasibility is implied.</p>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Propagated satellite positions"><table><caption>SGP4 position estimates at the calculation time above</caption><thead><tr>{['Spacecraft / NORAD', 'Element epoch UTC', 'Latitude °', 'Longitude °', 'Altitude km', 'Status'].map(h => <th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{data.satellites.map(s => <tr key={s.norad_id}><th scope="row">{s.name} / {s.norad_id}</th><td>{timestamp(s.epoch_utc)}</td><td>{number(s.latitude_deg)}</td><td>{number(s.longitude_deg)}</td><td>{number(s.altitude_km)}</td><td>{s.error || 'Propagated estimate'}</td></tr>)}</tbody></table></div>
      </section>}
      {!!data?.granules.length && <section className="panel live-panel"><div className="eyebrow">NASA CMR · EMIT V002 · GLOBAL CATALOGUE</div><h2>Latest published matching EMIT entries</h2><p>Sorted by observation time, not download time. These are discovery metadata, not newly ingested plume measurements or evidence of present emissions. Raster downloads may require Earthdata login.</p><div className="table-wrap" tabIndex={0} role="region" aria-label="NASA EMIT catalogue entries"><table><caption>Five newest matching catalogue entries returned by NASA</caption><thead><tr><th scope="col">Provider record</th><th scope="col">Observed UTC</th><th scope="col">Catalogue updated UTC</th></tr></thead><tbody>{data.granules.map(g => <tr key={g.id}><th scope="row"><a href={g.source_url} target="_blank" rel="noreferrer">{g.title}</a></th><td>{timestamp(g.observed_at_utc)}</td><td>{timestamp(g.catalog_updated_at_utc)}</td></tr>)}</tbody></table></div></section>}
      <section className="panel live-panel"><h2>Retrieval evidence</h2><p>The button recalculates positions from the cache. It does not download again or refresh old observations. A refresh worker retrieves new published inputs every two hours; without that worker this view is a timestamped cached snapshot.</p>{data?.feeds.map(f => <div className="live-feed" key={f.id}><h3>{f.id === 'emit' ? 'NASA EMIT catalogue' : 'CelesTrak orbital elements'} · {f.stale ? 'STALE CACHE' : 'CACHED PROVIDER INPUT'}</h3><dl><dt>Retrieved UTC</dt><dd>{timestamp(f.retrieved_at_utc)}</dd><dt>Cache age</dt><dd>{number(f.age_s / 3600)} h</dd><dt>Provider URL</dt><dd><a href={f.source_url} target="_blank" rel="noreferrer">{f.source_url}</a></dd><dt>Original response SHA-256</dt><dd className="mono">{f.sha256}</dd></dl></div>)}</section>
    </Container>
  </div>
}
