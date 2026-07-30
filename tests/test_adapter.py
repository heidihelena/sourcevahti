"""Source-specific adapter tests against the frozen registry response."""

from datetime import date
from importlib import resources

import pytest

from sourcevahti.adapters.finnish_cancer_registry import (
    FinnishCancerRegistryAdapter,
    iter_observations,
)
from sourcevahti.errors import (
    AmbiguousIndicatorError,
    IndicatorNotFoundError,
    InputValidationError,
    SourceDataError,
)
from sourcevahti.models import RateType, Sex, Unit


@pytest.fixture
def adapter() -> FinnishCancerRegistryAdapter:
    return FinnishCancerRegistryAdapter()


def test_snapshot_contains_three_distinct_rate_definitions(
    adapter: FinnishCancerRegistryAdapter,
) -> None:
    assert len(adapter.indicators) == 3
    assert {indicator.rate_type for indicator in adapter.indicators} == {
        RateType.CRUDE,
        RateType.AGE_STANDARDISED_WORLD_1966,
        RateType.AGE_STANDARDISED_FINLAND_2014,
    }
    assert {observation.value for observation in iter_observations(adapter)} == {29.96, 9.04, 23.28}


def test_search_returns_all_valid_mortality_rate_variants(
    adapter: FinnishCancerRegistryAdapter,
) -> None:
    result = adapter.search_indicators(
        "female lung cancer mortality rate",
        sex="women",
        unit="per 100 000",
    )

    assert result.count == 3
    assert all(match.score == 1 for match in result.matches)
    assert all(match.indicator.sex is Sex.FEMALE for match in result.matches)
    assert all(match.indicator.unit is Unit.PER_100_000_PERSON_YEARS for match in result.matches)


def test_free_text_sex_is_enforced_without_explicit_filter(
    adapter: FinnishCancerRegistryAdapter,
) -> None:
    assert adapter.search_indicators("male lung cancer mortality rate").count == 0
    with pytest.raises(IndicatorNotFoundError):
        adapter.get_latest_observation(
            query="male lung cancer mortality rate",
            rate_type="crude",
        )
    with pytest.raises(InputValidationError, match="sex conflicts"):
        adapter.get_latest_observation(
            query="male lung cancer mortality rate",
            sex="female",
            rate_type="crude",
        )


def test_free_text_rate_definition_is_enforced(
    adapter: FinnishCancerRegistryAdapter,
) -> None:
    crude = adapter.get_latest_observation(query="female crude lung cancer mortality rate")
    assert crude.indicator.rate_type is RateType.CRUDE

    world = adapter.get_latest_observation(query="female lung mortality, world standard population")
    assert world.indicator.rate_type is RateType.AGE_STANDARDISED_WORLD_1966

    with pytest.raises(AmbiguousIndicatorError) as raised:
        adapter.get_latest_observation(query="female age-standardised lung cancer mortality rate")
    assert len(raised.value.details["candidates"]) == 2


def test_acceptance_latest_female_lung_mortality_finland_2014(
    adapter: FinnishCancerRegistryAdapter,
) -> None:
    result = adapter.get_latest_observation(
        query="female lung cancer mortality rate",
        sex="female",
        rate_type="age_standardised_finland_2014",
        unit="per_100_000_person_years",
    )

    indicator = result.indicator
    observation = result.observation
    assert indicator.cancer_definition == (
        "Malignant neoplasms of trachea and bronchus/lung (ICD-10 C33-C34)"
    )
    assert observation.year == 2024
    assert observation.value == 23.28
    assert observation.rate_type is RateType.AGE_STANDARDISED_FINLAND_2014
    assert observation.standard_population == "Finland population 2014"
    assert observation.unit is Unit.PER_100_000_PERSON_YEARS
    assert observation.sex is Sex.FEMALE
    assert str(observation.provenance.citation_url).startswith(
        "https://cancerregistry.fi/statistics/cancer-statistics/"
    )
    assert observation.provenance.source_release_date == date(2026, 4, 24)
    assert observation.provenance.retrieval_date == date(2026, 7, 30)


