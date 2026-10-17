# Scenario families

Each file is an **override** applied to `configs/base.yaml` (never `demo.yaml`). Load with
`aether.config.load_scenario(base_path, family_path, seed=...)`. Overrides prefixed `truth:` change only the
hidden simulator. The planner and belief model keep the base values, which is what makes the
scenario *misspecified*. These families are **P0**: without them, an adaptive-EIG "win" is
circular, because the planner and the simulator would share the same model.

| File | Family | What differs between truth and planner model |
|---|---|---|
| `m0_well_specified.yaml` | control | nothing |
| `m1_persistence_wrong.yaml` | regime mix | truth has 1.5x the episodic share (0.40 -> 0.60) and half the persistent share |
| `m2_pod_optimistic.yaml` | sensor | truth Q50/Q90 are 2x the planner's (sensor worse than believed) |
| `m3_forecast_overconfident.yaml` | weather | truth forecast error is 2x the planner's assumed sigma |
| `m4_false_positives.yaml` | sensor | truth FP rate 0.05 vs model 0.02 |
| `r1_resource_scarce.yaml` | resources | storage 1.5 GB (4 scenes/orbit at 306 MB), slew 0.75 deg/s (both truth and model) |
| `h168_long_horizon.yaml` | horizon | 168 h horizon, 60 sources |
