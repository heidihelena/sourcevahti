"""Normalised public-data models exposed by SourceVahti tools."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class SourceVahtiModel(BaseModel):
    """Strict immutable base model for MCP input and output contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Sex(StrEnum):
    """Sex category as published by the source."""

    FEMALE = "female"
    MALE = "male"
    ALL = "all"


class SourceId(StrEnum):
    """Stable identifier for an upstream data source."""

    FINNISH_CANCER_REGISTRY = "finnish_cancer_registry"
    NORDCAN = "nordcan"
    WHO_GHO = "who_gho"
    EUROSTAT = "eurostat"


class Measure(StrEnum):
    """Normalised statistical measure."""

    CANCER_MORTALITY_RATE = "cancer_mortality_rate"
    TOBACCO_USE_PREVALENCE = "tobacco_use_prevalence"


class Unit(StrEnum):
    """Canonical unit for a normalised observation."""

    PER_100_000_PERSON_YEARS = "per_100_000_person_years"
    PERCENT = "percent"
    COUNT = "count"


class RateType(StrEnum):
    """Epidemiological rate definition."""

    CRUDE = "crude"
    AGE_STANDARDISED_WORLD = "age_standardised_world"
    AGE_STANDARDISED_WORLD_1966 = "age_standardised_world_1966"
    AGE_STANDARDISED_FINLAND_2014 = "age_standardised_finland_2014"
    AGE_STANDARDISED_NORDIC_2000 = "age_standardised_nordic_2000"
    AGE_STANDARDISED_EUROPE_1976 = "age_standardised_europe_1976"
    AGE_STANDARDISED_EUROPE_2013 = "age_standardised_europe_2013"
    AGE_STANDARDISED_WHO = "age_standardised_who"


class ObservationStatus(StrEnum):
    """Publication status supplied or derived from the source."""

    OBSERVED = "observed"
    MODELLED_ESTIMATE = "modelled_estimate"
    PROJECTED = "projected"


class Provenance(SourceVahtiModel):
    """Where an observation came from and when it was captured."""

    source_id: SourceId
    source_name: str = Field(min_length=1)
    dataset_title: str = Field(min_length=1)
    source_url: HttpUrl
    citation_url: HttpUrl
    source_release_version: str = Field(min_length=1)
    source_release_date: date
    retrieval_date: date
    snapshot_id: str = Field(min_length=1)
    license_note: str = Field(min_length=1)

    @model_validator(mode="after")
    def release_not_after_retrieval(self) -> Provenance:
        """Reject provenance that claims a future source release."""
        if self.source_release_date > self.retrieval_date:
            raise ValueError("source_release_date cannot be after retrieval_date")
        return self


class Indicator(SourceVahtiModel):
    """A precisely defined statistical series."""

    indicator_id: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z0-9_.]+$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    measure: Measure
    source_indicator_code: str = Field(min_length=1)
    health_topic: str = Field(min_length=1)
    indicator_definition: str = Field(min_length=1)
    cancer_site: str | None = Field(default=None, min_length=1)
    cancer_definition: str | None = Field(default=None, min_length=1)
    sex: Sex
    geography: str = Field(min_length=1)
    age_group: str = Field(min_length=1)
    unit: Unit
    rate_type: RateType
    standard_population: str | None
    observation_status: ObservationStatus
    first_year: int = Field(ge=1900, le=2200)
    latest_year: int = Field(ge=1900, le=2200)
    provenance: Provenance

    @model_validator(mode="after")
    def validate_rate_definition(self) -> Indicator:
        """Keep crude and age-standardised semantics internally consistent."""
        if self.first_year > self.latest_year:
            raise ValueError("first_year cannot be after latest_year")
        if self.rate_type is RateType.CRUDE and self.standard_population is not None:
            raise ValueError("crude rates cannot have a standard population")
        if self.rate_type is not RateType.CRUDE and not self.standard_population:
            raise ValueError("age-standardised rates require a standard population")
        if self.measure is Measure.CANCER_MORTALITY_RATE and self.unit is Unit.COUNT:
            raise ValueError("cancer mortality rates cannot use the count unit")
        if self.measure is Measure.CANCER_MORTALITY_RATE:
            if not self.cancer_site or not self.cancer_definition:
                raise ValueError("cancer mortality rates require a cancer definition")
            if self.unit is not Unit.PER_100_000_PERSON_YEARS:
                raise ValueError("cancer mortality rates must use the per-100,000 unit")
        if self.measure is Measure.TOBACCO_USE_PREVALENCE:
            if self.unit is not Unit.PERCENT:
                raise ValueError("tobacco prevalence must use percent")
            if self.rate_type is not RateType.AGE_STANDARDISED_WHO:
                raise ValueError("tobacco prevalence requires the WHO-standardised rate type")
        return self


