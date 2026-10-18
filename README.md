# AETHER
A research prototype that plans where **simulated**, taskable Earth-observation satellites should look next to collect the most useful evidence on major methane emission sources.

**SIMULATED MISSION · offline replay.** The offline demo uses seeded synthetic source
hypotheses and virtual spacecraft. The EMIT-shaped ingestion fixture is synthetic;
no verified real plume records are required. It does not task real satellites or
verify emission reductions.

Set up once, then generate and open the complete demonstration from the repository root:

```bash
python -m venv backend/.venv
backend/.venv/bin/pip install -e './backend[dev,geo,api]'
npm --prefix frontend ci
bash scripts/demo.sh
bash scripts/serve-demo.sh
```

Open http://127.0.0.1:4173. See [setup and presentation walkthrough](docs/demo-console.md)
for exact evidence, offline packaging, and limitations. Generation writes actual
simulator records, checks independent feasibility and byte-identical replay, exports
ZIPs, and runs a preliminary development-seed comparison using the base config.
Generated output stays in ignored `runs/demo/`.

- Requirements: `Implementation/AETHER_Product_Requirements_Document.md` (amended by `Implementation/PRD_Amendments.md`)
- Parameters: `Implementation/Parameter_Register.md`
- Team plan and agent rules: `Implementation/Work_Plan.md`, `AGENTS.md`

```bash
cd backend && . .venv/bin/activate
pytest
python -m aether.cli validate --config ../configs/base.yaml
```
