"""Validation tests for dimensions that materially change an observation."""

import pytest

from sourcevahti.errors import InputValidationError
from sourcevahti.models import RateType, Sex, SourceId, Unit
from sourcevahti.validators import (
    constrain_query,
    validate_geography,
    validate_query,
    validate_rate_type,
    validate_sex,
    validate_source,
    validate_unit,
    validate_year_range,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("female", Sex.FEMALE),
        ("Women", Sex.FEMALE),
        ("m", Sex.MALE),
        ("both together", Sex.ALL),
    ],
)
def test_validate_sex_accepts_documented_aliases(raw: str, expected: Sex) -> None:
    assert validate_sex(raw) is expected


def test_validate_sex_rejects_unknown_category() -> None:
    with pytest.raises(InputValidationError) as raised:
        validate_sex("unknown")

    payload = raised.value.as_dict()["error"]
    assert payload["code"] == "invalid_input"
    assert payload["details"]["field"] == "sex"
    assert payload["details"]["accepted"] == ["female", "male", "all"]


@pytest.mark.parametrize(
    "raw",
    [
        "per 100 000",
        "per 100000 person years",
        "per_100_000_person_years",
        "rate per 100 000",
    ],
)
def test_validate_unit_normalises_supported_spellings(raw: str) -> None:
    assert validate_unit(raw) is Unit.PER_100_000_PERSON_YEARS


def test_validate_unit_accepts_percentage() -> None:
    assert validate_unit("percent") is Unit.PERCENT
    assert validate_unit("number") is Unit.COUNT


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("crude rate", RateType.CRUDE),
        ("world 1966", RateType.AGE_STANDARDISED_WORLD_1966),
        ("age standardised world", RateType.AGE_STANDARDISED_WORLD),
        ("Nordic 2000", RateType.AGE_STANDARDISED_NORDIC_2000),
        ("European 2013", RateType.AGE_STANDARDISED_EUROPE_2013),
        ("Finland 2014", RateType.AGE_STANDARDISED_FINLAND_2014),
        ("WHO standard population", RateType.AGE_STANDARDISED_WHO),
    ],
)
def test_validate_rate_type(raw: str, expected: RateType) -> None:
    assert validate_rate_type(raw) is expected


def test_validate_rate_type_rejects_unknown_definition() -> None:
    with pytest.raises(InputValidationError, match="unsupported rate_type"):
        validate_rate_type("European standard population")


def test_validate_year_range_rejects_reverse_range() -> None:
    with pytest.raises(InputValidationError, match="start_year"):
        validate_year_range(2024, 2020)
    with pytest.raises(InputValidationError, match="end_year"):
        validate_year_range(None, 1800)


def test_validate_query_collapses_whitespace_and_enforces_bounds() -> None:
    assert validate_query("  lung   mortality ") == "lung mortality"
    with pytest.raises(InputValidationError):
        validate_query("x")
    with pytest.raises(InputValidationError):
        validate_query("x" * 201)


def test_query_dimensions_are_material_constraints() -> None:
    constraints = constrain_query("male lung mortality per 100 000, world standard population")

    assert constraints.sex is Sex.MALE
    assert constraints.unit is Unit.PER_100_000_PERSON_YEARS
    assert constraints.rate_types == {
        RateType.AGE_STANDARDISED_WORLD,
        RateType.AGE_STANDARDISED_WORLD_1966,
    }


def test_generic_age_standardised_query_preserves_both_definitions() -> None:
    constraints = constrain_query("female age-standardised lung mortality")

    assert constraints.rate_types == set(RateType) - {RateType.CRUDE}


@pytest.mark.parametrize(
    ("query", "kwargs", "dimension"),
    [
        ("male lung mortality", {"sex": "female"}, "sex"),
        ("lung mortality count", {"unit": "per 100 000"}, "unit"),
        ("crude lung mortality", {"rate_type": "age standardised world 1966"}, "rate_type"),
    ],
)
def test_explicit_dimensions_cannot_conflict_with_query(
    query: str,
    kwargs: dict[str, str],
    dimension: str,
) -> None:
    with pytest.raises(InputValidationError) as raised:
        constrain_query(query, **kwargs)

    assert raised.value.details["field"] == dimension


def test_query_source_and_geography_are_material_constraints() -> None:
    constraints = constrain_query("NORDCAN female Faroe Islands lung mortality, European 1976")

    assert constraints.source_id is SourceId.NORDCAN
    assert constraints.geography == "Faroe Islands"
    assert constraints.rate_types == {RateType.AGE_STANDARDISED_EUROPE_1976}


def test_source_and_geography_alias_validation() -> None:
    assert validate_source("FCR") is SourceId.FINNISH_CANCER_REGISTRY
    assert validate_source("NORDCAN") is SourceId.NORDCAN
    assert validate_source("WHO") is SourceId.WHO_GHO
    assert validate_source("Eurostat") is SourceId.EUROSTAT
    assert validate_geography("faroe") == "Faroe Islands"
    assert validate_geography("Finland") == "Finland"
    assert (
        validate_geography("NORDCAN countries excl. Faroe Islands and Greenland")
        == "NORDCAN countries excl. Faroe Islands and Greenland"
    )

    with pytest.raises(InputValidationError, match="unsupported source"):
        validate_source("CDC")
    with pytest.raises(InputValidationError, match="unsupported geography"):
        validate_geography("Estonia")


def test_query_rejects_conflicting_source_and_geography() -> None:
    with pytest.raises(InputValidationError, match="source conflicts"):
        constrain_query("NORDCAN Finland lung mortality", source="fcr")
    with pytest.raises(InputValidationError, match="geography conflicts"):
        constrain_query(
            "NORDCAN Finland lung mortality",
            geography="Denmark",
        )
