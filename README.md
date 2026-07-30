# SourceVahti

Reliable AI access to public health, government and research data.

SourceVahti is a Model Context Protocol (MCP) server that makes statistical
definitions explicit before returning a number. Version 0.3 exposes four
source-specific adapters and three read-only tools over local stdio:

- `search_indicators`
- `get_observations`
- `get_latest_observation`

The product is the ambiguity guard. “Mortality rate” may mean a crude rate or
one of several age-standardised rates, and two publishers may produce valid but
non-interchangeable values. SourceVahti returns a structured
`ambiguous_indicator` error with the valid candidates instead of silently
choosing one.

## Current sources

| Source | Narrow supported scope | Role |
| --- | --- | --- |
| Finnish Cancer Registry | Female Finnish lung/tracheal cancer mortality, 2024 | Exact registry acceptance case |
| NORDCAN 9.6 | Nordic lung-cancer mortality by country and rate definition, 2023–2024 | Nordic cancer outcomes |
| WHO Global Health Observatory | Current tobacco-use prevalence, age 15+, Nordic countries, 2000–2025 | Modelled risk-factor context |
| Eurostat | Lung-cancer mortality, C33-C34, Nordic countries, 2011–2023 | Independent mortality source |

All bundled data are frozen, reviewed snapshots. The MCP server makes no
upstream requests during a tool call.

### Finnish Cancer Registry

The snapshot contains the 2024 female lung and tracheal cancer mortality export.
The public application exposes three rates for the same population and year:

| Rate definition | Standard population | Value per 100,000 person-years |
| --- | --- | ---: |
| Crude | None | 29.96 |
| Age-standardised, world | World standard population (1966) | 9.04 |
| Age-standardised, Finland | Finland population 2014 | 23.28 |

