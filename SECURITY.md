# Security policy

AETHER is a research prototype. It plans observations for **simulated** spacecraft only. It has
no command, uplink or tasking path to any real spacecraft, and contributions that add one are
rejected (`backend/tests/unit/test_security_baseline.py` enforces this in CI).

## Reporting a vulnerability

Please report privately through GitHub: **Security → Report a vulnerability** on this repository.
Do not open a public issue for a security problem.

Include what you found, how to reproduce it, and the impact you expect. We aim to acknowledge
within 5 working days and to agree a fix or mitigation timeline with you. We follow 90-day
coordinated disclosure (Parameter_2 SEC-GOV-001): we ask that you don't publish details until a
fix is released or 90 days have passed, whichever comes first.

## Scope

In scope:
- Leakage of hidden simulated ground truth into planner-side code, logs, API responses or exports
  (this is a scientific-integrity failure, so we treat it as a vulnerability).
- Unsafe parsing of untrusted inputs: GeoJSON, rasters, YAML, OMM/XML, archives.
- Server-side request forgery or fetches outside the outbound allowlist
  (`backend/aether/netpolicy.py`).
- Secrets committed to the repository or written to logs.
- Anything in the API or web app that lets a viewer write data or change a record's provenance class.

Out of scope:
- The accuracy of scientific assumptions. These are documented and labelled in
  `Implementation/Parameter_Register.md`; please open a normal issue to challenge them.
- Findings in third-party data providers (NASA Earthdata, Carbon Mapper, CelesTrak, Copernicus).
  Report those to the provider.

## Handling secrets

- Credentials come from environment variables or `~/.netrc`, never from files in the repository.
  Copy `.env.example` to `.env` (git-ignored) for local use.
- CI runs gitleaks on the full history and fails on findings.
- If you commit a credential by mistake, treat it as leaked: revoke and rotate it first, then
  remove it from history.