def test_ambiguous_mortality_rate_lists_actionable_candidates(
    adapter: FinnishCancerRegistryAdapter,
) -> None:
    with pytest.raises(AmbiguousIndicatorError) as raised:
        adapter.get_latest_observation(
            query="mortality rate",
            sex="female",
        )

    error = raised.value.as_dict()["error"]
    assert error["code"] == "ambiguous_indicator"
    assert len(error["details"]["candidates"]) == 3
    assert {candidate["rate_type"] for candidate in error["details"]["candidates"]} == {
        "crude",
        "age_standardised_world_1966",
        "age_standardised_finland_2014",
    }
    assert "rate_type" in error["hint"]


def test_exact_indicator_id_cannot_conflict_with_dimensions(
    adapter: FinnishCancerRegistryAdapter,
) -> None:
    with pytest.raises(InputValidationError, match="conflicts"):
        adapter.get_latest_observation(
            indicator_id="fcr.lung_trachea.mortality.crude.female",
            rate_type="age_standardised_finland_2014",
        )


def test_observation_year_filter_can_return_empty_valid_series(
    adapter: FinnishCancerRegistryAdapter,
) -> None:
    result = adapter.get_observations(
        indicator_id="fcr.lung_trachea.mortality.crude.female",
        start_year=2020,
        end_year=2023,
    )
    assert result.count == 0
    assert result.observations == []


def test_unknown_indicator_is_actionable(
    adapter: FinnishCancerRegistryAdapter,
) -> None:
    with pytest.raises(IndicatorNotFoundError) as raised:
        adapter.get_latest_observation(indicator_id="fcr.not_real")
    assert "search_indicators" in (raised.value.hint or "")


def test_missing_snapshot_column_raises_source_data_error(tmp_path) -> None:
    bad_snapshot = tmp_path / "bad.csv"
    bad_snapshot.write_text("indicator_id,year\nbroken,2024\n", encoding="utf-8")

    with pytest.raises(SourceDataError) as raised:
        FinnishCancerRegistryAdapter(bad_snapshot)

    assert "indicator_name" in raised.value.details["missing_columns"]


def test_missing_and_invalid_snapshot_rows_are_source_errors(tmp_path) -> None:
    with pytest.raises(SourceDataError, match="could not read"):
        FinnishCancerRegistryAdapter(tmp_path / "missing.csv")

    bundled = resources.files("sourcevahti").joinpath("data/finnish_cancer_registry_2024.csv")
    invalid_snapshot = tmp_path / "invalid.csv"
    invalid_snapshot.write_text(
        bundled.read_text(encoding="utf-8").replace(
            ",2024,29.96,",
            ",not-a-year,29.96,",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(SourceDataError, match="invalid row") as raised:
        FinnishCancerRegistryAdapter(invalid_snapshot)
    assert raised.value.details["row"] == 2


def test_duplicate_indicator_year_is_rejected(tmp_path) -> None:
    bundled = resources.files("sourcevahti").joinpath("data/finnish_cancer_registry_2024.csv")
    snapshot = bundled.read_text(encoding="utf-8")
    header, first_row, *remaining_rows = snapshot.splitlines()
    duplicate_snapshot = tmp_path / "duplicate.csv"
    duplicate_snapshot.write_text(
        "\n".join([header, first_row, first_row, *remaining_rows, ""]),
        encoding="utf-8",
    )

    with pytest.raises(SourceDataError, match="duplicate observation") as raised:
        FinnishCancerRegistryAdapter(duplicate_snapshot)

    assert raised.value.details == {
        "indicator_id": "fcr.lung_trachea.mortality.crude.female",
        "year": 2024,
        "rows": [2, 3],
    }


def test_resolution_failure_paths_are_actionable(
    adapter: FinnishCancerRegistryAdapter,
) -> None:
    with pytest.raises(InputValidationError, match="indicator_id or query"):
        adapter.get_latest_observation()
    with pytest.raises(IndicatorNotFoundError, match="no indicator matched"):
        adapter.get_latest_observation(query="kidney incidence")
    with pytest.raises(InputValidationError, match="limit"):
        adapter.search_indicators("lung mortality", limit=0)

    no_count_matches = adapter.search_indicators("lung mortality", unit="count")
    assert no_count_matches.count == 0
