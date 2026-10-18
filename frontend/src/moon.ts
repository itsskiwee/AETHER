import { GeoMoon, HOUR2RAD, KM_PER_AU, RAD2DEG, RotateVector, Rotation_EQJ_EQD, SiderealTime } from 'astronomy-engine'
import { Mesh, MeshStandardMaterial, PerspectiveCamera, SphereGeometry, SRGBColorSpace, TextureLoader, Vector3 } from 'three'
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js'
import type { GlobeInstance } from 'globe.gl'

// PR-LUNAR01: presentation context only. Never an input to the mission or planner.
export const MOON_RADIUS_KM = 1737.4
export const EARTH_RADIUS_KM = 6371
export type LunarFocus = 'earth' | 'system' | 'moon'

// Hold the Earth's viewing frame at the start of the lunar preview. Advancing the
// Moon does not advance Earth-fixed satellite positions or the recorded mission.
export function lunarPosition(at: Date, frameAt: Date): { lat_deg: number; lon_deg: number; distance_km: number } {
  const vector = RotateVector(Rotation_EQJ_EQD(frameAt), GeoMoon(at))
  return {
    lat_deg: Math.atan2(vector.z, Math.hypot(vector.x, vector.y)) * RAD2DEG,
    lon_deg: (Math.atan2(vector.y, vector.x) - SiderealTime(frameAt) * HOUR2RAD) * RAD2DEG,
    distance_km: Math.hypot(vector.x, vector.y, vector.z) * KM_PER_AU,
  }
}

export function addMoon(globe: GlobeInstance, frameAt: Date) {
  const earthRadius = globe.getGlobeRadius()
  const radius = earthRadius * MOON_RADIUS_KM / EARTH_RADIUS_KM
  const geometry = new SphereGeometry(radius, 64, 32)
  const texture = new TextureLoader().load('/globe/moon-color.jpg')
  texture.colorSpace = SRGBColorSpace
  const material = new MeshStandardMaterial({ map: texture, roughness: 1 })
  const moon = new Mesh(geometry, material)
  moon.name = 'Moon'
  globe.scene().add(moon)
  function label(text: string) {
    const element = document.createElement('div')
    element.className = 'globe-body-label'
    element.textContent = text
    const object = new CSS2DObject(element)
    object.visible = false
    globe.scene().add(object)
    return object
  }
  const earthLabel = label('Earth')
  const moonLabel = label('Moon')

  function positionAt(at: Date) {
    const p = lunarPosition(at, frameAt)
    return new Vector3().copy(globe.getCoords(p.lat_deg, p.lon_deg, p.distance_km / EARTH_RADIUS_KM - 1))
  }

  function focus(mode: LunarFocus) {
    earthLabel.visible = moonLabel.visible = mode === 'system'
    if (mode === 'earth') return
    const camera = globe.camera() as PerspectiveCamera
    const controls = globe.controls()
    if (mode === 'moon') {
      // Keep Earth as the control target: globe.gl owns that target. Position the
      // camera just beyond the Moon, looking back along the Earth–Moon line.
      camera.position.copy(moon.position).addScaledVector(moon.position.clone().normalize(), radius * 4)
    } else {
      const next = positionAt(new Date(frameAt.getTime() + 86400000))
      const normal = new Vector3().crossVectors(positionAt(frameAt), next).normalize()
      const halfFov = Math.atan(Math.tan(camera.fov * Math.PI / 360) * Math.min(1, camera.aspect))
      const distance = (moon.position.length() + earthRadius) / Math.sin(halfFov) * 1.1
      controls.maxDistance = Math.max(controls.maxDistance, distance * 2)
      camera.position.copy(normal.multiplyScalar(distance))
    }
    camera.lookAt(0, 0, 0)
    controls.update()
  }

  function update(at: Date, mode: LunarFocus) {
    moon.position.copy(positionAt(at))
    moonLabel.position.copy(moon.position)
    earthLabel.visible = moonLabel.visible = mode === 'system'
    // Synchronous rotation: the same texture hemisphere faces Earth. This is a
    // visual approximation of tidal locking, without a lunar libration model.
    moon.lookAt(0, 0, 0)
    if (mode === 'moon') focus(mode)
    return lunarPosition(at, frameAt).distance_km
  }

  update(frameAt, 'earth')
  return {
    focus, update,
    dispose() {
      globe.scene().remove(moon)
      globe.scene().remove(earthLabel, moonLabel)
      earthLabel.element.remove()
      moonLabel.element.remove()
      geometry.dispose()
      material.dispose()
      texture.dispose()
    },
  }
}
