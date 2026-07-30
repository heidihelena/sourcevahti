# SourceVahti

Reliable AI access to public health, government, and research data.

SourceVahti is a small Model Context Protocol (MCP) server that makes statistical
definitions explicit before returning a number. Version 0.2 covers the Finnish
Cancer Registry and NORDCAN, and exposes three read-only tools over local stdio:

- `search_indicators`
- `get_observations`
- `get_latest_observation`

The product is the ambiguity guard. “Mortality rate” can mean a crude rate or one
of several age-standardised rates. SourceVahti returns a model-visible error with
the valid definitions instead of silently choosing one.

## Current scope

This release contains two frozen, source-specific snapshots.

The Finnish Cancer Registry snapshot contains its 2024 female lung and tracheal
cancer mortality export. The public statistics application exposes three rates
for the same population and year:

| Rate definition | Standard population | 2024 value |
| --- | --- | ---: |
| Crude | None | 29.96 |
| Age-standardised, world | World standard population (1966) | 9.04 |
| Age-standardised, Finland | Finland population 2014 | 23.28 |

All values are rates per 100,000 person-years. The snapshot was retrieved on
2026-07-30 from the [Finnish Cancer Registry statistics application](https://cancerregistry.fi/statistics/cancer-statistics/),
whose latest official year was 2024 and whose release date was 2026-04-24.

This is deliberately a deterministic proof of concept, not a claim of live
coverage. The registry publishes downloads through a session-based interactive
application rather than a documented stable data API. See
[Data refresh](#data-refresh) for the trust boundary.

The NORDCAN snapshot contains version 9.6 female lung-cancer mortality tables for
2023–2024. It covers Denmark, Finland, Greenland, Iceland, Norway, Sweden, the
Faroe Islands’ latest 2023 observation, and two published Nordic aggregates. Each
geography preserves five distinct rates:

| Rate definition | Standard population |
| --- | --- |
| Crude | None |
| Age-standardised, World | World standard population |
| Age-standardised, Nordic | NORDCAN population in 2000 |
| Age-standardised, European 1976 | European standard population 1976 |
| Age-standardised, European 2013 | European standard population 2013 |

NORDCAN version 9.6 was released on 2026-06-30 and contains data through 2024
where available. See the [NORDCAN database](https://nordcan.iarc.fr/en/database)
and [statistical definitions](https://nordcan.iarc.fr/en/additional-information).

## Install and run

Requirements: Python 3.11 or newer and
[uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/heidihelena/sourcevahti.git
cd sourcevahti
uv sync --all-extras --dev
uv run sourcevahti
```

`sourcevahti` starts a local stdio server. It should stay silent and wait for an
MCP host. Do not send logs to stdout because stdout carries the protocol.

For MCP Inspector:

```bash
uv run mcp dev src/sourcevahti/server.py:mcp
```

Generic MCP host configuration:

```json
{
  "mcpServers": {
    "sourcevahti": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/sourcevahti",
        "run",
        "sourcevahti"
      ]
    }
  }
}
```

Use absolute paths in host configuration. A host may start the server from a
different working directory.

## Acceptance example

First search without selecting a definition:

```json
{
  "query": "female lung cancer mortality rate",
  "source": "finnish_cancer_registry",
  "sex": "female",
  "unit": "per_100_000_person_years"
}
```

`search_indicators` returns three candidate indicators. Then call
`get_latest_observation` with the required epidemiological definition:

```json
{
  "query": "female lung cancer mortality rate",
  "source": "finnish_cancer_registry",
  "sex": "female",
  "rate_type": "age_standardised_finland_2014",
  "unit": "per_100_000_person_years"
}
```

The structured observation includes:

```json
{
  "source_indicator_code": "site=21L;value_type=mort.rate_finland_2014;sex=1L",
  "cancer_site": "Lung, trachea",
  "cancer_definition": "Malignant neoplasms of trachea and bronchus/lung (ICD-10 C33-C34)",
  "age_group": "All ages",
  "year": 2024,
  "value": 23.28,
  "unit": "per_100_000_person_years",
  "sex": "female",
  "geography": "Finland",
  "rate_type": "age_standardised_finland_2014",
  "standard_population": "Finland population 2014",
  "observation_status": "observed",
  "provenance": {
    "source_id": "finnish_cancer_registry",
    "source_name": "Finnish Cancer Registry",
    "source_release_version": "2024 statistical release",
    "source_release_date": "2026-04-24",
    "retrieval_date": "2026-07-30",
    "citation_url": "https://cancerregistry.fi/statistics/cancer-statistics/..."
  }
}
```

Requesting only `mortality rate` produces a tool error whose JSON payload contains
`code: "ambiguous_indicator"` and candidate IDs for the crude, world-standardised,
and Finland-2014-standardised series. The caller must retry with `indicator_id` or
`rate_type`.

For a NORDCAN result:

```json
{
  "query": "female Denmark lung cancer mortality, Nordic 2000",
  "source": "nordcan",
  "geography": "Denmark"
}
```

This returns Denmark’s 2024 Nordic-2000-standardised rate, 43.0 per 100,000
person-years. A query for Finland’s crude rate without `source` remains ambiguous
because both sources publish valid but independently defined values.

## Tool contracts

### `search_indicators`

Lexically searches indicator names, definitions, source codes, cancer codes,
source, geography, sex, unit, rate type, and standard population. Recognised
source, geography, sex, unit, and rate-definition terms in the query are enforced
as constraints. Explicit filters are validated and cannot contradict those terms.
It never collapses epidemiologically distinct series.

### `get_observations`

Returns one resolved series, optionally bounded by inclusive `start_year` and
`end_year`. Supply an exact `indicator_id`, or a query plus sufficient dimensions
to leave exactly one candidate.

### `get_latest_observation`

Returns the highest-year observation in one resolved series. The result contains
the source indicator code, cancer definition, age group, rate type, standard
population, observation status, value, unit, citation URL, source release version,
source release date, and retrieval date.

Supported canonical values:

- `source`: `finnish_cancer_registry`, `nordcan`
- `geography`: a geography published in the frozen snapshots
- `sex`: `female`, `male`, `all`
- `unit`: `per_100_000_person_years` (`count` is reserved for future count
  indicators and matches no series in this snapshot)
- `rate_type`: `crude`, `age_standardised_world`,
  `age_standardised_world_1966`, `age_standardised_finland_2014`,
  `age_standardised_nordic_2000`, `age_standardised_europe_1976`,
  `age_standardised_europe_2013`

The adapter accepts a small set of documented human-friendly aliases but rejects
unknown categories and dimensional mismatches.

## Architecture

```text
MCP typed tools
    └── SourceCatalog
          ├── cross-source query resolution and ambiguity checks
          ├── FinnishCancerRegistryAdapter
          │     └── frozen registry export
          └── NordcanAdapter
                └── frozen NORDCAN 9.6 table output
                      └── normalised Pydantic models + provenance
```

`src/sourcevahti/models.py` is the public schema. The MCP SDK derives JSON input
and output schemas from the typed functions and Pydantic return models. Domain
exceptions become MCP tool errors so a model can correct its request.

The adapter boundary is intentionally source-specific. Shared code handles
normalised search, validation, duplicate detection, and ambiguity, while each
adapter parses its own native response shape. Future WHO and Eurostat adapters
should follow the same boundary rather than reuse a generic scraper.

## Data refresh

The bundled source files are:

- `src/sourcevahti/data/finnish_cancer_registry_2024.csv`
- `src/sourcevahti/data/nordcan_lung_mortality_9_6.csv`

To refresh the Finnish snapshot:

1. Open the registry statistics application in English.
2. Select deaths due to cancer, female, whole country, lung/trachea (C33-C34),
   and latest year.
3. Export each of the crude, world-standardised, and Finland-2014-standardised
   rate definitions.
4. Preserve the raw exported files outside the repository for audit.
5. Update the normalised snapshot, exact citation URLs, source release date,
   retrieval date, and snapshot ID.
6. Run the full test suite and verify that the ambiguity test still returns every
   available rate definition.

To refresh NORDCAN:

1. Open the NORDCAN incidence/mortality tables.
2. Select mortality, females, lung (entity 160), all ages, and each available
   reporting year.
3. Preserve the World, Nordic 2000, European 1976, European 2013, and crude
   columns without selecting one implicitly.
4. Record the displayed data version, exact table permalink, retrieval date, and
   recommended citation.
5. Update the wide source snapshot and run the adapter, catalog, and MCP tests.

The NORDCAN web application offers CSV/XLSX table export but does not document a
stable public data API. The adapter therefore remains snapshot-backed.

Review source metadata and terms before redistributing new data. The repository’s
Apache-2.0 licence covers SourceVahti code. Source data remains governed by its
publisher’s terms; each snapshot carries a separate `license_note` in every
provenance object.

## Deployment and DNS

The planned public endpoints are `sourcevahti.vahtian.com` for the hosted HTTP/MCP
service and `trends.ntog.org` for the NTOG Shiny application. DNS records should
only be created after each deployment has supplied its canonical target hostname.

See [docs/DNS.md](docs/DNS.md) for the Cloudflare records, provider-side custom
domain steps, verification commands, and an explanation of why the existing NTOG
`CNAME` file must remain unchanged.

## Development

```bash
uv sync --all-extras --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

Tests use the frozen source response and the official SDK’s in-memory MCP client.
CI runs linting, type checking, tests, and package builds on supported Python
versions.

See [CONTRIBUTING.md](CONTRIBUTING.md) for source-update rules and
[SECURITY.md](SECURITY.md) for responsible disclosure.

## Licence

SourceVahti code is licensed under the
[Apache License, Version 2.0](LICENSE). No medical advice is provided. Always cite
the source and preserve the returned epidemiological definition when reporting a
value.
