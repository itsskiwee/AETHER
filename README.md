# AETHER
A research prototype that plans where **simulated**, taskable Earth-observation satellites should look next to collect the most useful evidence on major methane emission sources.

It uses real NASA EMIT plume records for context and runs entirely on virtual spacecraft. It does not task real satellites, and it does not verify emission reductions.

- Requirements: `Implementation/AETHER_Product_Requirements_Document.md` (amended by `Implementation/PRD_Amendments.md`)
- Parameters: `Implementation/Parameter_Register.md`
- Team plan and agent rules: `Implementation/Work_Plan.md`, `AGENTS.md`

```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
pytest
python -m aether.cli validate --config ../configs/base.yaml
```