It was retrieved on 2026-07-30 from the
[Finnish Cancer Registry statistics application](https://cancerregistry.fi/statistics/cancer-statistics/).
The latest official year was 2024 and the release date was 2026-04-24.

### NORDCAN

The NORDCAN snapshot contains version 9.6 female lung-cancer mortality tables
for 2023–2024. It covers Denmark, Finland, Greenland, Iceland, Norway, Sweden,
the Faroe Islands' latest 2023 observation and two Nordic aggregates. Every
geography retains crude, World, Nordic 2000, European 1976 and European 2013
rate definitions. NORDCAN 9.6 was released on 2026-06-30. See the
[database](https://nordcan.iarc.fr/en/database) and
[statistical definitions](https://nordcan.iarc.fr/en/additional-information).

### WHO GHO

The WHO adapter contains 150 observations: female, male and both-sex modelled
estimates for five Nordic countries at ten published years from 2000 through
2025. The indicator is current tobacco-use prevalence among people aged 15
years and over, standardised to the WHO standard population. Each value retains
its 95% uncertainty bounds, modelled/projected status and source note.

This is contextual risk-factor data, not a cancer outcome or causal estimate.
See the [WHO indicator metadata](https://www.who.int/data/gho/indicator-metadata-registry/imr-details/prevalence-of-current-tobacco-use-among-persons-aged-15-years-and-older-age-standardized).

### Eurostat

The Eurostat adapter contains 195 annual observations for Denmark, Finland,
Iceland, Norway and Sweden: female, male and both-sex rates from 2011 through
2023. It selects dataset `HLTH_CD_ASDR2`, unit `RT`, all ages and cause
`C33_C34`. Rates are directly standardised to the European Standard Population
2013 and retain Eurostat status flags.

See the [Eurostat causes-of-death metadata](https://ec.europa.eu/eurostat/cache/metadata/en/hlth_cdeath_sims.htm).
Eurostat and NORDCAN are separate publishers; matching definitions make a
source comparison possible but do not make their observations identical.

## Install and run

Requirements: Python 3.11 or newer and
[uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/heidihelena/sourcevahti.git
cd sourcevahti
uv sync --locked --all-extras --dev
uv run sourcevahti
```

`sourcevahti` starts a local stdio server. It should stay silent and wait for an
MCP host because stdout carries the protocol.

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

Use an absolute path because an MCP host may start the server from a different
working directory.

## Examples

First search without selecting a Finnish rate definition:

```json
{
  "query": "female lung cancer mortality rate",
  "source": "finnish_cancer_registry",
  "sex": "female",
  "unit": "per_100_000_person_years"
}
```

`search_indicators` returns three candidates. Retry
`get_latest_observation` with the required definition:

```json
{
  "query": "female lung cancer mortality rate",
  "source": "finnish_cancer_registry",
  "sex": "female",
  "rate_type": "age_standardised_finland_2014",
  "unit": "per_100_000_person_years"
}
```

The result includes the native source code, cancer definition, year, value,
unit, sex, geography, rate type, standard population, observation status,
citation URL, source version and release date, retrieval date and snapshot ID.
The acceptance value is 23.28 per 100,000 person-years in 2024.

WHO risk-factor context:

```json
{
  "query": "female Finland current tobacco use prevalence",
  "source": "who_gho",
  "sex": "female",
  "geography": "Finland",
  "unit": "percent"
}
```

This returns the 2025 projected estimate, 17.1%, with a 14.0–20.2% uncertainty
interval and the WHO indicator definition.

Eurostat source comparison:

```json
{
  "query": "female Finland lung cancer mortality European 2013",
  "source": "eurostat",
  "sex": "female",
  "geography": "Finland"
}
```

If `source` is omitted, a European-2013-standardised Nordic lung-cancer
mortality query may correctly remain ambiguous between NORDCAN and Eurostat.

## Tool contracts

### `search_indicators`

Lexically searches indicator names, descriptions, definitions, native codes,
health topic, cancer codes, source, geography, sex, unit, rate type and
standard population. Recognised dimensional terms in the query become
constraints. Explicit filters are validated and cannot contradict those terms.
Epidemiologically distinct series are never collapsed.

### `get_observations`

Returns one resolved series, optionally bounded by inclusive `start_year` and
`end_year`. Supply an exact `indicator_id`, or a query plus sufficient
dimensions to leave exactly one candidate.

### `get_latest_observation`

Returns the highest-year observation in one resolved series. In addition to the
shared provenance fields, an observation may include uncertainty bounds and a
publisher note.

Supported canonical values:

- `source`: `finnish_cancer_registry`, `nordcan`, `who_gho`, `eurostat`
- `sex`: `female`, `male`, `all`
- `unit`: `per_100_000_person_years`, `percent`
- `rate_type`: `crude`, `age_standardised_world`,
  `age_standardised_world_1966`, `age_standardised_finland_2014`,
  `age_standardised_nordic_2000`, `age_standardised_europe_1976`,
  `age_standardised_europe_2013`, `age_standardised_who`

`count` remains reserved for future count indicators. Source-specific geography
and semantic constraints are validated. Unknown categories and dimensional
mismatches are rejected.

## Architecture

```text
MCP typed tools
    └── SourceCatalog
          ├── cross-source query resolution and ambiguity checks
          ├── FinnishCancerRegistryAdapter
          ├── NordcanAdapter
          ├── WhoGhoAdapter
          └── EurostatAdapter
                └── frozen source snapshots
                      └── strict Pydantic models + provenance
```

`src/sourcevahti/models.py` is the public schema. Version 0.3 adds a general
health topic and indicator definition, measure type, percent units,
uncertainty bounds, publisher notes, modelled/projected status and optional
cancer fields. Cancer mortality observations still require an exact cancer
definition and a per-100,000 rate.

The official MCP SDK derives JSON schemas from the typed functions and
Pydantic models. Domain exceptions become MCP tool errors so a model can correct
its request. Adapters remain source-specific; shared code handles normalised
search, validation, duplicate detection and ambiguity.

## Data refresh

Bundled snapshot files:

- `src/sourcevahti/data/finnish_cancer_registry_2024.csv`
- `src/sourcevahti/data/nordcan_lung_mortality_9_6.csv`
- `src/sourcevahti/data/who_gho_tobacco_use_2026_01_15.csv`
- `src/sourcevahti/data/eurostat_lung_mortality_2026_06_08.csv`

WHO and Eurostat have documented machine endpoints. Refresh their deliberately
narrow matrices outside server startup:

```bash
uv run python scripts/refresh_context_snapshots.py
```

The script requests only the reviewed indicators/dimensions, rejects missing
countries, short series, duplicate country-sex-year keys and negative values,
then writes deterministic CSV files. Review diffs, metadata, terms and
publisher flags before accepting them.

The Finnish Cancer Registry and NORDCAN interactive applications remain a
manual trust boundary. Preserve raw exports outside the repository, verify all
rate definitions and standard populations, update provenance with the
normalised file, and confirm that ambiguity tests still expose every valid
definition.

SourceVahti code is Apache-2.0. Source data retain publisher terms; every
provenance object carries a separate `license_note`.

## Deployment and DNS

The public endpoints are `sourcevahti.vahtian.com` for the hosted HTTP/MCP
service and `trends.ntog.org` for the NTOG Shiny application. DNS records should
only be created after each deployment supplies its canonical target hostname.

See [docs/DNS.md](docs/DNS.md) for Cloudflare records, provider-side custom
domain steps and verification commands.

## Development

```bash
uv sync --locked --all-extras --dev
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy src
uv run --frozen pytest
uv build
```

Tests use frozen official responses and the SDK's in-memory MCP client. CI runs
linting, type checking, tests and package builds on Python 3.11 and 3.13.

See [CONTRIBUTING.md](CONTRIBUTING.md) for source-update rules and
[SECURITY.md](SECURITY.md) for responsible disclosure.

## Licence

SourceVahti code is licensed under the
[Apache License, Version 2.0](LICENSE). No medical advice is provided. Always
cite the source and preserve the returned epidemiological definition when
reporting a value.
