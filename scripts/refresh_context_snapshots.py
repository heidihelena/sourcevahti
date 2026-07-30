"""Refresh reviewed WHO and Eurostat Nordic lung-cancer context snapshots.

This maintenance script is intentionally not part of server startup. It downloads
narrow source responses, validates their dimensional scope, and writes deterministic
CSV files for review before release.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

COUNTRIES = {
    "DNK": "Denmark",
    "FIN": "Finland",
    "ISL": "Iceland",
    "NOR": "Norway",
    "SWE": "Sweden",
}
EUROSTAT_COUNTRIES = {
    "DK": "Denmark",
    "FI": "Finland",
    "IS": "Iceland",
    "NO": "Norway",
    "SE": "Sweden",
}
WHO_SEXES = {
    "SEX_FMLE": "female",
    "SEX_MLE": "male",
    "SEX_BTSX": "all",
}
EUROSTAT_SEXES = {"F": "female", "M": "male", "T": "all"}
WHO_URL = "https://ghoapi.azureedge.net/api/M_Est_tob_curr_std"
EUROSTAT_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/HLTH_CD_ASDR2"


def fetch_json(url: str, params: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Fetch one official JSON response with a transparent user agent."""
    query = urllib.parse.urlencode(list(params))
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"User-Agent": "SourceVahti snapshot refresh/0.3"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def fetch_who_rows() -> list[dict[str, object]]:
    """Return the 2000-2025 Nordic WHO tobacco-use estimate matrix."""
    rows: list[dict[str, object]] = []
    for country_code, country in COUNTRIES.items():
        payload = fetch_json(
            WHO_URL,
            (
                (
                    "$filter",
                    (f"SpatialDim eq '{country_code}' and TimeDim ge 2000 and TimeDim le 2025"),
                ),
                (
                    "$select",
                    ("SpatialDim,Dim1,TimeDim,NumericValue,Low,High,Comments,Date"),
                ),
            ),
        )
        for item in payload["value"]:
            sex_code = item["Dim1"]
            if sex_code not in WHO_SEXES:
                continue
            note = item.get("Comments") or ""
            rows.append(
                {
                    "country_code": country_code,
                    "country": country,
                    "sex_code": sex_code,
                    "sex": WHO_SEXES[sex_code],
                    "year": int(item["TimeDim"]),
                    "value": float(item["NumericValue"]),
                    "lower_bound": float(item["Low"]),
                    "upper_bound": float(item["High"]),
                    "status": (
                        "projected" if "projection" in note.casefold() else "modelled_estimate"
                    ),
                    "note": note,
                    "updated_at": item["Date"],
                }
            )
    validate_matrix(rows, expected_countries=set(COUNTRIES.values()), minimum_years=10)
    return sorted(rows, key=row_sort_key)


def ordered_codes(dimension: Mapping[str, Any]) -> list[str]:
    """Return JSON-stat category codes in their declared positional order."""
    index = dimension["category"]["index"]
    if isinstance(index, list):
        return [str(value) for value in index]
    return [str(code) for code, _ in sorted(index.items(), key=lambda item: int(item[1]))]


def jsonstat_rows(payload: Mapping[str, Any]) -> Iterable[dict[str, object]]:
    """Expand a compact JSON-stat value map into dimension-labelled rows."""
    dimension_ids = [str(value) for value in payload["id"]]
    dimensions = payload["dimension"]
    codes = [ordered_codes(dimensions[dimension_id]) for dimension_id in dimension_ids]
    sizes = [int(value) for value in payload["size"]]
    values = payload.get("value", {})
    statuses = payload.get("status") or {}

    for positions in itertools.product(*(range(size) for size in sizes)):
        flat_index = 0
        for position, size in zip(positions, sizes, strict=True):
            flat_index = flat_index * size + position
        value = values.get(str(flat_index))
        if value is None:
            continue
        row = {
            dimension_id: codes[index][position]
            for index, (dimension_id, position) in enumerate(
                zip(dimension_ids, positions, strict=True)
            )
        }
        row["value"] = float(value)
        row["status_flag"] = statuses.get(str(flat_index), "")
        yield row


def fetch_eurostat_rows() -> list[dict[str, object]]:
    """Return Nordic Eurostat lung-cancer standardised death rates since 2011."""
    params: list[tuple[str, str]] = [
        ("lang", "EN"),
        ("unit", "RT"),
        ("age", "TOTAL"),
        ("icd10", "C33_C34"),
        ("sinceTimePeriod", "2011"),
    ]
    params.extend(("geo", code) for code in EUROSTAT_COUNTRIES)
    params.extend(("sex", code) for code in EUROSTAT_SEXES)
    payload = fetch_json(EUROSTAT_URL, params)
    updated_at = str(payload["updated"])
    rows = [
        {
            "country_code": row["geo"],
            "country": EUROSTAT_COUNTRIES[str(row["geo"])],
            "sex_code": row["sex"],
            "sex": EUROSTAT_SEXES[str(row["sex"])],
            "year": int(row["time"]),
            "value": row["value"],
            "status_flag": row["status_flag"],
            "note": (f"Eurostat status flag: {row['status_flag']}" if row["status_flag"] else ""),
            "updated_at": updated_at,
        }
        for row in jsonstat_rows(payload)
    ]
    validate_matrix(
        rows,
        expected_countries=set(EUROSTAT_COUNTRIES.values()),
        minimum_years=10,
    )
    return sorted(rows, key=row_sort_key)


def row_sort_key(row: Mapping[str, object]) -> tuple[str, str, int]:
    """Sort snapshots stably by country, sex, then year."""
    return str(row["country"]), str(row["sex"]), int(row["year"])


def validate_matrix(
    rows: list[dict[str, object]],
    *,
    expected_countries: set[str],
    minimum_years: int,
) -> None:
    """Reject missing countries, short series, duplicates, and invalid values."""
    countries = {str(row["country"]) for row in rows}
    if countries != expected_countries:
        raise ValueError(f"unexpected country scope: {sorted(countries)}")
    keys = [(str(row["country"]), str(row["sex"]), int(row["year"])) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("snapshot contains duplicate country-sex-year rows")
    if any(float(row["value"]) < 0 for row in rows):
        raise ValueError("snapshot contains a negative value")
    for country, sex in itertools.product(expected_countries, {"female", "male", "all"}):
        years = {
            int(row["year"]) for row in rows if row["country"] == country and row["sex"] == sex
        }
        if len(years) < minimum_years:
            raise ValueError(f"{country} {sex} contains only {len(years)} years")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write a deterministic UTF-8 CSV using the first row's field order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    """Refresh both snapshots into the package data directory."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("src/sourcevahti/data"),
    )
    args = parser.parse_args()
    write_csv(
        args.output_dir / "who_gho_tobacco_use_2026_01_15.csv",
        fetch_who_rows(),
    )
    write_csv(
        args.output_dir / "eurostat_lung_mortality_2026_06_08.csv",
        fetch_eurostat_rows(),
    )


if __name__ == "__main__":
    main()
