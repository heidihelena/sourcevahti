"""Protocol-level tests through the MCP SDK's in-memory client."""

from collections.abc import AsyncIterator

import pytest
from mcp import Client

from sourcevahti.server import mcp


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[Client]:
    async with Client(mcp, raise_exceptions=True) as connected:
        yield connected


@pytest.mark.anyio
async def test_server_exposes_exactly_three_read_only_tools(client: Client) -> None:
    result = await client.list_tools()
    assert [tool.name for tool in result.tools] == [
        "search_indicators",
        "get_observations",
        "get_latest_observation",
    ]
    assert all(tool.annotations is not None for tool in result.tools)
    assert all(tool.annotations.read_only_hint for tool in result.tools)


@pytest.mark.anyio
async def test_search_tool_has_structured_result(client: Client) -> None:
    result = await client.call_tool(
        "search_indicators",
        {
            "query": "female lung cancer mortality rate",
            "source": "finnish_cancer_registry",
            "sex": "female",
            "unit": "per 100 000",
        },
    )

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["count"] == 3
    assert len(result.structured_content["matches"]) == 3


@pytest.mark.anyio
async def test_latest_tool_satisfies_acceptance_contract(client: Client) -> None:
    result = await client.call_tool(
        "get_latest_observation",
        {
            "query": "female lung cancer mortality rate",
            "sex": "female",
            "rate_type": "age_standardised_finland_2014",
            "unit": "per_100_000_person_years",
        },
    )

    assert not result.is_error
    assert result.structured_content is not None
    observation = result.structured_content["observation"]
    assert observation["cancer_definition"].endswith("(ICD-10 C33-C34)")
    assert observation["year"] == 2024
    assert observation["value"] == 23.28
    assert observation["rate_type"] == "age_standardised_finland_2014"
    assert observation["standard_population"] == "Finland population 2014"
    assert observation["unit"] == "per_100_000_person_years"
    assert observation["provenance"]["retrieval_date"] == "2026-07-30"
    assert observation["provenance"]["citation_url"].startswith("https://cancerregistry.fi/")


@pytest.mark.anyio
async def test_ambiguity_is_a_model_visible_tool_error(client: Client) -> None:
    result = await client.call_tool(
        "get_latest_observation",
        {
            "query": "mortality rate",
            "source": "finnish_cancer_registry",
            "sex": "female",
        },
    )

    assert result.is_error
    assert result.structured_content is None
    assert '"code": "ambiguous_indicator"' in result.content[0].text
    assert "age_standardised_finland_2014" in result.content[0].text
    assert "age_standardised_world_1966" in result.content[0].text
    assert '"rate_type": "crude"' in result.content[0].text


@pytest.mark.anyio
async def test_invalid_unit_is_a_model_visible_tool_error(client: Client) -> None:
    result = await client.call_tool(
        "get_latest_observation",
        {
            "indicator_id": "fcr.lung_trachea.mortality.crude.female",
            "unit": "percent",
        },
    )
    assert result.is_error
    assert '"code": "invalid_input"' in result.content[0].text


@pytest.mark.anyio
async def test_free_text_sex_cannot_select_opposite_series(client: Client) -> None:
    result = await client.call_tool(
        "get_latest_observation",
        {
            "query": "male lung cancer mortality rate",
            "rate_type": "crude",
        },
    )

    assert result.is_error
    assert '"code": "indicator_not_found"' in result.content[0].text


@pytest.mark.anyio
async def test_nordcan_latest_tool_preserves_rate_definition(client: Client) -> None:
    result = await client.call_tool(
        "get_latest_observation",
        {
            "query": "female Denmark lung cancer mortality, Nordic 2000",
            "source": "nordcan",
            "geography": "Denmark",
        },
    )

    assert not result.is_error
    assert result.structured_content is not None
    observation = result.structured_content["observation"]
    assert observation["year"] == 2024
    assert observation["value"] == 43.0
    assert observation["rate_type"] == "age_standardised_nordic_2000"
    assert observation["standard_population"] == "NORDCAN population 2000"
    assert observation["provenance"]["source_id"] == "nordcan"
    assert observation["provenance"]["source_release_version"] == "9.6"
