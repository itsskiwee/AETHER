@AGENTS.md

## Claude lanes

Claude agents run lanes L1 (Integrator), L2 (Science model) and L3 (Evaluation & integrity). See `Implementation/Work_Plan.md`.

- **L1** is the only lane that merges to `main` or edits `backend/aether/contracts/`, `config.py`, `rng.py`, `cli.py`, `simulation/runner.py` or `configs/`. Review contract PRs from other lanes quickly. They are blocked until you answer.
- **L2 and L3** do the scientific judgment calls. When a parameter or method choice is uncertain, write the options and your recommendation in the relevant model card or `docs/validation-report.md`. Don't silently pick one.
- **L3** reviews wording on every user-facing surface against PRD §22.3 and files issues; it does not edit other lanes' files.
