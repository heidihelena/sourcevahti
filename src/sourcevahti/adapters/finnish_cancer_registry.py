"""Adapter for a frozen Finnish Cancer Registry statistical-app export."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path

from sourcevahti.adapters.base import LoadedRow, SnapshotAdapter
from sourcevahti.errors import SourceDataError
from sourcevahti.models import (
    Measure,
    Observation,
    ObservationStatus,
    Provenance,
    RateType,
    Sex,
    SourceId,
    Unit,
)

_REQUIRED_COLUMNS = {
    "indicator_id",
    "indicator_name",
    "indicator_description",
    "cancer_site",
    "cancer_definition",
    "sex",
    "geography",
    "year",
    "value",
    "unit",
    "rate_type",
    "standard_population",
    "source_url",
    "citation_url",
    "source_release_date",
    "retrieval_date",
    "snapshot_id",
    "license_note",
}
_SOURCE_VALUE_TYPES = {
    RateType.CRUDE: "mort.rate",
    RateType.AGE_STANDARDISED_WORLD_1966: "mort.rate_world_1966",
    RateType.AGE_STANDARDISED_FINLAND_2014: "mort.rate_finland_2014",
}


class FinnishCancerRegistryAdapter(SnapshotAdapter):
    """Parse and normalise the Finnish Cancer Registry snapshot."""

    source_id = SourceId.FINNISH_CANCER_REGISTRY
    source_name = "Finnish Cancer Registry"
    dataset_title = "Cancer statistics: deaths due to cancer"
    snapshot_resource = "finnish_cancer_registry_2024.csv"

    def __init__(self, data_path: Path | None = None) -> None:
        super().__init__(data_path)

    def _load_rows(self) -> list[LoadedRow]:
        rows = self._read_snapshot(_REQUIRED_COLUMNS)
        loaded_rows: list[LoadedRow] = []
        for row_number, row in enumerate(rows, start=2):
            try:
                provenance = Provenance.model_validate(
                    {
                        "source_id": self.source_id,
                        "source_name": self.source_name,
                        "dataset_title": self.dataset_title,
                        "source_url": row["source_url"],
                        "citation_url": row["citation_url"],
                        "source_release_version": "2024 statistical release",
                        "source_release_date": date.fromisoformat(row["source_release_date"]),
                        "retrieval_date": date.fromisoformat(row["retrieval_date"]),
                        "snapshot_id": row["snapshot_id"],
                        "license_note": row["license_note"],
                    }
                )
                rate_type = RateType(row["rate_type"])
                observation = Observation(
                    indicator_id=row["indicator_id"],
                    year=int(row["year"]),
                    value=float(row["value"]),
                    measure=Measure.CANCER_MORTALITY_RATE,
                    source_indicator_code=(
                        f"site=21L;value_type={_SOURCE_VALUE_TYPES[rate_type]};sex=1L"
                    ),
                    unit=Unit(row["unit"]),
                    sex=Sex(row["sex"]),
                    geography=row["geography"],
                    age_group="All ages",
                    cancer_site=row["cancer_site"],
                    cancer_definition=row["cancer_definition"],
                    rate_type=rate_type,
                    standard_population=row["standard_population"] or None,
                    observation_status=ObservationStatus.OBSERVED,
                    provenance=provenance,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise SourceDataError(
                    "invalid row in Finnish Cancer Registry snapshot",
                    details={"row": row_number, "reason": str(exc)},
                ) from exc
            loaded_rows.append(
                LoadedRow(
                    observation=observation,
                    indicator_name=row["indicator_name"],
                    indicator_description=row["indicator_description"],
                    row_number=row_number,
                )
            )
        return loaded_rows


def iter_observations(
    adapter: FinnishCancerRegistryAdapter,
) -> Iterable[Observation]:
    """Yield all observations for maintenance checks and test diagnostics."""
    for indicator in adapter.indicators:
        yield from adapter.get_observations(indicator_id=indicator.indicator_id).observations
