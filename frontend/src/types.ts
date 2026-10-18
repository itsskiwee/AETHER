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
  solver_status: string; objective_value: number | null; best_bound: number | null; runtime_s: number | null; validation_ok: boolean | null
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
export interface InputDatasetRef {
  dataset_id: string; manifest_path: string; manifest_sha256: string; normalized_sha256: string
  record_count: number; in_region_count: number; seeded_source_count: number; uniform_fill_count: number
}
export interface RunRecord {
  run_id: string; policy_id: string; scenario_id: string; family: string; seed: number
  model_config_hash: string; truth_config_hash: string; code_version: string; sources: Source[]
  input_dataset?: InputDatasetRef | null
  windows: ObservationWindow[]; plans: Plan[]; validations: { plan_revision: number; ok: boolean; violations: { rule: string; detail: string; option_ids: string[] }[]; checker_version: string }[]
  utilities: CandidateUtility[]; acquisitions: SimulatedAcquisition[]; beliefs: BeliefSnapshot[]; events: RunEvent[]
}

export interface RunIndexItem { run_id: string; policy_id: string; scenario_id: string; family: string; seed: number }
export type BenchmarkRow = Record<string, string>
export interface PairedInterval {
  mean_diff: number; lo: number; hi: number; p_value: number; n: number; resamples: number; level: number
}
export interface BenchmarkComparison {
  family: string; a: string; b: string; metric: string; better_direction: 'lower' | 'higher' | null
  n_pairs: number; n_excluded_undefined: number
  result: PairedInterval | null; note?: string
}
export interface BenchmarkReport {
  protocol_version: number; protocol_sha256: string; protocol_locked: boolean; lock_tag: string | null
  n_seeds: number; total_checker_violations: number; comparisons: BenchmarkComparison[]
  preliminary?: boolean; insufficient_samples?: boolean
  holm_primary?: Record<string, { adjusted_p: number; reject: boolean }>
  success_verdict: { success: boolean; m0_win: boolean; misspecified_wins: string[]; zero_violations: boolean; reasons: string[] } | null
  note: string | null
}
export interface BenchmarkProtocol {
  protocol_version?: number; locked?: boolean; primary_metric: string; primary_comparison: [string, string]
  mandatory_secondary_comparison: [string, string]; success_criterion: string
  families?: string[]; policies?: string[]
}
export interface ProjectSnapshot {
  scenario: {
    id: string; epoch_utc: string; horizon_hours: number; sources_count: number; policies: string[]
    region: { id: string; name: string; bbox_wgs84: [number, number, number, number] }
    weather: { type: string; mean_cloud_fraction: number; wind_median_m_s: number }
  }
  source_model: { placement: string; min_separation_m: number; flux_prior: { family: string; median_kg_h: number; sigma_ln: number; min_kg_h: number; max_kg_h: number }; regimes: { name: string; weight: number; mean_on_hours: number; mean_off_hours: number }[] }
  planner: { lookahead_hours: number; replan_on: string[]; weights: Record<string, number>; utility: string; solver: Record<string, string | number>; max_visits_per_source_per_solve: number }
  scenario_families: string[]
  spacecraft: { id: string; virtual: boolean; profile_version: string; sensor_ids: string[]; orbit: Record<string, string | number>; attitude: Record<string, number>; resources: Record<string, number> }[]
  sensors: { id: string; calibration_status: string; gsd_nadir_m: number; exposure_seconds: number; min_sun_elevation_deg: number; q50_ref_kg_h: number; q90_ref_kg_h: number; ref_wind_m_s: number; false_positive_prob: number; retrieval_success_prob: number; data_bytes_per_scene: number; energy_wh_per_scene: number }[]
  fixture: { manifest: { provider: string; dataset: string; citation_text: string; fixture_status: string; files: { path: string; sha256: string; size_bytes: number }[] } | null; features: { id: string; time_utc: string | null; longitude: number | null; latitude: number | null; rate: string | number | null; geometry_type: string; quality: string }[] }
  pinned_data: { earth_orientation: { filename: string; url: string; byte_size: number; sha256: string; retrieved_at_utc: string } | null; planetary_ephemeris: { filename: string; url: string; byte_size: number; sha256: string; retrieved_at_utc: string } | null }
  benchmark_protocol: { path: string; version: number | null; locked: boolean; families: string[]; policies: string[]; primary_metric: string | null; seed_count_rule: string | null; seed_files: string[] }
}

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
