"""WHO GHO and Eurostat adapter tests against frozen official responses."""

from sourcevahti.adapters import EurostatAdapter, WhoGhoAdapter
from sourcevahti.models import (
    Measure,
    ObservationStatus,
    RateType,
    SourceId,
    Unit,
)


def test_who_tobacco_snapshot_preserves_uncertainty_and_projection_status() -> None:
    adapter = WhoGhoAdapter()

    assert len(adapter.indicators) == 15
    result = adapter.get_latest_observation(
        query="WHO female Finland current tobacco use prevalence age-standardised"
    )
    observation = result.observation

    assert observation.year == 2025
    assert observation.value == 17.1
    assert observation.lower_bound == 14.0
    assert observation.upper_bound == 20.2
    assert observation.unit is Unit.PERCENT
    assert observation.measure is Measure.TOBACCO_USE_PREVALENCE
    assert observation.rate_type is RateType.AGE_STANDARDISED_WHO
    assert observation.observation_status is ObservationStatus.PROJECTED
    assert observation.cancer_site is None
    assert observation.provenance.source_id is SourceId.WHO_GHO


def test_who_series_has_reviewed_nordic_scope() -> None:
    adapter = WhoGhoAdapter()
    series = adapter.get_observations(
        indicator_id=("who_gho.tobacco.current_use.age_standardised.female.denmark")
    )

    assert series.count == 10
    assert series.observations[0].year == 2000
    assert series.observations[-1].year == 2025
    assert all(item.lower_bound <= item.value <= item.upper_bound for item in series.observations)


def test_eurostat_lung_snapshot_preserves_rate_definition() -> None:
    adapter = EurostatAdapter()

    assert len(adapter.indicators) == 15
    result = adapter.get_latest_observation(
        query="Eurostat female Sweden lung mortality European 2013"
    )
    observation = result.observation

    assert observation.year == 2023
    assert observation.value == 32.57
    assert observation.measure is Measure.CANCER_MORTALITY_RATE
    assert observation.unit is Unit.PER_100_000_PERSON_YEARS
    assert observation.rate_type is RateType.AGE_STANDARDISED_EUROPE_2013
    assert observation.standard_population == "European Standard Population 2013"
    assert observation.cancer_definition is not None
    assert "C33-C34" in observation.cancer_definition
    assert observation.provenance.source_id is SourceId.EUROSTAT


def test_eurostat_series_is_annual_from_2011_to_2023() -> None:
    adapter = EurostatAdapter()
    series = adapter.get_observations(
        indicator_id=("eurostat.lung.mortality.asr_europe_2013.female.norway")
    )

    assert series.count == 13
    assert [item.year for item in series.observations] == list(range(2011, 2024))
