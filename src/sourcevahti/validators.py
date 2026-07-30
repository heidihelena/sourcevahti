"""Validation and normalisation for user-supplied statistical dimensions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeVar

from sourcevahti.errors import InputValidationError
from sourcevahti.models import RateType, Sex, SourceId, Unit

_SPACE_RE = re.compile(r"[\s_-]+")
_QUERY_TOKEN_RE = re.compile(r"[a-z0-9]+")
_Dimension = TypeVar("_Dimension", Sex, Unit, SourceId)
_GEOGRAPHY_ALIASES = {
    "denmark": "Denmark",
    "faroe islands": "Faroe Islands",
    "faroe": "Faroe Islands",
    "finland": "Finland",
    "greenland": "Greenland",
    "iceland": "Iceland",
    "norway": "Norway",
    "sweden": "Sweden",
    "nordcan countries": "NORDCAN countries",
    "nordcan countries excluding faroe islands and greenland": (
        "NORDCAN countries excl. Faroe Islands and Greenland"
    ),
    "nordcan countries excl faroe islands and greenland": (
        "NORDCAN countries excl. Faroe Islands and Greenland"
    ),
    "nordcan countries excl. faroe islands and greenland": (
        "NORDCAN countries excl. Faroe Islands and Greenland"
    ),
}


@dataclass(frozen=True)
class QueryConstraints:
    """Material dimensions recognised in a validated free-text query."""

    query: str
    source_id: SourceId | None
    sex: Sex | None
    unit: Unit | None
    geography: str | None
    rate_types: frozenset[RateType] | None


def _normalise(value: str) -> str:
    """Normalise common spelling separators without weakening validation."""
    return _SPACE_RE.sub(" ", value.strip().casefold())


def validate_query(query: str) -> str:
    """Require a meaningful, bounded indicator query."""
    cleaned = " ".join(query.split())
    if len(cleaned) < 2:
        raise InputValidationError(
            "query must contain at least two characters",
            details={"field": "query"},
        )
    if len(cleaned) > 200:
        raise InputValidationError(
            "query cannot exceed 200 characters",
            details={"field": "query", "maximum": 200},
        )
    return cleaned


def constrain_query(
    query: str,
    *,
    sex: str | Sex | None = None,
    unit: str | Unit | None = None,
    rate_type: str | RateType | None = None,
    source: str | SourceId | None = None,
    geography: str | None = None,
) -> QueryConstraints:
    """Combine dimensions stated in free text with explicit tool arguments."""
    cleaned = validate_query(query)
    tokens = _QUERY_TOKEN_RE.findall(_normalise(cleaned))
    token_set = set(tokens)

    query_sexes: set[Sex] = set()
    if token_set & {"female", "females", "woman", "women"}:
        query_sexes.add(Sex.FEMALE)
    if token_set & {"male", "males", "man", "men"}:
        query_sexes.add(Sex.MALE)
    if _has_phrase(tokens, ("both", "sexes")) or _has_phrase(tokens, ("all", "sexes")):
        query_sexes.add(Sex.ALL)
    if len(query_sexes) > 1:
        raise InputValidationError(
            "query contains multiple sex categories",
            details={
                "field": "query",
                "dimension": "sex",
                "values": sorted(value.value for value in query_sexes),
            },
            hint="Request one sex category per indicator query.",
        )
    query_sex = next(iter(query_sexes), None)

    query_sources: set[SourceId] = set()
    if "nordcan" in token_set:
        query_sources.add(SourceId.NORDCAN)
    if "fcr" in token_set or _has_phrase(tokens, ("finnish", "cancer", "registry")):
        query_sources.add(SourceId.FINNISH_CANCER_REGISTRY)
    if (
        "gho" in token_set
        or "who" in token_set
        or _has_phrase(tokens, ("global", "health", "observatory"))
    ):
        query_sources.add(SourceId.WHO_GHO)
    if "eurostat" in token_set:
        query_sources.add(SourceId.EUROSTAT)
    if len(query_sources) > 1:
        raise InputValidationError(
            "query contains multiple sources",
            details={
                "field": "query",
                "dimension": "source",
                "values": sorted(value.value for value in query_sources),
            },
            hint="Request one source per resolved indicator query.",
        )
    query_source = next(iter(query_sources), None)

    query_geographies = _extract_geographies(tokens)
    if len(query_geographies) > 1:
        raise InputValidationError(
            "query contains multiple geographies",
            details={
                "field": "query",
                "dimension": "geography",
                "values": sorted(query_geographies),
            },
            hint="Request one geography per resolved indicator query.",
        )
    query_geography = next(iter(query_geographies), None)

    query_units: set[Unit] = set()
    if token_set & {"count", "counts"} or _has_phrase(tokens, ("number", "of", "deaths")):
        query_units.add(Unit.COUNT)
    if _contains_per_100_000(tokens):
        query_units.add(Unit.PER_100_000_PERSON_YEARS)
    if token_set & {"percent", "percentage", "pct"}:
        query_units.add(Unit.PERCENT)
    if len(query_units) > 1:
        raise InputValidationError(
            "query contains conflicting units",
            details={
                "field": "query",
                "dimension": "unit",
                "values": sorted(value.value for value in query_units),
            },
        )
    query_unit = next(iter(query_units), None)

    query_rate_types: set[RateType] = set()
    if "crude" in token_set:
        query_rate_types.add(RateType.CRUDE)

    world_1966_standard = (
        _has_phrase(tokens, ("world", "1966"))
        or _has_phrase(tokens, ("1966", "world"))
        or _has_phrase(tokens, ("world", "standard", "population", "1966"))
    )
    world_standard = (
        _has_phrase(tokens, ("world", "standard", "population"))
        or _has_phrase(tokens, ("world", "standardised"))
        or _has_phrase(tokens, ("world", "standardized"))
        or _has_phrase(tokens, ("asr", "world"))
    )
    finland_2014_standard = (
        _has_phrase(tokens, ("finland", "2014", "standardised"))
        or _has_phrase(tokens, ("finland", "2014", "standardized"))
        or _has_phrase(tokens, ("finland", "standard", "population", "2014"))
        or _has_phrase(tokens, ("finland", "2014", "standard", "population"))
    )
    nordic_2000_standard = (
        _has_phrase(tokens, ("nordic", "2000"))
        or _has_phrase(tokens, ("nordic", "standard"))
        or _has_phrase(tokens, ("asr", "nordic"))
    )
    europe_1976_standard = (
        _has_phrase(tokens, ("europe", "1976"))
        or _has_phrase(tokens, ("european", "1976"))
        or _has_phrase(tokens, ("asr", "european", "1976"))
    )
    europe_2013_standard = (
        _has_phrase(tokens, ("europe", "2013"))
        or _has_phrase(tokens, ("european", "2013"))
        or _has_phrase(tokens, ("asr", "european", "2013"))
    )
    who_standard = (
        _has_phrase(tokens, ("who", "standard", "population"))
        or _has_phrase(tokens, ("who", "standardised"))
        or _has_phrase(tokens, ("who", "standardized"))
    )
    if world_1966_standard:
        query_rate_types.add(RateType.AGE_STANDARDISED_WORLD_1966)
    elif world_standard:
        query_rate_types.update(
            {
                RateType.AGE_STANDARDISED_WORLD,
                RateType.AGE_STANDARDISED_WORLD_1966,
            }
        )
    if finland_2014_standard:
        query_rate_types.add(RateType.AGE_STANDARDISED_FINLAND_2014)
    if nordic_2000_standard:
        query_rate_types.add(RateType.AGE_STANDARDISED_NORDIC_2000)
    if europe_1976_standard:
        query_rate_types.add(RateType.AGE_STANDARDISED_EUROPE_1976)
    if europe_2013_standard:
        query_rate_types.add(RateType.AGE_STANDARDISED_EUROPE_2013)
    if who_standard:
        query_rate_types.add(RateType.AGE_STANDARDISED_WHO)

    generic_age_standardised = (
        "standardised" in token_set
        or "standardized" in token_set
        or "asr" in token_set
        or _has_phrase(tokens, ("age", "adjusted"))
    )
    has_specific_standard = any(
        (
            world_standard,
            world_1966_standard,
            finland_2014_standard,
            nordic_2000_standard,
            europe_1976_standard,
            europe_2013_standard,
            who_standard,
        )
    )
    if generic_age_standardised and not has_specific_standard:
        query_rate_types.update(rate for rate in RateType if rate is not RateType.CRUDE)

    explicit_source = validate_source(source)
    explicit_sex = validate_sex(sex)
    explicit_unit = validate_unit(unit)
    explicit_geography = validate_geography(geography)
    explicit_rate_type = validate_rate_type(rate_type)
    resolved_source = _merge_single_constraint(
        "source",
        explicit_source,
        query_source,
    )
    resolved_sex = _merge_single_constraint("sex", explicit_sex, query_sex)
    resolved_unit = _merge_single_constraint("unit", explicit_unit, query_unit)
    resolved_geography = _merge_geography(explicit_geography, query_geography)

    if (
        explicit_rate_type is not None
        and query_rate_types
        and explicit_rate_type not in query_rate_types
    ):
        raise InputValidationError(
            "rate_type conflicts with the free-text query",
            details={
                "field": "rate_type",
                "supplied": explicit_rate_type.value,
                "query_values": sorted(value.value for value in query_rate_types),
            },
        )
    resolved_rate_types = (
        frozenset({explicit_rate_type})
        if explicit_rate_type is not None
        else frozenset(query_rate_types) or None
    )
    return QueryConstraints(
        query=cleaned,
        source_id=resolved_source,
        sex=resolved_sex,
        unit=resolved_unit,
        geography=resolved_geography,
        rate_types=resolved_rate_types,
    )


def _has_phrase(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    """Return whether a complete token phrase occurs in order."""
    width = len(phrase)
    return any(
        tuple(tokens[index : index + width]) == phrase for index in range(len(tokens) - width + 1)
    )


def _contains_per_100_000(tokens: list[str]) -> bool:
    """Recognise the canonical rate denominator without matching arbitrary numbers."""
    return (
        _has_phrase(tokens, ("per", "100000"))
        or _has_phrase(tokens, ("per", "100", "000"))
        or _has_phrase(tokens, ("per", "100000", "person", "years"))
        or _has_phrase(tokens, ("per", "100", "000", "person", "years"))
    )


def _extract_geographies(tokens: list[str]) -> set[str]:
    """Extract supported countries without confusing standard populations."""
    joined = " ".join(tokens)
    geographies: set[str] = set()
    aggregate_aliases = (
        "nordcan countries excluding faroe islands and greenland",
        "nordcan countries excl faroe islands and greenland",
    )
    aggregate_match = next(
        (alias for alias in aggregate_aliases if alias in joined),
        None,
    )
    if aggregate_match:
        geographies.add(_GEOGRAPHY_ALIASES[aggregate_match])
        return geographies
    if "nordcan countries" in joined:
        geographies.add(_GEOGRAPHY_ALIASES["nordcan countries"])
        return geographies
    if _has_phrase(tokens, ("faroe", "islands")):
        geographies.add("Faroe Islands")
    for token in {"denmark", "finland", "greenland", "iceland", "norway", "sweden"}:
        if token in tokens:
            geographies.add(_GEOGRAPHY_ALIASES[token])
    return geographies


def _merge_single_constraint(
    dimension: str,
    explicit: _Dimension | None,
    inferred: _Dimension | None,
) -> _Dimension | None:
    """Reject disagreement instead of letting explicit arguments hide query intent."""
    if explicit is not None and inferred is not None and explicit is not inferred:
        raise InputValidationError(
            f"{dimension} conflicts with the free-text query",
            details={
                "field": dimension,
                "supplied": explicit.value,
                "query_value": inferred.value,
            },
        )
    return explicit or inferred


def _merge_geography(explicit: str | None, inferred: str | None) -> str | None:
    """Reject explicit geography that contradicts a country named in the query."""
    if explicit is not None and inferred is not None and explicit.casefold() != inferred.casefold():
        raise InputValidationError(
            "geography conflicts with the free-text query",
            details={
                "field": "geography",
                "supplied": explicit,
                "query_value": inferred,
            },
        )
    return explicit or inferred


def validate_source(value: str | SourceId | None) -> SourceId | None:
    """Normalise supported source identifiers and names."""
    if value is None or isinstance(value, SourceId):
        return value
    aliases = {
        "fcr": SourceId.FINNISH_CANCER_REGISTRY,
        "finnish cancer registry": SourceId.FINNISH_CANCER_REGISTRY,
        "finnish_cancer_registry": SourceId.FINNISH_CANCER_REGISTRY,
        "nordcan": SourceId.NORDCAN,
        "who": SourceId.WHO_GHO,
        "who gho": SourceId.WHO_GHO,
        "who_gho": SourceId.WHO_GHO,
        "global health observatory": SourceId.WHO_GHO,
        "eurostat": SourceId.EUROSTAT,
    }
    normalised = _normalise(value)
    try:
        return aliases[normalised]
    except KeyError as exc:
        raise InputValidationError(
            f"unsupported source {value!r}",
            details={
                "field": "source",
                "accepted": [member.value for member in SourceId],
            },
        ) from exc


def validate_geography(value: str | None) -> str | None:
    """Normalise the geographies available in the bundled source snapshots."""
    if value is None:
        return None
    normalised = _normalise(value)
    try:
        return _GEOGRAPHY_ALIASES[normalised]
    except KeyError as exc:
        raise InputValidationError(
            f"unsupported geography {value!r}",
            details={
                "field": "geography",
                "accepted": sorted(set(_GEOGRAPHY_ALIASES.values())),
            },
        ) from exc


def validate_sex(value: str | Sex | None) -> Sex | None:
    """Map a small documented alias set and reject unknown sex categories."""
    if value is None or isinstance(value, Sex):
        return value
    aliases = {
        "female": Sex.FEMALE,
        "f": Sex.FEMALE,
        "woman": Sex.FEMALE,
        "women": Sex.FEMALE,
        "male": Sex.MALE,
        "m": Sex.MALE,
        "man": Sex.MALE,
        "men": Sex.MALE,
        "all": Sex.ALL,
        "both": Sex.ALL,
        "both together": Sex.ALL,
    }
    normalised = _normalise(value)
    try:
        return aliases[normalised]
    except KeyError as exc:
        raise InputValidationError(
            f"unsupported sex {value!r}",
            details={
                "field": "sex",
                "accepted": [member.value for member in Sex],
            },
        ) from exc


def validate_unit(value: str | Unit | None) -> Unit | None:
    """Normalise supported rate-unit spellings and reject dimensional mismatch."""
    if value is None or isinstance(value, Unit):
        return value
    aliases = {
        "count": Unit.COUNT,
        "number": Unit.COUNT,
        "per 100 000": Unit.PER_100_000_PERSON_YEARS,
        "per 100000": Unit.PER_100_000_PERSON_YEARS,
        "per 100 000 person years": Unit.PER_100_000_PERSON_YEARS,
        "per 100000 person years": Unit.PER_100_000_PERSON_YEARS,
        "per_100_000_person_years": Unit.PER_100_000_PERSON_YEARS,
        "rate per 100 000": Unit.PER_100_000_PERSON_YEARS,
        "percent": Unit.PERCENT,
        "percentage": Unit.PERCENT,
        "pct": Unit.PERCENT,
    }
    normalised = _normalise(value)
    try:
        return aliases[normalised]
    except KeyError as exc:
        raise InputValidationError(
            f"unsupported unit {value!r}",
            details={
                "field": "unit",
                "accepted": [member.value for member in Unit],
            },
        ) from exc


def validate_rate_type(value: str | RateType | None) -> RateType | None:
    """Normalise explicit rate definitions while preserving their distinction."""
    if value is None or isinstance(value, RateType):
        return value
    aliases = {
        "crude": RateType.CRUDE,
        "crude rate": RateType.CRUDE,
        "age standardised world 1966": RateType.AGE_STANDARDISED_WORLD_1966,
        "age_standardised_world_1966": RateType.AGE_STANDARDISED_WORLD_1966,
        "age standardized world 1966": RateType.AGE_STANDARDISED_WORLD_1966,
        "world 1966": RateType.AGE_STANDARDISED_WORLD_1966,
        "age standardised world": RateType.AGE_STANDARDISED_WORLD,
        "age_standardised_world": RateType.AGE_STANDARDISED_WORLD,
        "age standardized world": RateType.AGE_STANDARDISED_WORLD,
        "age standardised finland 2014": RateType.AGE_STANDARDISED_FINLAND_2014,
        "finland 2014": RateType.AGE_STANDARDISED_FINLAND_2014,
        "age_standardised_finland_2014": RateType.AGE_STANDARDISED_FINLAND_2014,
        "age standardized finland 2014": RateType.AGE_STANDARDISED_FINLAND_2014,
        "age standardised nordic 2000": RateType.AGE_STANDARDISED_NORDIC_2000,
        "age_standardised_nordic_2000": RateType.AGE_STANDARDISED_NORDIC_2000,
        "nordic 2000": RateType.AGE_STANDARDISED_NORDIC_2000,
        "age standardised europe 1976": RateType.AGE_STANDARDISED_EUROPE_1976,
        "age_standardised_europe_1976": RateType.AGE_STANDARDISED_EUROPE_1976,
        "european 1976": RateType.AGE_STANDARDISED_EUROPE_1976,
        "age standardised europe 2013": RateType.AGE_STANDARDISED_EUROPE_2013,
        "age_standardised_europe_2013": RateType.AGE_STANDARDISED_EUROPE_2013,
        "european 2013": RateType.AGE_STANDARDISED_EUROPE_2013,
        "age standardised who": RateType.AGE_STANDARDISED_WHO,
        "age_standardised_who": RateType.AGE_STANDARDISED_WHO,
        "age standardized who": RateType.AGE_STANDARDISED_WHO,
        "who standard population": RateType.AGE_STANDARDISED_WHO,
    }
    normalised = _normalise(value)
    try:
        return aliases[normalised]
    except KeyError as exc:
        raise InputValidationError(
            f"unsupported rate_type {value!r}",
            details={
                "field": "rate_type",
                "accepted": [member.value for member in RateType],
            },
        ) from exc


def validate_year_range(
    start_year: int | None,
    end_year: int | None,
) -> tuple[int | None, int | None]:
    """Validate a closed optional year range."""
    for field, value in (("start_year", start_year), ("end_year", end_year)):
        if value is not None and not 1900 <= value <= 2200:
            raise InputValidationError(
                f"{field} must be between 1900 and 2200",
                details={"field": field, "value": value},
            )
    if start_year is not None and end_year is not None and start_year > end_year:
        raise InputValidationError(
            "start_year cannot be after end_year",
            details={"start_year": start_year, "end_year": end_year},
        )
    return start_year, end_year
