import { useEffect, useMemo, useRef, useState } from 'react'
import Globe, { type GlobeInstance } from 'globe.gl'
import { degreesLat, degreesLong, eciToGeodetic, gstime, json2satrec, propagate, type OMMJsonObject, type SatRec } from 'satellite.js'
import { craftName } from './fleet'
import './globe.css'

// Presentation view (UI-10). Two clocks, never mixed:
//  REAL      — published CelesTrak elements propagated (SGP4) to the viewer's current UTC time.
//  SIMULATED — the recorded AETHER demo replay: virtual fleet tracks (Skyfield, precomputed by
//              scripts/build_globe_data.py) and the planner's simulated acquisitions.

type RealSat = { norad_id: number; name: string; role: string; url: string; omm?: OMMJsonObject; retrieved_at_utc?: string; sha256?: string; refresh_status: string }
type Fleet = { id: string; altitude_km: number; inclination_deg: number; track: [number, number, number][] }
type Acq = { time_utc: string; spacecraft_id: string; source_id: string; outcome: string }
type Site = { id: string; lat: number; lon: number; plume_id: string | null }
type Mission = { label: string; epoch_utc: string; horizon_hours: number; track_step_s: number; sources: Site[]; fleet: Fleet[]; runs: { run_id: string; policy_id: string; acquisitions: Acq[] }[] }
type GlobeData = {
  missions?: Mission[]
  real_satellites: RealSat[]
  plume_sources: { id: string; lat: number; lon: number; plume_id: string | null }[]
  simulation: { scenario_id: string; epoch_utc: string; horizon_hours: number; track_step_s: number; fleet: Fleet[]; runs: { run_id: string; policy_id: string; acquisitions: Acq[] }[] }
}
type Marker = { kind: 'real' | 'sim'; id: string; label: string; lat: number; lng: number; alt_km: number }
type Path = { kind: 'real' | 'sim' | 'look'; points: [number, number, number][]; outcome?: string }

const EARTH_KM = 6371
const LOOK_WINDOW_S = 1200
// Replay speeds. 60x shows one ~95 min orbit in about 1.5 minutes; 1x is real time.
const SPEEDS: [number, string][] = [[1, 'Real time'], [10, '10×'], [60, '60×'], [300, '300×']]
const OUTCOME_COLOR: Record<string, string> = { DETECTION: '#e8743b', VALID_NON_DETECTION: '#7aa7e0', INVALID_ACQUISITION: '#a89a6a', NOT_OBSERVED: '#7d848c' }
const OUTCOME_LABEL: Record<string, string> = { DETECTION: 'Plume found', VALID_NON_DETECTION: 'Nothing found', INVALID_ACQUISITION: 'Look failed (cloud or geometry)', NOT_OBSERVED: 'Not observed' }
const SHORT_ROLE: Record<number, string> = { 25544: 'Carries NASA EMIT', 39084: 'Land imaging', 49260: 'Land imaging', 42969: 'Daily methane maps' }
const POLICY_NAME: Record<string, string> = { adaptive_eig: 'Adaptive planner (information gain)', largest_first: 'Baseline: largest source first' }

