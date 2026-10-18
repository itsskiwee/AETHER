import { useEffect, useMemo, useRef, useState } from 'react'
import Globe, { type GlobeInstance } from 'globe.gl'
import { degreesLat, degreesLong, eciToGeodetic, gstime, json2satrec, propagate, type OMMJsonObject, type SatRec } from 'satellite.js'
import './globe.css'

// Presentation view (UI-10). Two clocks, never mixed:
//  REAL      — published CelesTrak elements propagated (SGP4) to the viewer's current UTC time.
//  SIMULATED — the recorded AETHER demo replay: virtual fleet tracks (Skyfield, precomputed by
//              scripts/build_globe_data.py) and the planner's simulated acquisitions.

type RealSat = { norad_id: number; name: string; role: string; url: string; omm?: OMMJsonObject; retrieved_at_utc?: string; sha256?: string; refresh_status: string }
type Fleet = { id: string; altitude_km: number; inclination_deg: number; track: [number, number, number][] }
type Acq = { time_utc: string; spacecraft_id: string; source_id: string; outcome: string }
type GlobeData = {
  real_satellites: RealSat[]
  plume_sources: { id: string; lat: number; lon: number; plume_id: string | null }[]
  simulation: { scenario_id: string; epoch_utc: string; horizon_hours: number; track_step_s: number; fleet: Fleet[]; runs: { run_id: string; policy_id: string; acquisitions: Acq[] }[] }
}
type Marker = { kind: 'real' | 'sim'; id: string; label: string; lat: number; lng: number; alt_km: number }
type Path = { kind: 'real' | 'sim' | 'look'; points: [number, number, number][]; outcome?: string }

const EARTH_KM = 6371
const LOOK_WINDOW_S = 1200
const SPEEDS = [300, 900, 3600]
const OUTCOME_COLOR: Record<string, string> = { DETECTION: '#ff7a45', VALID_NON_DETECTION: '#7fb2ff', INVALID_ACQUISITION: '#c9a74a', NOT_OBSERVED: '#8792a2' }
const POLICY_NAME: Record<string, string> = { adaptive_eig: 'Adaptive EIG planner', largest_first: 'Largest-first baseline' }

