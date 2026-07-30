"""NORDCAN adapter tests against frozen version 9.6 table outputs."""

from importlib import resources

import pytest

from sourcevahti.adapters.nordcan import NordcanAdapter
from sourcevahti.errors import AmbiguousIndicatorError, SourceDataError
from sourcevahti.models import RateType, SourceId


@pytest.fixture
def adapter() -> NordcanAdapter:
    return NordcanAdapter()


def test_snapshot_covers_nine_geographies_and_five_rate_definitions(
    adapter: NordcanAdapter,
) -> None:
    assert len(adapter.indicators) == 45
    assert {indicator.geography for indicator in adapter.indicators} == {
        "NORDCAN countries",
        "NORDCAN countries excl. Faroe Islands and Greenland",
        "Denmark",
        "Faroe Islands",
        "Finland",
        "Greenland",
        "Iceland",
        "Norway",
        "Sweden",
    }
    assert {indicator.rate_type for indicator in adapter.indicators} == {
        RateType.CRUDE,
        RateType.AGE_STANDARDISED_WORLD,
        RateType.AGE_STANDARDISED_NORDIC_2000,
        RateType.AGE_STANDARDISED_EUROPE_1976,
        RateType.AGE_STANDARDISED_EUROPE_2013,
    }


def test_latest_denmark_nordic_standardised_mortality(
    adapter: NordcanAdapter,
) -> None:
    result = adapter.get_latest_observation(
        query="NORDCAN female Denmark lung mortality, Nordic 2000"
    )

    assert result.observation.year == 2024
    assert result.observation.value == 43.0
    assert result.observation.standard_population == "NORDCAN population 2000"
    assert result.observation.provenance.source_id is SourceId.NORDCAN
    assert result.observation.provenance.source_release_version == "9.6"
    assert result.observation.age_group == "All ages (0-85+)"


def test_series_and_source_specific_latest_years(adapter: NordcanAdapter) -> None:
    norway = adapter.get_observations(indicator_id="nordcan.lung.mortality.crude.female.norway")
    faroe = adapter.get_latest_observation(query="female Faroe Islands lung mortality crude")

    assert [item.year for item in norway.observations] == [2023, 2024]
    assert [item.value for item in norway.observations] == [36.4, 39.8]
    assert faroe.observation.year == 2023
    assert faroe.observation.value == 45.9


def test_unqualified_denmark_rate_is_ambiguous(adapter: NordcanAdapter) -> None:
    with pytest.raises(AmbiguousIndicatorError) as raised:
        adapter.get_latest_observation(query="female Denmark lung cancer mortality rate")

    candidates = raised.value.details["candidates"]
    assert len(candidates) == 5
    assert {candidate["source"] for candidate in candidates} == {"nordcan"}
    assert {candidate["geography"] for candidate in candidates} == {"Denmark"}


def test_duplicate_wide_source_row_is_rejected(tmp_path) -> None:
    bundled = resources.files("sourcevahti").joinpath("data/nordcan_lung_mortality_9_6.csv")
    lines = bundled.read_text(encoding="utf-8").splitlines()
    duplicate = tmp_path / "duplicate.csv"
    duplicate.write_text(
        "\n".join([lines[0], lines[1], lines[1], *lines[2:], ""]),
        encoding="utf-8",
    )

    with pytest.raises(SourceDataError, match="duplicate observation") as raised:
        NordcanAdapter(duplicate)

    assert raised.value.details["year"] == 2023
    assert raised.value.details["rows"] == [2, 3]


def test_invalid_nordcan_source_row_is_actionable(tmp_path) -> None:
    invalid = tmp_path / "invalid.csv"
    invalid.write_text(
        "geography,geography_code,year,asr_world,asr_nordic_2000,"
        "asr_europe_1976,asr_europe_2013,crude\n"
        "Denmark,denmark,not-a-year,1,2,3,4,5\n",
        encoding="utf-8",
    )

    with pytest.raises(SourceDataError, match="invalid row") as raised:
        NordcanAdapter(invalid)
    assert raised.value.details["row"] == 2
