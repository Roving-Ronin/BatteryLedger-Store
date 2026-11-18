# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

The BatteryLedger Store: community battery specs (`specs/<brand>/<id>.json`) and sensor profiles
(`profiles/<id>.json`) used by the BatteryLedger Home Assistant integration
(`Roving-Ronin/BatteryLedger`). The Pages workflow publishes `index.json` and the browse site
(`site/index.html`) to `https://roving-ronin.github.io/BatteryLedger-Store/`.

## Commands

```bash
pip install -r scripts/requirements.txt pytest
python scripts/validate.py          # every spec and profile
python scripts/build_index.py _site # what Pages publishes
python -m pytest -q tests
pip install ruff zizmor && ruff check . && zizmor .   # lint + workflow security audit
```

CI: Validate (Ruff, specs and profiles, tests, index build) on pushes to main and PRs; Security (zizmor,
CodeQL) on pushes, PRs and weekly.

## Workflow security
- Never put `${{ ... }}` expressions inside `run:` scripts: pass them through `env:` and use `"$VAR"`.
  The issue body is untrusted: `submission.yml` passes it via `ISSUE_BODY`; keep it that way.
- `permissions: {}` at workflow level where jobs differ, and grant each job only what it needs.
- `actions/checkout` with `persist-credentials: false`, unless the job pushes (`submission.yml`, marked
  `# zizmor: ignore[artipacked]`).
- Actions are pinned by tag (`.github/zizmor.yml`), kept current by Dependabot.

## Rules

- **`index.json` is an API.** The integration reads it (`index_format` 1). Adding optional fields is
  fine; renaming or removing fields, or changing their meaning, needs a new `index_format` and a matching
  BatteryLedger release first.
- **Spec changes:** any change to figures raises `spec_version` (installs are offered the revision
  through Repairs). Setting `verified` or editing notes or sources doesn't need a bump.
- `verified: true` only after checking the figures against the manufacturer documents in `sources`.
- **No install-specific data**, ever: no serial numbers, station IDs, config entry IDs, install dates,
  costs or energy totals. Sensor profile templates use placeholders for anything that differs between
  installs; module templates must contain `{serial}`.
- Sensor profiles: `unique_id` templates do the matching; `default_entity_ids` are only for people reading the
  Store site. Take both from the integration's source, not guesses, and keep install-specific parts as
  placeholders (`<serial>`).
- Field naming: `series` is shown to users as **Model** (product line, e.g. SigenStor, Neo); `model` is
  shown as **Battery module** (e.g. SigenStor BAT 8.0).
- Specs sort brand → model line → battery module, numbers largest first (`build_index.natural_key`).
- Sensor profiles list their brands explicitly (no wildcard). An integration for several brands (Energy
  Manager) lists each one and must be updated when a brand is added. On the site, Sigenergy comes first,
  then the other brands alphabetically; profiles offered for every brand come last.
- Submissions: `issue_to_spec.py` parses the issue form by **label text** and the integration's JSON
  block after `<!-- batteryledger-spec -->`. Changing a form label means changing the parser constant
  and its test. The issue body is untrusted input: pass it via environment variables, never interpolate
  it into a script.
- Issue templates use GitHub's default labels (`bug`, `enhancement`, `question`), plus
  `spec-submission` / `needs-changes` for the submission pipeline.
- Never commit or push without the maintainer's explicit approval.
