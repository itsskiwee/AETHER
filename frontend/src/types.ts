// Hand-matched read-only projection of backend/aether/contracts/models.py.
export type ProvenanceClass = 'REAL_OBSERVATION' | 'MODEL_INFERENCE' | 'SIMULATED_OBSERVATION' | 'SIMULATED_GROUND_TRUTH'
export type ObservationOutcome = 'DETECTION' | 'VALID_NON_DETECTION' | 'INVALID_ACQUISITION' | 'NOT_OBSERVED'

export interface Source { id: string; lon: number; lat: number; seeded_from_plume_id: string | null; attribution_status: string }
export interface AcquisitionOption { option_id: string; window_id: string; start_utc: string; end_utc: string; off_nadir_deg: number; sun_elevation_deg: number; los_unit_ecef: [number, number, number] }
export interface ObservationWindow {
  id: string; spacecraft_id: string; sensor_id: string; source_id: string; start_utc: string; end_utc: string
  pass_id: string; orbit_number: number; feasible: boolean; rejection_reasons: string[]; min_off_nadir_deg: number
  options: AcquisitionOption[]; duration_s: number; energy_wh: number; data_bytes: number
}
export interface CandidateUtility {
  window_id: string; plan_revision: number; expected_info_gain_bits: number; decision_relevance: number
  latency_s: number; resource_cost: number; p_valid_forecast: number; utility: number; integer_utility: number
}
export interface Plan {
  run_id: string; policy_id: string; revision: number; created_at_sim_utc: string; cause: string
  objective_weights: Record<string, number>; candidate_window_ids: string[]
  selections: Selection[]; selected_window_ids: string[]
  solver_status: string; objective_value: number | null; best_bound: number | null; runtime_s: number; validation_ok: boolean | null
}
export interface Selection { window_id: string; option_id: string }
export interface BeliefSnapshot {
  source_id: string; state_time_utc: string; provenance_class: 'MODEL_INFERENCE'; p_active: number
  regime_probs: Record<string, number>; flux_median_kg_h: number; flux_ci90_kg_h: [number, number]
  entropy_bits: number; model_version: string; evidence_ids: string[]; received_new_evidence: boolean
}
export interface SimulatedAcquisition {
  id: string; option_id: string; window_id: string; source_id: string; spacecraft_id: string; sensor_id: string
  time_utc: string; provenance_class: 'SIMULATED_OBSERVATION'; outcome: ObservationOutcome
  measured_flux_kg_h: number | null; off_nadir_deg: number; wind_estimate_m_s: number
  scene_cloud_fraction: number; rng_key: string
}
export interface RunEvent {
  event_id: string; run_id: string; sequence_number: number; event_time_sim_utc: string
  event_type: string; actor: string; payload: Record<string, unknown>; payload_sha256: string
  config_hash: string; model_version: string
}
export interface RunRecord {
  run_id: string; policy_id: string; scenario_id: string; family: string; seed: number
  model_config_hash: string; truth_config_hash: string; code_version: string; sources: Source[]
  windows: ObservationWindow[]; plans: Plan[]; validations: { plan_revision: number; ok: boolean; violations: { rule: string; detail: string; option_ids: string[] }[]; checker_version: string }[]
  utilities: CandidateUtility[]; acquisitions: SimulatedAcquisition[]; beliefs: BeliefSnapshot[]; events: RunEvent[]
}

export interface RunIndexItem { run_id: string; policy_id: string; scenario_id: string; family: string; seed: number }
export interface BenchmarkRow extends Record<string, string> {}

export function parseRun(value: unknown): RunRecord {
  if (!value || typeof value !== 'object') throw new Error('Run response must be an object')
  const run = value as Partial<RunRecord>
  for (const key of ['run_id', 'policy_id', 'scenario_id', 'family', 'model_config_hash', 'truth_config_hash', 'code_version']) {
    if (typeof run[key as keyof RunRecord] !== 'string') throw new Error(`Run artifact is missing ${key}`)
  }
  for (const key of ['sources', 'windows', 'plans', 'validations', 'utilities', 'acquisitions', 'beliefs', 'events']) {
    if (!Array.isArray(run[key as keyof RunRecord])) throw new Error(`Run artifact field ${key} must be an array`)
  }
  return run as RunRecord
}
