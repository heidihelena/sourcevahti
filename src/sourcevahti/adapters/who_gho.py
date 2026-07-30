"""Adapter for a frozen WHO Global Health Observatory tobacco-use snapshot."""

from __future__ import annotations

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
    "country_code",
    "country",
    "sex_code",
    "sex",
    "year",
    "value",
    "lower_bound",
    "upper_bound",
    "status",
    "note",
    "updated_at",
}
_SOURCE_URL = "https://ghoapi.azureedge.net/api/M_Est_tob_curr_std"
_CITATION_URL = (
    "https://www.who.int/data/gho/indicator-metadata-registry/imr-details/"
    "prevalence-of-current-tobacco-use-among-persons-aged-15-years-and-older-"
    "age-standardized"
)
_INDICATOR_DEFINITION = (
    "Percentage of people aged 15 years and over who currently use any tobacco "
    "product, daily or non-daily, age-standardised to the WHO standard population."
)


class WhoGhoAdapter(SnapshotAdapter):
    """Parse WHO modelled tobacco-use estimates for Nordic countries."""

    source_id = SourceId.WHO_GHO
    source_name = "WHO Global Health Observatory"
    dataset_title = "Estimate of current tobacco use prevalence (%) (age-standardized)"
    snapshot_resource = "who_gho_tobacco_use_2026_01_15.csv"

    def __init__(self, data_path: Path | None = None) -> None:
        super().__init__(data_path)

    def _load_rows(self) -> list[LoadedRow]:
        rows = self._read_snapshot(_REQUIRED_COLUMNS)
        loaded_rows: list[LoadedRow] = []
        for row_number, row in enumerate(rows, start=2):
            try:
                country_slug = row["country"].casefold().replace(" ", "_")
                sex = Sex(row["sex"])
                status = ObservationStatus(row["status"])
                update_date = date.fromisoformat(row["updated_at"][:10])
                provenance = Provenance.model_validate(
                    {
                        "source_id": self.source_id,
                        "source_name": self.source_name,
                        "dataset_title": self.dataset_title,
                        "source_url": _SOURCE_URL,
                        "citation_url": _CITATION_URL,
                        "source_release_version": f"GHO API {update_date.isoformat()}",
                        "source_release_date": update_date,
                        "retrieval_date": date(2026, 7, 30),
                        "snapshot_id": "who-gho-tobacco-use-nordic-20260115-20260730",
                        "license_note": (
                            "WHO data retain WHO terms and attribution; Apache-2.0 "
                            "covers SourceVahti code only."
                        ),
                    }
                )
                indicator_id = (
                    f"who_gho.tobacco.current_use.age_standardised.{sex.value}.{country_slug}"
                )
                note = row["note"].strip() or None
                observation = Observation(
                    indicator_id=indicator_id,
                    year=int(row["year"]),
                    value=float(row["value"]),
                    lower_bound=float(row["lower_bound"]),
                    upper_bound=float(row["upper_bound"]),
                    note=note,
                    measure=Measure.TOBACCO_USE_PREVALENCE,
                    source_indicator_code=(
                        "M_Est_tob_curr_std;"
                        f"SpatialDim={row['country_code']};Dim1={row['sex_code']}"
                    ),
                    health_topic="Tobacco use",
                    indicator_definition=_INDICATOR_DEFINITION,
                    unit=Unit.PERCENT,
                    sex=sex,
                    geography=row["country"],
                    age_group="15 years and over",
                    rate_type=RateType.AGE_STANDARDISED_WHO,
                    standard_population="WHO standard population",
                    observation_status=status,
                    provenance=provenance,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise SourceDataError(
                    "invalid row in WHO GHO snapshot",
                    details={"row": row_number, "reason": str(exc)},
                ) from exc
            loaded_rows.append(
                LoadedRow(
                    observation=observation,
                    indicator_name=(
                        f"Current tobacco use prevalence — {sex.value} — {row['country']}"
                    ),
                    indicator_description=(
                        "WHO age-standardised modelled estimate with a 95% "
                        "uncertainty interval. Contextual risk-factor data; it is "
                        "not an outcome measure or a causal estimate."
                    ),
                    row_number=row_number,
                )
            )
        return loaded_rows
