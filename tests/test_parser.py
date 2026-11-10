"""Tests for the snapshot parser (no Home Assistant needed)."""

from __future__ import annotations

from datetime import UTC, datetime

from custom_components.knmi_waarschuwingen.parser import (
    highest_color,
    parse_snapshot,
    point_in_geometry,
)

from .conftest import AMSTERDAM, ZWOLLE, load_snapshot

NOON = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[5.0, 52.0], [6.0, 52.0], [6.0, 53.0], [5.0, 53.0], [5.0, 52.0]]],
}


def test_point_in_polygon() -> None:
    assert point_in_geometry(52.5, 5.5, SQUARE)
    assert not point_in_geometry(52.5, 6.5, SQUARE)
    assert not point_in_geometry(51.9, 5.5, SQUARE)


def test_point_in_polygon_with_hole() -> None:
    geom = {
        "type": "Polygon",
        "coordinates": [
            SQUARE["coordinates"][0],
            [[5.4, 52.4], [5.6, 52.4], [5.6, 52.6], [5.4, 52.6], [5.4, 52.4]],
        ],
    }
    assert not point_in_geometry(52.5, 5.5, geom)
    assert point_in_geometry(52.2, 5.2, geom)


def test_point_in_multipolygon_and_feature() -> None:
    multi = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            SQUARE["coordinates"],
        ],
    }
    assert point_in_geometry(52.5, 5.5, multi)
    assert point_in_geometry(0.5, 0.5, multi)
    assert point_in_geometry(52.5, 5.5, {"type": "Feature", "geometry": SQUARE})


def test_invalid_geometry() -> None:
    assert not point_in_geometry(52.5, 5.5, None)
    assert not point_in_geometry(52.5, 5.5, {"type": "Point", "coordinates": [5, 52]})
    assert not point_in_geometry(
        52.5, 5.5, {"type": "Polygon", "coordinates": [[["a"]]]}
    )


def test_parse_filters_cancelled_and_test() -> None:
    snapshot = parse_snapshot(load_snapshot())
    uuids = {p.part_uuid for p in snapshot.parts}
    assert "part-cancelled" not in uuids
    assert "part-test" not in uuids
    assert {"part-fog-east", "part-fog-south", "part-wind", "part-pdw"} <= uuids
    assert snapshot.generated_at == datetime(2026, 11, 10, 11, 30, tzinfo=UTC)


def test_zwolle_at_noon() -> None:
    snapshot = parse_snapshot(load_snapshot())
    parts = snapshot.for_location(*ZWOLLE, NOON)
    by_uuid = {p.part_uuid: p for p in parts}
    # Expired road ice is gone; fog current, wind upcoming, PDW present.
    assert set(by_uuid) == {"part-fog-east", "part-wind", "part-pdw"}
    # Sorted most severe first.
    assert parts[0].part_uuid == "part-wind"

    fog = by_uuid["part-fog-east"]
    assert fog.is_current(NOON)
    assert fog.color == "yellow"
    assert fog.headline == "Code geel: dichte mist"
    assert fog.instruction == "Pas je snelheid aan."
    assert fog.area_description == "delen van Overijssel"

    wind = by_uuid["part-wind"]
    assert wind.is_upcoming(NOON)
    assert not wind.is_current(NOON)

    warnings = [p for p in parts if p.is_warning]
    assert highest_color(p for p in warnings if p.is_current(NOON)) == "yellow"
    assert highest_color(warnings) == "orange"


def test_amsterdam_only_pdw() -> None:
    snapshot = parse_snapshot(load_snapshot())
    parts = snapshot.for_location(*AMSTERDAM, NOON)
    assert [p.part_uuid for p in parts] == ["part-pdw"]
    assert parts[0].is_potentially_dangerous_weather
    assert highest_color(p for p in parts if p.is_warning) == "green"


def test_english_texts_with_fallback() -> None:
    snapshot = parse_snapshot(load_snapshot(), language="en")
    by_uuid = {p.part_uuid: p for p in snapshot.parts}
    assert by_uuid["part-fog-east"].headline == "Code yellow: dense fog"
    assert by_uuid["part-fog-east"].instruction == "Adjust your speed."
    # Wind set only has Dutch texts -> falls back to nl.
    assert by_uuid["part-wind"].headline == "Code oranje: zware windstoten"


def test_color_from_severity_when_missing() -> None:
    data = load_snapshot()
    del data["warnings"][1]["parts"][0]["color"]
    snapshot = parse_snapshot(data)
    wind = next(p for p in snapshot.parts if p.part_uuid == "part-wind")
    assert wind.color == "orange"


def test_empty_snapshot() -> None:
    snapshot = parse_snapshot({})
    assert snapshot.parts == ()
    assert snapshot.for_location(*ZWOLLE, NOON) == []
