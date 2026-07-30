# Contributing

SourceVahti values statistical correctness over source count. A pull request for
a new source should begin with one narrow, documented indicator family and frozen
upstream responses.

## Development workflow

1. Create a focused branch.
2. Install with `uv sync --all-extras --dev`.
3. Make the smallest source-specific change.
4. Run `uv run ruff check .`, `uv run ruff format --check .`,
   `uv run mypy src`, and `uv run pytest`.
5. Explain any definition, unit, standard-population, provenance, or licensing
   change in the pull request.

Do not commit secrets, health records, personal data, browser session URLs, or
session cookies.

## Adapter acceptance rules

Every adapter must:

- preserve native indicator identifiers and definitions;
- map observations to strict normalised models;
- distinguish crude from age-standardised values;
- name the standard population for every standardised rate;
- preserve source indicator codes, geography, age group, and observation status;
- validate source, geography, sex, unit, and rate categories;
- return an ambiguity error when several valid definitions remain;
- include a direct citation URL, source release version and date, retrieval date,
  and snapshot identifier;
- reject duplicate indicator-year observations before serving data;
- test against a frozen upstream response; and
- document the source’s update and licensing boundary.

A generic scraper is not an acceptable substitute for a source contract.

## Refreshing a source snapshot

Keep the change auditable:

1. Record the exact source selection and retrieval date.
2. Preserve the unmodified source export outside this repository.
3. Compare columns, categories, definitions, units, and missing-value markers with
   the previous response.
4. Update the normalised snapshot and its provenance together.
5. Add or update tests for every new dimension or changed definition.
6. Treat a disappearing or renamed dimension as a breaking upstream change, not
   as an empty result.

Code is licensed under Apache-2.0. Confirm that source data may be redistributed
before adding it; otherwise commit only the smallest legally permitted fixture or
a synthetic contract fixture and document the limitation.
