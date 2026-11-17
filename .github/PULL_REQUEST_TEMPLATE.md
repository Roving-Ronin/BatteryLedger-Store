<!--- Provide a general summary of your changes in the Title above. -->
<!--- Adding or correcting a battery? The easiest way is the "Battery spec submission" issue form, which opens a pull request for you. -->

## Description

<!--- What does this add or change? -->

## Type of change

- [ ] New battery spec (`specs/<brand>/<id>.json`)
- [ ] Correction to an existing spec (`spec_version` increased)
- [ ] New or updated sensor profile (`profiles/<id>.json`, `profile_version` increased if updated)
- [ ] Schema change (`schema/`)
- [ ] Website / scripts / workflows

## Sources

<!--- Links to the manufacturer's datasheet and warranty document for the region. Required for spec changes. -->

## Related issues

<!--- e.g. resolves #123 -->

## Checklist

<!--- Put an `x` in all the boxes that apply. -->

- [ ] Figures come from the manufacturer's documents for the stated regions, linked in `sources`
- [ ] `python scripts/validate.py` passes
- [ ] `python -m pytest -q tests` passes (for script or schema changes)
- [ ] No install-specific details: no serial numbers, station IDs, setup IDs, install dates, costs or energy totals
- [ ] Sensor profile templates use placeholders (`{entry}`, `{prefix}`, `{plant}`, `{station}`, `{serial}`, ...) for anything that differs between installs
