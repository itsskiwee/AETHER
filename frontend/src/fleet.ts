// Display names for the four virtual spacecraft. The IDs (vsat_a..vsat_d) stay the source of truth:
// they are in configs/spacecraft/*.yaml, every run record and every export hash, so they are never
// renamed. Only the interface shows the names.
export const CRAFT_NAMES: Record<string, string> = {
  vsat_a: 'Pip',
  vsat_b: 'Wren',
  vsat_c: 'Juniper',
  vsat_d: 'Mochi',
}

export const craftName = (id: string) => CRAFT_NAMES[id] ?? id
