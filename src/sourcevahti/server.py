"""SourceVahti MCP server with local stdio transport."""

from __future__ import annotations

from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from sourcevahti.catalog import SourceCatalog
from sourcevahti.models import (
    IndicatorSearchResponse,
    LatestObservationResponse,
    ObservationResponse,
)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def create_server(
    catalog: SourceCatalog | None = None,
) -> MCPServer:
    """Create a server, optionally injecting a source catalog for tests."""
    registry = catalog or SourceCatalog()
    server = MCPServer(
        "SourceVahti",
        instructions=(
            "Retrieve precisely defined public-health indicators across sources. "
            "Treat source, geography, rate_type, standard_population, sex, unit, "
            "and provenance as material. If a tool reports ambiguity, present the "
            "candidates and ask the user to choose."
        ),
    )

    @server.tool(
        title="Search health indicators",
        annotations=READ_ONLY,
    )
    def search_indicators(
        query: Annotated[
            str,
            Field(
                min_length=2,
                max_length=200,
                description=(
                    "Plain-language indicator query, for example "
                    "'female lung cancer mortality rate'."
                ),
            ),
        ],
        source: Annotated[
            str | None,
            Field(
                description=(
                    "Optional source: finnish_cancer_registry, nordcan, who_gho, "
                    "or eurostat. "
                    "Source names in the query are also enforced."
                )
            ),
        ] = None,
        geography: Annotated[
            str | None,
            Field(
                description=(
                    "Optional published geography, for example Finland, Denmark, "
                    "Norway, Sweden, Iceland, Greenland, or Faroe Islands."
                )
            ),
        ] = None,
        sex: Annotated[
            str | None,
            Field(description="Optional sex: female, male, or all."),
        ] = None,
        unit: Annotated[
            str | None,
            Field(
                description=(
                    "Optional unit. Canonical values include per_100_000_person_years and percent."
                )
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(ge=1, le=50, description="Maximum matches to return."),
        ] = 10,
    ) -> IndicatorSearchResponse:
        """Search precisely defined indicators and expose all valid rate variants."""
        return registry.search_indicators(
            query,
            source=source,
            geography=geography,
            sex=sex,
            unit=unit,
            limit=limit,
        )

    @server.tool(
        title="Get health observations",
        annotations=READ_ONLY,
    )
    def get_observations(
        indicator_id: Annotated[
            str | None,
            Field(description="Exact identifier returned by search_indicators."),
        ] = None,
        query: Annotated[
            str | None,
            Field(description="Indicator query used when indicator_id is omitted."),
        ] = None,
        source: Annotated[
            str | None,
            Field(description="Optional source identifier."),
        ] = None,
        geography: Annotated[
            str | None,
            Field(description="Optional published geography."),
        ] = None,
        sex: Annotated[
            str | None,
            Field(description="Optional sex filter: female, male, or all."),
        ] = None,
        rate_type: Annotated[
            str | None,
            Field(
                description=(
                    "Explicit canonical rate definition returned by "
                    "search_indicators. Required when several definitions match."
                )
            ),
        ] = None,
        unit: Annotated[
            str | None,
            Field(description="Optional canonical unit filter."),
        ] = None,
        start_year: Annotated[
            int | None,
            Field(ge=1900, le=2200, description="Inclusive first year."),
        ] = None,
        end_year: Annotated[
            int | None,
            Field(ge=1900, le=2200, description="Inclusive final year."),
        ] = None,
    ) -> ObservationResponse:
        """Return a normalised series only after resolving its full definition."""
        return registry.get_observations(
            indicator_id=indicator_id,
            query=query,
            source=source,
            geography=geography,
            sex=sex,
            rate_type=rate_type,
            unit=unit,
            start_year=start_year,
            end_year=end_year,
        )

    @server.tool(
        title="Get latest health observation",
        annotations=READ_ONLY,
    )
    def get_latest_observation(
        indicator_id: Annotated[
            str | None,
            Field(description="Exact identifier returned by search_indicators."),
        ] = None,
        query: Annotated[
            str | None,
            Field(description="Indicator query used when indicator_id is omitted."),
        ] = None,
        source: Annotated[
            str | None,
            Field(description="Optional source identifier."),
        ] = None,
        geography: Annotated[
            str | None,
            Field(description="Optional published geography."),
        ] = None,
        sex: Annotated[
            str | None,
            Field(description="Optional sex filter: female, male, or all."),
        ] = None,
        rate_type: Annotated[
            str | None,
            Field(
                description=(
                    "Explicit epidemiological rate definition. Omission produces "
                    "an ambiguity error when several definitions are valid."
                )
            ),
        ] = None,
        unit: Annotated[
            str | None,
            Field(description="Optional canonical unit filter."),
        ] = None,
    ) -> LatestObservationResponse:
        """Return the latest observation with definition and full provenance."""
        return registry.get_latest_observation(
            indicator_id=indicator_id,
            query=query,
            source=source,
            geography=geography,
            sex=sex,
            rate_type=rate_type,
            unit=unit,
        )

    return server


mcp = create_server()


def main() -> None:
    """Run the MCP server over local stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
