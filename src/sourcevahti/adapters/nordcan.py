"""Adapter for frozen NORDCAN 9.6 table outputs."""

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
    "geography",
    "geography_code",
    "year",
    "asr_world",
    "asr_nordic_2000",
    "asr_europe_1976",
    "asr_europe_2013",
    "crude",
}
_RATE_COLUMNS: dict[str, tuple[str, RateType, str | None, str]] = {
    "crude": (
        "crude",
        RateType.CRUDE,
        None,
        "without age standardisation",
    ),
    "asr_world": (
        "asr_world",
        RateType.AGE_STANDARDISED_WORLD,
        "World standard population",
        "using the World standard population",
    ),
    "asr_nordic_2000": (
        "asr_nordic_2000",
        RateType.AGE_STANDARDISED_NORDIC_2000,
        "NORDCAN population 2000",
        "using the NORDCAN population in 2000",
    ),
    "asr_europe_1976": (
        "asr_europe_1976",
        RateType.AGE_STANDARDISED_EUROPE_1976,
        "European standard population 1976",
        "using the European standard population 1976",
    ),
    "asr_europe_2013": (
        "asr_europe_2013",
        RateType.AGE_STANDARDISED_EUROPE_2013,
        "European standard population 2013",
        "using the European standard population 2013",
    ),
}
_SOURCE_URL = "https://nordcan.iarc.fr/en/database"
_CITATION_URL = (
    "https://nordcan.iarc.fr/en/dataviz/tables"
    "?age_start=0&cancers=160&multiple_populations=0&populations=246"
    "&sexes=2&types=1&years={year}"
)


class NordcanAdapter(SnapshotAdapter):
    """Parse NORDCAN's wide table export into explicit rate series."""

    source_id = SourceId.NORDCAN
    source_name = "NORDCAN"
    dataset_title = "Cancer Incidence, Mortality, Prevalence and Survival in the Nordic Countries"
    snapshot_resource = "nordcan_lung_mortality_9_6.csv"

    def __init__(self, data_path: Path | None = None) -> None:
        super().__init__(data_path)

    def _load_rows(self) -> list[LoadedRow]:
        rows = self._read_snapshot(_REQUIRED_COLUMNS)
        loaded_rows: list[LoadedRow] = []
        for row_number, row in enumerate(rows, start=2):
            try:
                year = int(row["year"])
                geography = row["geography"]
                geography_code = row["geography_code"]
                provenance = Provenance.model_validate(
                    {
                        "source_id": self.source_id,
                        "source_name": self.source_name,
                        "dataset_title": self.dataset_title,
                        "source_url": _SOURCE_URL,
                        "citation_url": _CITATION_URL.format(year=year),
                        "source_release_version": "9.6",
                        "source_release_date": date(2026, 6, 30),
                        "retrieval_date": date(2026, 7, 30),
                        "snapshot_id": ("nordcan-9.6-lung-mortality-female-20260730"),
                        "license_note": (
                            "NORDCAN tabulated statistics are freely available for "
                            "use with the recommended citation; IARC terms apply."
                        ),
                    }
                )
                for column, (
                    indicator_suffix,
                    rate_type,
                    standard_population,
                    definition,
                ) in _RATE_COLUMNS.items():
                    indicator_id = (
                        f"nordcan.lung.mortality.{indicator_suffix}.female.{geography_code}"
                    )
                    loaded_rows.append(
                        LoadedRow(
                            observation=Observation(
                                indicator_id=indicator_id,
                                year=year,
                                value=float(row[column]),
                                measure=Measure.CANCER_MORTALITY_RATE,
                                source_indicator_code=(
                                    "type=1;cancer=160;sex=2;"
                                    f"geography={geography_code};statistic={column}"
                                ),
                                health_topic="Lung cancer",
                                indicator_definition=(
                                    "Deaths from malignant neoplasms of the trachea, "
                                    "bronchus and lung in the published population."
                                ),
                                unit=Unit.PER_100_000_PERSON_YEARS,
                                sex=Sex.FEMALE,
                                geography=geography,
                                age_group="All ages (0-85+)",
                                cancer_site="Lung",
                                cancer_definition=(
                                    "Lung cancer (NORDCAN entity 160; ICD-10 C33-C34)"
                                ),
                                rate_type=rate_type,
                                standard_population=standard_population,
                                observation_status=ObservationStatus.OBSERVED,
                                provenance=provenance,
                            ),
                            indicator_name=(
                                f"Female lung cancer mortality rate — "
                                f"{rate_type.value} — {geography}"
                            ),
                            indicator_description=(
                                f"Observed female lung-cancer mortality {definition}."
                            ),
                            row_number=row_number,
                        )
                    )
            except (KeyError, TypeError, ValueError) as exc:
                raise SourceDataError(
                    "invalid row in NORDCAN snapshot",
                    details={"row": row_number, "reason": str(exc)},
                ) from exc
        return loaded_rows