const utc = (iso: string) => Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)
const fmt = (n: number, d = 1) => n.toFixed(d)
const clock = (ms: number) => new Date(ms).toLocaleString('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' UTC'

function geodetic(rec: SatRec, at: Date): [number, number, number] | null {
  const pv = propagate(rec, at)
  const p = pv?.position
  if (!p || typeof p === 'boolean') return null
  const g = eciToGeodetic(p, gstime(at))
  return [degreesLat(g.latitude), degreesLong(g.longitude), g.height]
}

function simIndex(fleet: Fleet, seconds: number, step: number) {
  return Math.max(0, Math.min(fleet.track.length - 1, Math.round(seconds / step)))
}

export default function GlobeView() {
  const host = useRef<HTMLDivElement>(null)
  const globe = useRef<GlobeInstance | null>(null)
  const [data, setData] = useState<GlobeData | null>(null)
  const [error, setError] = useState('')
  const [now, setNow] = useState(() => Date.now())
  const [simS, setSimS] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(60)
  const [runIndex, setRunIndex] = useState(0)
  const [missionIndex, setMissionIndex] = useState(0)
  const [follow, setFollow] = useState(false)

  useEffect(() => {
    document.title = 'Globe · AETHER'
    fetch('/globe/globe-data.json').then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() }).then(setData).catch(e => setError(String(e)))
  }, [])

  const recs = useMemo(() => (data?.real_satellites ?? []).flatMap(s => s.omm ? [{ sat: s, rec: json2satrec(s.omm) }] : []), [data])
  const missions = useMemo<Mission[]>(() => data?.missions?.length ? data.missions : data ? [{ label: 'Recorded demo', ...data.simulation, sources: data.plume_sources }] : [], [data])
  const mission = missions[missionIndex]
  const run = mission?.runs[runIndex]
  const epochMs = mission ? utc(mission.epoch_utc) : 0
  const horizonS = (mission?.horizon_hours ?? 0) * 3600
  const simulatedSites = useMemo(() => (mission?.sources ?? []).filter(x => !x.plume_id), [mission])
  const chooseMission = (i: number) => { setMissionIndex(i); setRunIndex(0); setSimS(0); setPlaying(false) }

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    if (!playing || !horizonS) return
    const id = window.setInterval(() => setSimS(s => (s + speed * 0.25) % horizonS), 250)
    return () => window.clearInterval(id)
  }, [playing, speed, horizonS])

  useEffect(() => {
    if (!host.current || globe.current) return
    const g = new Globe(host.current)
      .globeImageUrl('/globe/earth-blue-marble.jpg')
      .bumpImageUrl('/globe/earth-topology.png')
      .backgroundColor('#0e1116')
      .atmosphereColor('#9db7d3')
      .atmosphereAltitude(0.1)
      .pointOfView({ lat: 28, lng: -100, altitude: 2.4 })
      .htmlTransitionDuration(0)
      .pathTransitionDuration(0)
      .pointsTransitionDuration(0)
      .htmlAltitude((d: object) => (d as Marker).alt_km / EARTH_KM)
      .htmlElement((d: object) => {
        const m = d as Marker
        const el = document.createElement('div')
        el.className = `globe-sat ${m.kind}`
        el.innerHTML = '<i></i><span></span>'
        el.querySelector('span')!.textContent = m.label
        el.title = m.kind === 'real' ? `${m.label}: real satellite, position calculated from published orbital elements` : `${m.label}: virtual satellite in the recorded simulation`
        return el
      })
      .pathPoints((d: object) => (d as Path).points)
      .pathPointLat((p: [number, number, number]) => p[0])
      .pathPointLng((p: [number, number, number]) => p[1])
      .pathPointAlt((p: [number, number, number]) => p[2] / EARTH_KM)
      .pathColor((d: object) => { const p = d as Path; return p.kind === 'real' ? 'rgba(255,255,255,0.35)' : p.kind === 'sim' ? 'rgba(224,164,58,0.55)' : OUTCOME_COLOR[p.outcome ?? ''] ?? '#fff' })
      .pathStroke((d: object) => ((d as Path).kind === 'look' ? 1.2 : 0.5))
      .pointLat('lat').pointLng('lon').pointColor((d: object) => ((d as Site).plume_id ? '#e8743b' : '#8a929b')).pointAltitude(0.004).pointRadius((d: object) => ((d as Site).plume_id ? 0.12 : 0.08))
      .pointLabel((d: object) => { const s = d as Site; return `${s.plume_id ? 'Real EMIT plume site' : 'Simulated site (no EMIT record)'}<br>${s.plume_id ?? 'placed by the simulation'}<br>${fmt(s.lat, 3)}°, ${fmt(s.lon, 3)}°` })
    g.controls().autoRotate = false
    globe.current = g
    const resize = () => { if (host.current) g.width(host.current.clientWidth).height(host.current.clientHeight) }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(host.current)
    return () => { observer.disconnect(); g._destructor(); globe.current = null }
  }, [])

  const realNow = useMemo(() => recs.flatMap(({ sat, rec }) => {
    const p = geodetic(rec, new Date(now))
    return p ? [{ sat, lat: p[0], lng: p[1], alt_km: p[2] }] : []
  }), [recs, now])

  // Real orbit trails are recomputed every 30 s, not every frame.
  const trailKey = Math.floor(now / 30000)
  const realTrails = useMemo<Path[]>(() => recs.map(({ sat, rec }) => {
    const periodMin = 1440 / Number(sat.omm?.MEAN_MOTION ?? 15)
    const points: [number, number, number][] = []
    for (let i = 0; i <= 90; i++) {
      const p = geodetic(rec, new Date(trailKey * 30000 + (i / 90) * periodMin * 60000))
      if (p) points.push(p)
    }
    return { kind: 'real', points }
  }), [recs, trailKey])

  const sim = useMemo(() => {
    if (!mission || !run) return { markers: [] as Marker[], paths: [] as Path[], counts: {} as Record<string, number> }
    const step = mission.track_step_s
    const sources = new Map(mission.sources.map(x => [x.id, x]))
    const markers: Marker[] = []
    const paths: Path[] = []
    for (const f of mission.fleet) {
      const i = simIndex(f, simS, step)
      const [lat, lng, alt] = f.track[i]
      markers.push({ kind: 'sim', id: f.id, label: craftName(f.id), lat, lng, alt_km: alt })
      paths.push({ kind: 'sim', points: f.track.slice(Math.max(0, i - 40), i + 1) })
    }
    const counts: Record<string, number> = {}
    for (const a of run.acquisitions) {
      const t = (utc(a.time_utc) - epochMs) / 1000
      if (t > simS) continue
      counts[a.outcome] = (counts[a.outcome] ?? 0) + 1
      if (simS - t > LOOK_WINDOW_S) continue
      const f = mission.fleet.find(x => x.id === a.spacecraft_id)
      const s = sources.get(a.source_id)
      if (!f || !s) continue
      paths.push({ kind: 'look', outcome: a.outcome, points: [f.track[simIndex(f, t, step)], [s.lat, s.lon, 0]] })
    }
    return { markers, paths, counts }
  }, [mission, run, simS, epochMs])

  useEffect(() => {
    const g = globe.current
    if (!g || !data) return
    const real: Marker[] = realNow.map(r => ({ kind: 'real', id: String(r.sat.norad_id), label: r.sat.name, lat: r.lat, lng: r.lng, alt_km: r.alt_km }))
    g.htmlElementsData([...real, ...sim.markers]).pathsData([...realTrails, ...sim.paths]).pointsData([...data.plume_sources, ...simulatedSites])
    if (follow) {
      const iss = realNow.find(r => r.sat.norad_id === 25544)
      if (iss) g.pointOfView({ lat: iss.lat, lng: iss.lng, altitude: 1.6 }, 900)
    }
  }, [data, realNow, realTrails, sim, follow, simulatedSites])

  const elementAgeH = (s: RealSat) => (s.omm ? (now - utc(String(s.omm.EPOCH))) / 3600000 : NaN)
  const totalLooks = Object.values(sim.counts).reduce((a, b) => a + b, 0)

  const view = (pov: { lat: number; lng: number; altitude: number }) => { setFollow(false); globe.current?.pointOfView(pov, 1500) }
  const retrieved = data?.real_satellites.find(sat => sat.retrieved_at_utc)?.retrieved_at_utc

  return (
    <div className="globe-shell">
      <aside className="globe-side" aria-label="Globe controls and data">
        <header className="globe-head">
          <a className="globe-brand" href="/?view=overview">AETHER</a>
          <a className="globe-console" href="/?view=overview">Open the console</a>
        </header>
        <p className="globe-intro">Methane observation planning over the Permian Basin. Real satellites and real plume sites, with a recorded simulation of four virtual satellites.</p>
        {error && <p className="globe-error" role="alert">Globe data unavailable ({error}). Run <code>python -m scripts.build_globe_data</code> and rebuild the console.</p>}

        <section aria-labelledby="g-real">
          <h2 id="g-real">Real satellites</h2>
          <p className="globe-meta">Positions now, calculated from CelesTrak orbital elements{retrieved ? ` retrieved ${clock(utc(retrieved))}` : ''}. Not live telemetry, and AETHER does not control these spacecraft.</p>
          <table>
            <caption className="sr-only">Real satellite positions calculated for the current time</caption>
            <thead><tr><th scope="col">Satellite</th><th scope="col">Lat</th><th scope="col">Lon</th><th scope="col">Alt</th></tr></thead>
            <tbody>{data?.real_satellites.map(s => { const r = realNow.find(x => x.sat.norad_id === s.norad_id); return (
              <tr key={s.norad_id}><th scope="row">{s.name}<small>{SHORT_ROLE[s.norad_id] ?? s.role}{s.omm ? ` · elements ${fmt(elementAgeH(s), 0)} h old` : ''}</small></th>{r ? <><td>{fmt(r.lat)}°</td><td>{fmt(r.lng)}°</td><td>{fmt(r.alt_km, 0)} km</td></> : <td colSpan={3}>{s.refresh_status}</td>}</tr>) })}</tbody>
          </table>
          <p className="globe-clock">{clock(now)}</p>
        </section>

        <section aria-labelledby="g-sim">
          <h2 id="g-sim">Simulated mission</h2>
          <p className="globe-meta">Satellites, sensor, weather and outcomes are all simulated.{simulatedSites.length > 0 && ` This mission has ${mission?.sources.length} sites: ${(mission?.sources.length ?? 0) - simulatedSites.length} real EMIT locations and ${simulatedSites.length} simulated ones (grey).`}</p>
          <label className="globe-label" htmlFor="globe-mission">Mission</label>
          <select id="globe-mission" value={missionIndex} onChange={e => chooseMission(Number(e.target.value))}>{missions.map((m, i) => <option key={m.label} value={i}>{m.label}</option>)}</select>
          <label className="globe-label" htmlFor="globe-run">Planner</label>
          <select id="globe-run" value={runIndex} onChange={e => setRunIndex(Number(e.target.value))}>{mission?.runs.map((r, i) => <option key={r.run_id} value={i}>{POLICY_NAME[r.policy_id] ?? r.policy_id}</option>)}</select>
          <div className="globe-controls">
            <button onClick={() => setPlaying(p => !p)}>{playing ? 'Pause' : 'Play'}</button>
            <label className="sr-only" htmlFor="globe-speed">Replay speed</label>
            <select id="globe-speed" value={speed} onChange={e => setSpeed(Number(e.target.value))}>{SPEEDS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select>
          </div>
          <label className="sr-only" htmlFor="globe-scrub">Replay time</label>
          <input id="globe-scrub" type="range" min={0} max={horizonS} step={60} value={simS} onChange={e => setSimS(Number(e.target.value))} />
          <p className="globe-clock">{data ? clock(epochMs + simS * 1000) : '—'} <span>hour {fmt(simS / 3600)} of {mission?.horizon_hours ?? '—'}</span></p>
          <ul className="globe-fleet">{mission?.fleet.map(f => <li key={f.id}><i />{craftName(f.id)}<span>{f.id} · {fmt(f.altitude_km, 0)} km</span></li>)}</ul>
          <p className="globe-looks"><strong>{totalLooks}</strong> looks so far</p>
          <ul className="globe-outcomes">{Object.entries(OUTCOME_COLOR).map(([k, c]) => <li key={k}><i style={{ background: c }} />{OUTCOME_LABEL[k]}<span>{sim.counts[k] ?? 0}</span></li>)}</ul>
          <p className="globe-meta">A line joins a satellite to a site for {LOOK_WINDOW_S / 60} minutes after each look.</p>
        </section>

        <section aria-labelledby="g-view">
          <h2 id="g-view">View</h2>
          <div className="globe-views">
            <button onClick={() => view({ lat: 32, lng: -102.8, altitude: 0.9 })}>Permian Basin</button>
            <button onClick={() => view({ lat: 20, lng: -100, altitude: 2.6 })}>Whole Earth</button>
            <button aria-pressed={follow} onClick={() => setFollow(f => !f)}>{follow ? 'Stop following' : 'Follow the ISS'}</button>
          </div>
          <ul className="globe-key">
            <li><i className="real" />Real satellite</li>
            <li><i className="sim" />Virtual satellite</li>
            <li><i className="plume" />Real EMIT plume site (20)</li>
            {simulatedSites.length > 0 && <li><i className="fill" />Simulated site</li>}
          </ul>
        </section>
      </aside>
      <div className="globe-canvas" ref={host} role="img" aria-label="3D Earth showing real satellite positions, the 20 real EMIT plume sites in the Permian Basin, and the recorded simulation of four virtual satellites. The sidebar lists the same information as text." />
    </div>
  )
}
