"""Cross-source routing and ambiguity tests."""

import pytest

from sourcevahti.adapters import FinnishCancerRegistryAdapter
from sourcevahti.catalog import SourceCatalog
from sourcevahti.errors import (
    AmbiguousIndicatorError,
    IndicatorNotFoundError,
    SourceDataError,
)
from sourcevahti.models import SourceId


@pytest.fixture
def catalog() -> SourceCatalog:
    return SourceCatalog()


def test_catalog_exposes_both_sources(catalog: SourceCatalog) -> None:
    assert len(catalog.indicators) == 48
    assert {item.provenance.source_id for item in catalog.indicators} == {
        SourceId.FINNISH_CANCER_REGISTRY,
        SourceId.NORDCAN,
    }


def test_search_can_be_scoped_to_nordcan_denmark(catalog: SourceCatalog) -> None:
    result = catalog.search_indicators(
        "female Denmark lung mortality",
        source="nordcan",
        geography="Denmark",
    )

    assert result.count == 5
    assert all(match.indicator.provenance.source_id is SourceId.NORDCAN for match in result.matches)


def test_overlapping_finland_crude_rates_are_cross_source_ambiguous(
    catalog: SourceCatalog,
) -> None:
    with pytest.raises(AmbiguousIndicatorError) as raised:
        catalog.get_latest_observation(query="female Finland lung mortality crude")

    candidates = raised.value.details["candidates"]
    assert len(candidates) == 2
    assert {candidate["source"] for candidate in candidates} == {
        "finnish_cancer_registry",
        "nordcan",
    }


def test_source_filter_resolves_overlapping_finland_rate(
    catalog: SourceCatalog,
) -> None:
    result = catalog.get_latest_observation(
        query="female Finland lung mortality crude",
        source="nordcan",
    )

    assert result.observation.value == 29.9
    assert result.observation.provenance.source_id is SourceId.NORDCAN


def test_exact_identifier_routes_to_owning_adapter(catalog: SourceCatalog) -> None:
    result = catalog.get_observations(indicator_id="fcr.lung_trachea.mortality.crude.female")

    assert result.count == 1
    assert result.indicator.provenance.source_id is SourceId.FINNISH_CANCER_REGISTRY


def test_unknown_identifier_is_actionable(catalog: SourceCatalog) -> None:
    with pytest.raises(IndicatorNotFoundError, match="unknown indicator_id"):
        catalog.get_latest_observation(indicator_id="nordcan.not_real")


def test_catalog_rejects_invalid_adapter_configuration() -> None:
    with pytest.raises(ValueError, match="at least one"):
        SourceCatalog([])
    with pytest.raises(SourceDataError, match="same source identifier"):
        SourceCatalog(
            [
                FinnishCancerRegistryAdapter(),
                FinnishCancerRegistryAdapter(),
            ]
        )

    duplicate_ids = FinnishCancerRegistryAdapter()
    duplicate_ids.source_id = SourceId.NORDCAN
    with pytest.raises(SourceDataError, match="duplicated across sources"):
        SourceCatalog([FinnishCancerRegistryAdapter(), duplicate_ids])
