"""Shared contracts for deterministic, source-specific snapshot adapters."""

from __future__ import annotations

import csv
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import IO

from sourcevahti.errors import (
    AmbiguousIndicatorError,
    IndicatorNotFoundError,
    InputValidationError,
    SourceDataError,
)
from sourcevahti.models import (
    Indicator,
    IndicatorMatch,
    IndicatorSearchResponse,
    LatestObservationResponse,
    Observation,
    ObservationResponse,
    RateType,
    Sex,
    SourceId,
    Unit,
)
from sourcevahti.validators import (
    QueryConstraints,
    constrain_query,
    validate_geography,
    validate_rate_type,
    validate_sex,
    validate_source,
    validate_unit,
    validate_year_range,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SEARCH_ALIASES = {
    "death": {"death", "deaths", "mortality"},
    "deaths": {"death", "deaths", "mortality"},
    "mortality": {"death", "deaths", "mortality"},
    "female": {"female", "women", "woman"},
    "women": {"female", "women", "woman"},
    "woman": {"female", "women", "woman"},
    "lung": {"lung", "trachea", "c33", "c34"},
    "standardised": {"standardised", "standardized", "asr"},
    "standardized": {"standardised", "standardized", "asr"},
}


@dataclass(frozen=True)
class LoadedRow:
    """One parsed source row plus stable indicator metadata."""

    observation: Observation
    indicator_name: str
    indicator_description: str
    row_number: int


class SnapshotAdapter(ABC):
    """Search and resolve observations parsed by one source-specific adapter."""

    source_id: SourceId
    source_name: str
    dataset_title: str
    snapshot_resource: str

    def __init__(self, data_path: Path | None = None) -> None:
        self._data_path = data_path
        loaded_rows = self._load_rows()
        if not loaded_rows:
            raise SourceDataError(f"{self.source_name} snapshot contains no rows")
        self._reject_duplicate_observations(loaded_rows)

        rows_by_indicator: dict[str, list[LoadedRow]] = defaultdict(list)
        for loaded_row in loaded_rows:
            rows_by_indicator[loaded_row.observation.indicator_id].append(loaded_row)
        for series in rows_by_indicator.values():
            series.sort(key=lambda item: item.observation.year)

        self._loaded_rows_by_indicator = dict(rows_by_indicator)
        self._observations_by_indicator = {
            indicator_id: [item.observation for item in series]
            for indicator_id, series in rows_by_indicator.items()
        }
        self._indicators = {
            indicator_id: self._make_indicator(series)
            for indicator_id, series in rows_by_indicator.items()
        }

    @abstractmethod
    def _load_rows(self) -> list[LoadedRow]:
        """Parse and normalise the adapter's frozen source response."""

    @property
    def indicators(self) -> tuple[Indicator, ...]:
        """Return all precisely defined indicators in stable identifier order."""
        return tuple(self._indicators[key] for key in sorted(self._indicators))

    def search_indicators(
        self,
        query: str,
        *,
        source: str | SourceId | None = None,
        geography: str | None = None,
        sex: str | Sex | None = None,
        unit: str | Unit | None = None,
        limit: int = 10,
    ) -> IndicatorSearchResponse:
        """Search without silently selecting material statistical dimensions."""
        constraints = constrain_query(
            query,
            source=source,
            geography=geography,
            sex=sex,
            unit=unit,
        )
        self._validate_limit(limit)
        if constraints.source_id is not None and constraints.source_id is not self.source_id:
            return IndicatorSearchResponse(query=constraints.query, count=0, matches=[])

        matches: list[IndicatorMatch] = []
        for indicator in self.indicators:
            if not self._matches_constraints(indicator, constraints):
                continue
            score, matched_terms = self._score(constraints.query, indicator)
            if score > 0:
                matches.append(
                    IndicatorMatch(
                        indicator=indicator,
                        score=score,
                        matched_terms=matched_terms,
                    )
                )
        matches.sort(key=lambda item: (-item.score, item.indicator.indicator_id))
        limited = matches[:limit]
        return IndicatorSearchResponse(
            query=constraints.query,
            count=len(limited),
            matches=limited,
        )

    def get_observations(
        self,
        *,
        indicator_id: str | None = None,
        query: str | None = None,
        source: str | SourceId | None = None,
        geography: str | None = None,
        sex: str | Sex | None = None,
        unit: str | Unit | None = None,
        rate_type: str | RateType | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> ObservationResponse:
        """Resolve one indicator and return observations in ascending year order."""
        start_year, end_year = validate_year_range(start_year, end_year)
        indicator = self._resolve_indicator(
            indicator_id=indicator_id,
            query=query,
            source=source,
            geography=geography,
            sex=sex,
            unit=unit,
            rate_type=rate_type,
        )
        observations = [
            item
            for item in self._observations_by_indicator[indicator.indicator_id]
            if (start_year is None or item.year >= start_year)
            and (end_year is None or item.year <= end_year)
        ]
        return ObservationResponse(
            indicator=indicator,
            count=len(observations),
            observations=observations,
        )

    def get_latest_observation(
        self,
        *,
        indicator_id: str | None = None,
        query: str | None = None,
        source: str | SourceId | None = None,
        geography: str | None = None,
        sex: str | Sex | None = None,
        unit: str | Unit | None = None,
        rate_type: str | RateType | None = None,
    ) -> LatestObservationResponse:
        """Resolve one indicator and return its latest available observation."""
        indicator = self._resolve_indicator(
            indicator_id=indicator_id,
            query=query,
            source=source,
            geography=geography,
            sex=sex,
            unit=unit,
            rate_type=rate_type,
        )
        observation = self._observations_by_indicator[indicator.indicator_id][-1]
        return LatestObservationResponse(indicator=indicator, observation=observation)

    def has_indicator(self, indicator_id: str) -> bool:
        """Return whether this source owns an exact indicator identifier."""
        return indicator_id in self._indicators

    @contextmanager
    def _open_snapshot(self) -> Iterator[IO[str]]:
        if self._data_path is not None:
            with self._data_path.open(encoding="utf-8", newline="") as handle:
                yield handle
            return
        snapshot = resources.files("sourcevahti").joinpath(f"data/{self.snapshot_resource}")
        with snapshot.open(encoding="utf-8") as handle:
            yield handle

    def _read_snapshot(self, required_columns: set[str]) -> list[dict[str, str]]:
        try:
            with self._open_snapshot() as handle:
                reader = csv.DictReader(handle)
                columns = set(reader.fieldnames or ())
                missing = sorted(required_columns - columns)
                if missing:
                    raise SourceDataError(
                        f"{self.source_name} snapshot is missing required columns",
                        details={"missing_columns": missing},
                    )
                return list(reader)
        except OSError as exc:
            raise SourceDataError(
                f"could not read {self.source_name} snapshot",
                details={"path": str(self._data_path) if self._data_path else "bundled"},
            ) from exc

    def _resolve_indicator(
        self,
        *,
        indicator_id: str | None,
        query: str | None,
        source: str | SourceId | None,
        geography: str | None,
        sex: str | Sex | None,
        unit: str | Unit | None,
        rate_type: str | RateType | None,
    ) -> Indicator:
        constraints = self._constraints_for_resolution(
            query=query,
            source=source,
            geography=geography,
            sex=sex,
            unit=unit,
            rate_type=rate_type,
        )

        if indicator_id:
            try:
                indicator = self._indicators[indicator_id]
            except KeyError as exc:
                raise IndicatorNotFoundError(
                    f"unknown indicator_id {indicator_id!r}",
                    details={"indicator_id": indicator_id},
                    hint="Call search_indicators to discover valid identifiers.",
                ) from exc
            mismatches = self._constraint_mismatches(indicator, constraints)
            if mismatches:
                raise InputValidationError(
                    "indicator_id conflicts with supplied dimensions",
                    details={"indicator_id": indicator_id, "conflicts": mismatches},
                )
            return indicator

        if not query:
            raise InputValidationError(
                "provide indicator_id or query",
                details={"required_any_of": ["indicator_id", "query"]},
            )

        search = self.search_indicators(
            constraints.query,
            source=constraints.source_id,
            geography=constraints.geography,
            sex=constraints.sex,
            unit=constraints.unit,
            limit=50,
        )
        candidates = [
            match.indicator
            for match in search.matches
            if constraints.rate_types is None or match.indicator.rate_type in constraints.rate_types
        ]
        if not candidates:
            raise IndicatorNotFoundError(
                "no indicator matched the requested definition",
                details=self._constraint_details(constraints),
                hint="Call search_indicators with a broader cancer-site query.",
            )
        if len(candidates) > 1:
            raise self._ambiguity_error(candidates)
        return candidates[0]

    def _constraints_for_resolution(
        self,
        *,
        query: str | None,
        source: str | SourceId | None,
        geography: str | None,
        sex: str | Sex | None,
        unit: str | Unit | None,
        rate_type: str | RateType | None,
    ) -> QueryConstraints:
        if query:
            return constrain_query(
                query,
                source=source,
                geography=geography,
                sex=sex,
                unit=unit,
                rate_type=rate_type,
            )
        validated_rate_type = validate_rate_type(rate_type)
        return QueryConstraints(
            query="",
            source_id=validate_source(source),
            geography=validate_geography(geography),
            sex=validate_sex(sex),
            unit=validate_unit(unit),
            rate_types=(
                frozenset({validated_rate_type}) if validated_rate_type is not None else None
            ),
        )

    @staticmethod
    def _matches_constraints(
        indicator: Indicator,
        constraints: QueryConstraints,
    ) -> bool:
        return not (
            (
                constraints.source_id is not None
                and indicator.provenance.source_id is not constraints.source_id
            )
            or (constraints.sex is not None and indicator.sex is not constraints.sex)
            or (constraints.unit is not None and indicator.unit is not constraints.unit)
            or (
                constraints.geography is not None
                and indicator.geography.casefold() != constraints.geography.casefold()
            )
            or (
                constraints.rate_types is not None
                and indicator.rate_type not in constraints.rate_types
            )
        )

    @staticmethod
    def _constraint_mismatches(
        indicator: Indicator,
        constraints: QueryConstraints,
    ) -> dict[str, object]:
        mismatches: dict[str, object] = {}
        if (
            constraints.source_id is not None
            and indicator.provenance.source_id is not constraints.source_id
        ):
            mismatches["source"] = constraints.source_id.value
        if constraints.sex is not None and indicator.sex is not constraints.sex:
            mismatches["sex"] = constraints.sex.value
        if constraints.unit is not None and indicator.unit is not constraints.unit:
            mismatches["unit"] = constraints.unit.value
        if (
            constraints.geography is not None
            and indicator.geography.casefold() != constraints.geography.casefold()
        ):
            mismatches["geography"] = constraints.geography
        if constraints.rate_types is not None and indicator.rate_type not in constraints.rate_types:
            mismatches["rate_type"] = sorted(value.value for value in constraints.rate_types)
        return mismatches

    @staticmethod
    def _constraint_details(constraints: QueryConstraints) -> dict[str, object]:
        return {
            "query": constraints.query,
            "source": constraints.source_id.value if constraints.source_id else None,
            "geography": constraints.geography,
            "sex": constraints.sex.value if constraints.sex else None,
            "unit": constraints.unit.value if constraints.unit else None,
            "rate_types": (
                sorted(value.value for value in constraints.rate_types)
                if constraints.rate_types
                else None
            ),
        }

    @staticmethod
    def _ambiguity_error(candidates: list[Indicator]) -> AmbiguousIndicatorError:
        return AmbiguousIndicatorError(
            "multiple statistical definitions match the request",
            candidates=[
                {
                    "indicator_id": candidate.indicator_id,
                    "source": candidate.provenance.source_id.value,
                    "geography": candidate.geography,
                    "rate_type": candidate.rate_type.value,
                    "standard_population": candidate.standard_population,
                    "unit": candidate.unit.value,
                }
                for candidate in candidates
            ],
        )

    def _reject_duplicate_observations(self, loaded_rows: list[LoadedRow]) -> None:
        seen: dict[tuple[str, int], int] = {}
        for loaded_row in loaded_rows:
            observation = loaded_row.observation
            key = (observation.indicator_id, observation.year)
            if first_row := seen.get(key):
                raise SourceDataError(
                    f"duplicate observation in {self.source_name} snapshot",
                    details={
                        "indicator_id": observation.indicator_id,
                        "year": observation.year,
                        "rows": [first_row, loaded_row.row_number],
                    },
                )
            seen[key] = loaded_row.row_number

    def _make_indicator(self, series: list[LoadedRow]) -> Indicator:
        first_loaded = series[0]
        first = first_loaded.observation
        expected = self._indicator_contract(first_loaded)
        if any(self._indicator_contract(item) != expected for item in series[1:]):
            raise SourceDataError(
                "indicator contains inconsistent dimensions or metadata",
                details={"indicator_id": first.indicator_id},
            )

        latest = series[-1].observation
        return Indicator(
            indicator_id=first.indicator_id,
            name=first_loaded.indicator_name,
            description=first_loaded.indicator_description,
            measure=first.measure,
            source_indicator_code=first.source_indicator_code,
            cancer_site=first.cancer_site,
            cancer_definition=first.cancer_definition,
            sex=first.sex,
            geography=first.geography,
            age_group=first.age_group,
            unit=first.unit,
            rate_type=first.rate_type,
            standard_population=first.standard_population,
            observation_status=first.observation_status,
            first_year=first.year,
            latest_year=latest.year,
            provenance=latest.provenance,
        )

    @staticmethod
    def _indicator_contract(loaded_row: LoadedRow) -> tuple[object, ...]:
        item = loaded_row.observation
        provenance = item.provenance
        return (
            loaded_row.indicator_name,
            loaded_row.indicator_description,
            item.measure,
            item.source_indicator_code,
            item.unit,
            item.sex,
            item.geography,
            item.age_group,
            item.cancer_site,
            item.cancer_definition,
            item.rate_type,
            item.standard_population,
            item.observation_status,
            provenance.source_id,
            provenance.source_name,
            provenance.dataset_title,
            provenance.source_release_version,
            provenance.source_release_date,
            provenance.retrieval_date,
            provenance.snapshot_id,
            provenance.license_note,
        )

    @staticmethod
    def _score(query: str, indicator: Indicator) -> tuple[float, list[str]]:
        query_tokens = _TOKEN_RE.findall(query.casefold())
        blob = " ".join(
            (
                indicator.indicator_id,
                indicator.name,
                indicator.description,
                indicator.measure.value,
                indicator.source_indicator_code,
                indicator.provenance.source_id.value,
                indicator.provenance.source_name,
                indicator.cancer_site,
                indicator.cancer_definition,
                indicator.sex.value,
                indicator.geography,
                indicator.age_group,
                indicator.unit.value,
                indicator.rate_type.value,
                indicator.standard_population or "",
                "cancer rate per 100000 asr",
            )
        ).casefold()
        blob_tokens = set(_TOKEN_RE.findall(blob))

        matched: list[str] = []
        for token in dict.fromkeys(query_tokens):
            aliases = _SEARCH_ALIASES.get(token, {token})
            if aliases & blob_tokens:
                matched.append(token)
        if not matched:
            return 0.0, []
        score = len(matched) / len(set(query_tokens))
        return round(score, 4), matched

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if not 1 <= limit <= 50:
            raise InputValidationError(
                "limit must be between 1 and 50",
                details={"field": "limit", "value": limit},
            )
