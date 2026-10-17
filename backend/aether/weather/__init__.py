"""Lane L6 (simulation). Weather: synthetic scenario fields and, at P1, ERA5 replay.

Interface (tasks SIM-01, SIM-02):

    class WeatherModel(Protocol):
        def cloud_truth(self, source_id: str, t_utc) -> float          # restricted: simulator only
        def wind_truth(self, source_id: str, t_utc) -> float           # restricted: simulator only
        def cloud_forecast(self, source_id: str, t_utc, issued_at_utc) -> float  # planner-visible
        def wind_forecast(self, source_id: str, t_utc, issued_at_utc) -> float   # planner-visible
        def latest_issue_time(self, now_utc) -> datetime

    build_synthetic_weather(cfg_truth: ScenarioConfig, sources, *, model_cfg: ScenarioConfig)
        -> WeatherModel
        Latent Gaussian field on sources: exponential spatial kernel (corr length), AR(1) in time
        (corr time), logistic transform calibrated so the mean cloud fraction matches. Forecast =
        truth logit + N(0, sigma_base + sigma_per_lead * lead_h), issued every issue_interval_hours.
        injected_events overwrite BOTH the truth and the forecast for the target source.
        All randomness comes from aether.rng namespace "weather".

Synthetic weather is labelled synthetic everywhere. It is never called a forecast product.
"""