const utc = (iso: string) => Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)
const fmt = (n: number, d = 1) => n.toFixed(d)
const clock = (ms: number) => new Date(ms).toISOString().replace('T', ' ').slice(0, 19) + ' UTC'

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
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(900)
  const [runIndex, setRunIndex] = useState(0)
  const [follow, setFollow] = useState(false)

  useEffect(() => {
    document.title = 'Globe · AETHER'
    fetch('/globe/globe-data.json').then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() }).then(setData).catch(e => setError(String(e)))
  }, [])

  const recs = useMemo(() => (data?.real_satellites ?? []).flatMap(s => s.omm ? [{ sat: s, rec: json2satrec(s.omm) }] : []), [data])
  const run = data?.simulation.runs[runIndex]
  const epochMs = data ? utc(data.simulation.epoch_utc) : 0
  const horizonS = (data?.simulation.horizon_hours ?? 0) * 3600

  useEffect(() => {
    const id = window.setInterval(() => {
      setNow(Date.now())
      if (playing) setSimS(s => (horizonS ? (s + speed * 0.25) % horizonS : 0))
    }, 250)
    return () => window.clearInterval(id)
  }, [playing, speed, horizonS])

  useEffect(() => {
    if (!host.current || globe.current) return
    const g = new Globe(host.current)
      .globeImageUrl('/globe/earth-blue-marble.jpg')
      .bumpImageUrl('/globe/earth-topology.png')
      .backgroundImageUrl('/globe/night-sky.png')
      .atmosphereColor('#7fc8ff')
      .pointOfView({ lat: 28, lng: -100, altitude: 2.4 })
      .htmlTransitionDuration(0)
      .pathTransitionDuration(0)
      .pointsTransitionDuration(0)
      .htmlAltitude((d: object) => (d as Marker).alt_km / EARTH_KM)
      .htmlElement((d: object) => {
        const m = d as Marker
        const el = document.createElement('div')
        el.className = `globe-sat ${m.kind}`
        el.innerHTML = `<i></i><span>${m.label}</span>`
        el.title = `${m.kind === 'real' ? 'REAL (propagated from published elements)' : 'SIMULATED virtual spacecraft'}: ${m.label}`
        return el
      })
      .pathPoints((d: object) => (d as Path).points)
      .pathPointLat((p: [number, number, number]) => p[0])
      .pathPointLng((p: [number, number, number]) => p[1])
      .pathPointAlt((p: [number, number, number]) => p[2] / EARTH_KM)
      .pathColor((d: object) => { const p = d as Path; return p.kind === 'real' ? 'rgba(120,220,255,0.55)' : p.kind === 'sim' ? 'rgba(255,196,92,0.7)' : OUTCOME_COLOR[p.outcome ?? ''] ?? '#fff' })
      .pathStroke((d: object) => ((d as Path).kind === 'look' ? 1.6 : 0.6))
      .pathDashLength((d: object) => ((d as Path).kind === 'sim' ? 0.02 : 1))
      .pathDashGap((d: object) => ((d as Path).kind === 'sim' ? 0.01 : 0))
      .pointLat('lat').pointLng('lon').pointColor(() => '#ff9d3c').pointAltitude(0.004).pointRadius(0.12)
      .pointLabel((d: object) => { const s = d as GlobeData['plume_sources'][number]; return `EMIT plume location (historical, real)<br>${s.plume_id ?? 'unattributed'}<br>${fmt(s.lat, 3)}°, ${fmt(s.lon, 3)}°` })
      .ringColor((d: object) => () => OUTCOME_COLOR[(d as { outcome: string }).outcome] ?? '#fff')
      .ringMaxRadius(1.6).ringPropagationSpeed(1.2).ringRepeatPeriod(700)
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
    if (!data || !run) return { markers: [] as Marker[], paths: [] as Path[], rings: [] as object[], counts: {} as Record<string, number> }
    const step = data.simulation.track_step_s
    const sources = new Map(data.plume_sources.map(s => [s.id, s]))
    const markers: Marker[] = []
    const paths: Path[] = []
    for (const f of data.simulation.fleet) {
      const i = simIndex(f, simS, step)
      const [lat, lng, alt] = f.track[i]
      markers.push({ kind: 'sim', id: f.id, label: `${f.id} · SIM`, lat, lng, alt_km: alt })
      paths.push({ kind: 'sim', points: f.track.slice(Math.max(0, i - 40), i + 1) })
    }
    const rings: object[] = []
    const counts: Record<string, number> = {}
    for (const a of run.acquisitions) {
      const t = (utc(a.time_utc) - epochMs) / 1000
      if (t > simS) continue
      counts[a.outcome] = (counts[a.outcome] ?? 0) + 1
      if (simS - t > LOOK_WINDOW_S) continue
      const f = data.simulation.fleet.find(x => x.id === a.spacecraft_id)
      const s = sources.get(a.source_id)
      if (!f || !s) continue
      paths.push({ kind: 'look', outcome: a.outcome, points: [f.track[simIndex(f, t, step)], [s.lat, s.lon, 0]] })
      rings.push({ lat: s.lat, lng: s.lon, outcome: a.outcome })
    }
    return { markers, paths, rings, counts }
  }, [data, run, simS, epochMs])

  useEffect(() => {
    const g = globe.current
    if (!g || !data) return
    const real: Marker[] = realNow.map(r => ({ kind: 'real', id: String(r.sat.norad_id), label: r.sat.name, lat: r.lat, lng: r.lng, alt_km: r.alt_km }))
    g.htmlElementsData([...real, ...sim.markers]).pathsData([...realTrails, ...sim.paths]).ringsData(sim.rings).pointsData(data.plume_sources)
    if (follow) {
      const iss = realNow.find(r => r.sat.norad_id === 25544)
      if (iss) g.pointOfView({ lat: iss.lat, lng: iss.lng, altitude: 1.6 }, 900)
    }
  }, [data, realNow, realTrails, sim, follow])

  const elementAgeH = (s: RealSat) => (s.omm ? (now - utc(String(s.omm.EPOCH))) / 3600000 : NaN)
  const totalLooks = Object.values(sim.counts).reduce((a, b) => a + b, 0)

  return (
    <div className="globe-shell">
      <div className="globe-canvas" ref={host} role="img" aria-label="3D Earth with real satellite positions propagated from published orbital elements, historical EMIT plume locations in the Permian Basin, and the simulated AETHER fleet replay. The panels list the same information as text." />
      <header className="globe-top">
        <a className="globe-brand" href="/?view=overview"><b>AETHER</b><span>Earth observation planning research</span></a>
        <div className="globe-actions">
          <button onClick={() => { setFollow(false); globe.current?.pointOfView({ lat: 32, lng: -102.8, altitude: 0.9 }, 1500) }}>Focus Permian Basin</button>
          <button aria-pressed={follow} onClick={() => setFollow(f => !f)}>{follow ? 'Following ISS' : 'Follow ISS (EMIT)'}</button>
          <button onClick={() => { setFollow(false); globe.current?.pointOfView({ lat: 20, lng: -100, altitude: 2.6 }, 1500) }}>Whole Earth</button>
          <a className="globe-primary" href="/?view=overview">Open the console →</a>
        </div>
      </header>

      {error && <div className="globe-error" role="alert">Globe data unavailable ({error}). Run <code>python -m scripts.build_globe_data</code> and rebuild the console.</div>}

      <aside className="globe-panel globe-real" aria-label="Real satellites">
        <div className="globe-tag real">REAL · NOW</div>
        <h2>Real Earth-observation satellites</h2>
        <p className="globe-clock">{clock(now)}</p>
        <table>
          <caption className="sr-only">Real satellite positions propagated to the current time</caption>
          <thead><tr><th scope="col">Satellite</th><th scope="col">Lat</th><th scope="col">Lon</th><th scope="col">Alt km</th></tr></thead>
          <tbody>{data?.real_satellites.map(s => { const r = realNow.find(x => x.sat.norad_id === s.norad_id); return (
            <tr key={s.norad_id}><th scope="row" title={s.role}>{s.name}<small>{s.role}</small></th>{r ? <><td>{fmt(r.lat)}°</td><td>{fmt(r.lng)}°</td><td>{fmt(r.alt_km, 0)}</td></> : <td colSpan={3}>{s.refresh_status}</td>}</tr>) })}</tbody>
        </table>
        <p className="globe-note">Positions are SGP4 estimates from CelesTrak GP elements{data?.real_satellites[0]?.retrieved_at_utc ? `, retrieved ${clock(utc(data.real_satellites[0].retrieved_at_utc))}` : ''}. Element age {data ? data.real_satellites.map(s => `${s.name.split(' ')[0]} ${fmt(elementAgeH(s), 0)} h`).join(' · ') : '—'}. <strong>Not live telemetry.</strong> AETHER does not task these spacecraft.</p>
      </aside>

      <aside className="globe-panel globe-sim" aria-label="Simulated mission replay">
        <div className="globe-tag sim">SIMULATED MISSION · REPLAY</div>
        <h2>Virtual AETHER fleet</h2>
        <p className="globe-clock">{data ? clock(epochMs + simS * 1000) : '—'}<small> · T+{fmt(simS / 3600)} h of {data?.simulation.horizon_hours ?? '—'} h</small></p>
        <div className="globe-controls">
          <button onClick={() => setPlaying(p => !p)} aria-label={playing ? 'Pause replay' : 'Play replay'}>{playing ? '❚❚' : '▶'}</button>
          <label className="sr-only" htmlFor="globe-scrub">Replay time</label>
          <input id="globe-scrub" type="range" min={0} max={horizonS} step={60} value={simS} onChange={e => setSimS(Number(e.target.value))} />
          <label className="sr-only" htmlFor="globe-speed">Replay speed</label>
          <select id="globe-speed" value={speed} onChange={e => setSpeed(Number(e.target.value))}>{SPEEDS.map(s => <option key={s} value={s}>{s}×</option>)}</select>
        </div>
        <label className="globe-caption" htmlFor="globe-run">Recorded policy run</label>
        <select id="globe-run" value={runIndex} onChange={e => setRunIndex(Number(e.target.value))}>{data?.simulation.runs.map((r, i) => <option key={r.run_id} value={i}>{POLICY_NAME[r.policy_id] ?? r.policy_id} · seed 1000</option>)}</select>
        <dl className="globe-counts">
          <div><dt>Simulated looks so far</dt><dd>{totalLooks}</dd></div>
          {Object.entries(OUTCOME_COLOR).map(([k, c]) => <div key={k}><dt><i style={{ background: c }} />{k.replaceAll('_', ' ').toLowerCase()}</dt><dd>{sim.counts[k] ?? 0}</dd></div>)}
        </dl>
        <p className="globe-note">{data?.simulation.fleet.length ?? 4} virtual spacecraft (dashed tracks), orbits computed with the project's Skyfield/SGP4 model. Lines show each simulated look for {LOOK_WINDOW_S / 60} min. Spacecraft, sensors, weather and outcomes are simulated.</p>
      </aside>

      <footer className="globe-legend" aria-label="Legend">
        <span><i className="real" />Real satellite (modelled position)</span>
        <span><i className="sim" />Virtual AETHER spacecraft</span>
        <span><i className="plume" />Historical EMIT plume location (20, Permian Basin)</span>
        <span><i className="look" />Simulated look (colour = outcome)</span>
      </footer>
    </div>
  )
}
