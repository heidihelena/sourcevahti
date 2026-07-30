"""Multi-source routing with cross-source ambiguity protection."""

from __future__ import annotations

from collections.abc import Iterable

from sourcevahti.adapters import FinnishCancerRegistryAdapter, NordcanAdapter
from sourcevahti.adapters.base import SnapshotAdapter
from sourcevahti.errors import (
    IndicatorNotFoundError,
    InputValidationError,
    SourceDataError,
)
from sourcevahti.models import (
    Indicator,
    IndicatorSearchResponse,
    LatestObservationResponse,
    ObservationResponse,
    RateType,
    Sex,
    SourceId,
    Unit,
)
from sourcevahti.validators import QueryConstraints, constrain_query


class SourceCatalog:
    """Aggregate source adapters without collapsing distinct definitions."""

    def __init__(self, adapters: Iterable[SnapshotAdapter] | None = None) -> None:
        configured = tuple(
            adapters if adapters is not None else (FinnishCancerRegistryAdapter(), NordcanAdapter())
        )
        if not configured:
            raise ValueError("SourceCatalog requires at least one adapter")

        by_source: dict[SourceId, SnapshotAdapter] = {}
        indicator_owners: dict[str, SnapshotAdapter] = {}
        for adapter in configured:
            if adapter.source_id in by_source:
                raise SourceDataError(
                    "multiple adapters use the same source identifier",
                    details={"source": adapter.source_id.value},
                )
            by_source[adapter.source_id] = adapter
            for indicator in adapter.indicators:
                if indicator.indicator_id in indicator_owners:
                    raise SourceDataError(
                        "indicator identifier is duplicated across sources",
                        details={"indicator_id": indicator.indicator_id},
                    )
                indicator_owners[indicator.indicator_id] = adapter

        self._adapters = configured
        self._by_source = by_source
        self._indicator_owners = indicator_owners

    @property
    def indicators(self) -> tuple[Indicator, ...]:
        """Return all source indicators in stable identifier order."""
        return tuple(
            sorted(
                (indicator for adapter in self._adapters for indicator in adapter.indicators),
                key=lambda indicator: indicator.indicator_id,
            )
        )

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
        """Search all requested sources and rank their matches together."""
        constraints = constrain_query(
            query,
            source=source,
            geography=geography,
            sex=sex,
            unit=unit,
        )
        SnapshotAdapter._validate_limit(limit)

        matches = []
        for adapter in self._adapters:
            if constraints.source_id is not None and adapter.source_id is not constraints.source_id:
                continue
            result = adapter.search_indicators(
                constraints.query,
                source=constraints.source_id,
                geography=constraints.geography,
                sex=constraints.sex,
                unit=constraints.unit,
                limit=50,
            )
            matches.extend(result.matches)
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
        """Resolve within or across sources and return one observation series."""
        if indicator_id:
            adapter = self._adapter_for_indicator(indicator_id)
            return adapter.get_observations(
                indicator_id=indicator_id,
                query=query,
                source=source,
                geography=geography,
                sex=sex,
                unit=unit,
                rate_type=rate_type,
                start_year=start_year,
                end_year=end_year,
            )

        adapter, indicator = self._resolve_query(
            query=query,
            source=source,
            geography=geography,
            sex=sex,
            unit=unit,
            rate_type=rate_type,
        )
        return adapter.get_observations(
            indicator_id=indicator.indicator_id,
            start_year=start_year,
            end_year=end_year,
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
        """Resolve within or across sources and return the latest observation."""
        if indicator_id:
            adapter = self._adapter_for_indicator(indicator_id)
            return adapter.get_latest_observation(
                indicator_id=indicator_id,
                query=query,
                source=source,
                geography=geography,
                sex=sex,
                unit=unit,
                rate_type=rate_type,
            )

        adapter, indicator = self._resolve_query(
            query=query,
            source=source,
            geography=geography,
            sex=sex,
            unit=unit,
            rate_type=rate_type,
        )
        return adapter.get_latest_observation(indicator_id=indicator.indicator_id)

    def _resolve_query(
        self,
        *,
        query: str | None,
        source: str | SourceId | None,
        geography: str | None,
        sex: str | Sex | None,
        unit: str | Unit | None,
        rate_type: str | RateType | None,
    ) -> tuple[SnapshotAdapter, Indicator]:
        if not query:
            raise InputValidationError(
                "provide indicator_id or query",
                details={"required_any_of": ["indicator_id", "query"]},
            )
        constraints = constrain_query(
            query,
            source=source,
            geography=geography,
            sex=sex,
            unit=unit,
            rate_type=rate_type,
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
                hint="Call search_indicators with a broader query or another source.",
            )
        if len(candidates) > 1:
            raise SnapshotAdapter._ambiguity_error(candidates)
        indicator = candidates[0]
        return self._indicator_owners[indicator.indicator_id], indicator

    def _adapter_for_indicator(self, indicator_id: str) -> SnapshotAdapter:
        try:
            return self._indicator_owners[indicator_id]
        except KeyError as exc:
            raise IndicatorNotFoundError(
                f"unknown indicator_id {indicator_id!r}",
                details={"indicator_id": indicator_id},
                hint="Call search_indicators to discover valid identifiers.",
            ) from exc

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
