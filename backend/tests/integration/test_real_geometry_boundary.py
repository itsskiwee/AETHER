"""Real SGP4 boundary regression, with the independent checker left strict."""

from datetime import timedelta

from aether.config import load_scenario
from aether.contracts import Plan, Selection
from aether.orbit import generate_windows
from aether.planning.checker import check_schedule
from aether.simulation.runner import generate_sources


def test_seed1000_pointing_boundary_options_pass_independent_physics(repo_root):
    cfg = load_scenario(repo_root / "configs/demo.yaml", seed=1000).model
    source = generate_sources(cfg, 1000)[0]
    # The original actual failure occurred at source-001's 17:12 UTC pass.
    start = cfg.simulation_epoch_utc + timedelta(hours=17, minutes=10)
    windows = generate_windows(cfg, [source], start, start + timedelta(minutes=5))
    checked = 0
    for window in windows:
        for option in window.options:
            assert (
                option.off_nadir_deg
                <= cfg.spacecraft[window.spacecraft_id].attitude.max_off_nadir_deg
            )
            plan = Plan(
                run_id="real-boundary-regression",
                policy_id="largest_first",
                revision=0,
                created_at_sim_utc=start,
                cause="test",
                objective_weights={},
                candidate_window_ids=(window.id,),
                selections=(Selection(window_id=window.id, option_id=option.option_id),),
                solver_status="HEURISTIC",
                objective_value=None,
                best_bound=None,
            )
            result = check_schedule(
                plan, [window], [source], cfg.spacecraft, cfg.sensors[window.sensor_id], cfg
            )
            assert result.ok, result.violations
            checked += 1
    assert checked > 0