class IndicatorMatch(SourceVahtiModel):
    """A search result with a transparent lexical match score."""

    indicator: Indicator
    score: float = Field(ge=0, le=1)
    matched_terms: list[str]


class IndicatorSearchResponse(SourceVahtiModel):
    """Structured response from ``search_indicators``."""

    query: str
    count: int = Field(ge=0)
    matches: list[IndicatorMatch]


class Observation(SourceVahtiModel):
    """One normalised statistical observation."""

    indicator_id: str
    year: int = Field(ge=1900, le=2200)
    value: float = Field(ge=0)
    lower_bound: float | None = Field(default=None, ge=0)
    upper_bound: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, min_length=1)
    measure: Measure
    source_indicator_code: str = Field(min_length=1)
    unit: Unit
    sex: Sex
    geography: str = Field(min_length=1)
    age_group: str = Field(min_length=1)
    health_topic: str = Field(min_length=1)
    indicator_definition: str = Field(min_length=1)
    cancer_site: str | None = Field(default=None, min_length=1)
    cancer_definition: str | None = Field(default=None, min_length=1)
    rate_type: RateType
    standard_population: str | None
    observation_status: ObservationStatus
    provenance: Provenance

    @model_validator(mode="after")
    def validate_observation_rate(self) -> Observation:
        """Apply the same rate semantics to each observation."""
        if self.rate_type is RateType.CRUDE and self.standard_population is not None:
            raise ValueError("crude observations cannot have a standard population")
        if self.rate_type is not RateType.CRUDE and not self.standard_population:
            raise ValueError("age-standardised observations require a standard population")
        if self.measure is Measure.CANCER_MORTALITY_RATE and self.unit is Unit.COUNT:
            raise ValueError("cancer mortality rates cannot use the count unit")
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and not self.lower_bound <= self.value <= self.upper_bound
        ):
            raise ValueError("value must fall within its uncertainty bounds")
        if (self.lower_bound is None) is not (self.upper_bound is None):
            raise ValueError("uncertainty bounds must be supplied together")
        if self.measure is Measure.CANCER_MORTALITY_RATE:
            if not self.cancer_site or not self.cancer_definition:
                raise ValueError("cancer mortality rates require a cancer definition")
            if self.unit is not Unit.PER_100_000_PERSON_YEARS:
                raise ValueError("cancer mortality rates must use the per-100,000 unit")
        if self.measure is Measure.TOBACCO_USE_PREVALENCE:
            if self.unit is not Unit.PERCENT:
                raise ValueError("tobacco prevalence must use percent")
            if self.rate_type is not RateType.AGE_STANDARDISED_WHO:
                raise ValueError("tobacco prevalence requires the WHO-standardised rate type")
        return self


class ObservationResponse(SourceVahtiModel):
    """Structured response from ``get_observations``."""

    indicator: Indicator
    count: int = Field(ge=0)
    observations: list[Observation]


class LatestObservationResponse(SourceVahtiModel):
    """Structured response from ``get_latest_observation``."""

    indicator: Indicator
    observation: Observation
