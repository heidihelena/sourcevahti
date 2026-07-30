"""Actionable domain errors for model-facing MCP tool failures."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


class SourceVahtiError(ValueError):
    """Base error serialised as a compact, model-readable JSON object."""

    code = "sourcevahti_error"

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})
        self.hint = hint

    def as_dict(self) -> dict[str, Any]:
        """Return the stable error payload embedded in the tool error text."""
        payload: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details:
            payload["error"]["details"] = self.details
        if self.hint:
            payload["error"]["hint"] = self.hint
        return payload

    def __str__(self) -> str:
        """Render JSON so an MCP caller can recover without guessing."""
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)


class InputValidationError(SourceVahtiError):
    """A supplied query dimension is unsupported or inconsistent."""

    code = "invalid_input"


class IndicatorNotFoundError(SourceVahtiError):
    """No indicator satisfies the requested definition."""

    code = "indicator_not_found"


class AmbiguousIndicatorError(SourceVahtiError):
    """More than one epidemiologically valid series matches a request."""

    code = "ambiguous_indicator"

    def __init__(
        self,
        message: str,
        *,
        candidates: Sequence[Mapping[str, Any]],
    ) -> None:
        super().__init__(
            message,
            details={"candidates": [dict(candidate) for candidate in candidates]},
            hint=(
                "Retry with indicator_id or specify source, geography, and rate_type. "
                "Never choose among distinct definitions implicitly."
            ),
        )


class SourceDataError(SourceVahtiError):
    """The frozen upstream response is missing or violates its contract."""

    code = "source_data_error"
