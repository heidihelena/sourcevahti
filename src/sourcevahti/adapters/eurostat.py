"""Adapter for a frozen Eurostat lung-cancer mortality snapshot."""

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
    "status_flag",
    "note",
    "updated_at",
}
_SOURCE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/HLTH_CD_ASDR2"
_CITATION_URL = "https://ec.europa.eu/eurostat/cache/metadata/en/hlth_cdeath_sims.htm"
_CANCER_DEFINITION = (
    "Malignant neoplasm of trachea, bronchus and lung (Eurostat code C33_C34; ICD-10 C33-C34)"
)


class EurostatAdapter(SnapshotAdapter):
    """Parse Eurostat standardised death rates for Nordic countries."""

    source_id = SourceId.EUROSTAT
    source_name = "Eurostat"
    dataset_title = "Causes of death — standardised death rate (HLTH_CD_ASDR2)"
    snapshot_resource = "eurostat_lung_mortality_2026_06_08.csv"

    def __init__(self, data_path: Path | None = None) -> None:
        super().__init__(data_path)

    def _load_rows(self) -> list[LoadedRow]:
        rows = self._read_snapshot(_REQUIRED_COLUMNS)
        loaded_rows: list[LoadedRow] = []
        for row_number, row in enumerate(rows, start=2):
            try:
                country_slug = row["country"].casefold().replace(" ", "_")
                sex = Sex(row["sex"])
                update_date = date.fromisoformat(row["updated_at"][:10])
                provenance = Provenance.model_validate(
                    {
                        "source_id": self.source_id,
                        "source_name": self.source_name,
                        "dataset_title": self.dataset_title,
                        "source_url": _SOURCE_URL,
                        "citation_url": _CITATION_URL,
                        "source_release_version": (f"HLTH_CD_ASDR2 {update_date.isoformat()}"),
                        "source_release_date": update_date,
                        "retrieval_date": date(2026, 7, 30),
                        "snapshot_id": ("eurostat-hlth-cd-asdr2-lung-nordic-20260608-20260730"),
                        "license_note": (
                            "Eurostat data retain Eurostat terms and attribution; "
                            "Apache-2.0 covers SourceVahti code only."
                        ),
                    }
                )
                indicator_id = f"eurostat.lung.mortality.asr_europe_2013.{sex.value}.{country_slug}"
                note = row["note"].strip() or None
                observation = Observation(
                    indicator_id=indicator_id,
                    year=int(row["year"]),
                    value=float(row["value"]),
                    note=note,
                    measure=Measure.CANCER_MORTALITY_RATE,
                    source_indicator_code=(
                        "HLTH_CD_ASDR2;unit=RT;age=TOTAL;icd10=C33_C34;"
                        f"geo={row['country_code']};sex={row['sex_code']}"
                    ),
                    health_topic="Lung cancer",
                    indicator_definition=(
                        "Underlying-cause deaths among residents, standardised by "
                        "the direct method for comparison across populations."
                    ),
                    cancer_site="Lung, trachea and bronchus",
                    cancer_definition=_CANCER_DEFINITION,
                    unit=Unit.PER_100_000_PERSON_YEARS,
                    sex=sex,
                    geography=row["country"],
                    age_group="All ages",
                    rate_type=RateType.AGE_STANDARDISED_EUROPE_2013,
                    standard_population="European Standard Population 2013",
                    observation_status=ObservationStatus.OBSERVED,
                    provenance=provenance,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise SourceDataError(
                    "invalid row in Eurostat snapshot",
                    details={"row": row_number, "reason": str(exc)},
                ) from exc
            loaded_rows.append(
                LoadedRow(
                    observation=observation,
                    indicator_name=(
                        f"Lung-cancer mortality rate — European 2013 — "
                        f"{sex.value} — {row['country']}"
                    ),
                    indicator_description=(
                        "Eurostat resident underlying-cause mortality, directly "
                        "standardised to the European Standard Population 2013."
                    ),
                    row_number=row_number,
                )
            )
        return loaded_rows
