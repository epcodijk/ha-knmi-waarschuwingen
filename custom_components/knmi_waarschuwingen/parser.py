"""Parse KNMI public weather warning snapshots.

This module has no Home Assistant dependencies so it can be tested in isolation.

A snapshot is a JSON document that replaces the previous one completely. It holds
warning *sets* (one per phenomenon/incident) that each contain one or more *parts*.
Every part has its own colour, area (GeoJSON Polygon/MultiPolygon) and validity.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .const import (
    COLOR_GREEN,
    COLOR_RANK,
    SEVERITY_TO_COLOR,
    WARNING_TYPE_PDW,
    WARNING_TYPE_WARNING,
)

ACTIVE = "active"
ACTUAL = "Actual"


def parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp; KNMI timestamps are UTC."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _localized(obj: Any, language: str) -> dict[str, Any]:
    """Return the sub-dict for a language, falling back to nl, then en."""
    if not isinstance(obj, Mapping):
        return {}
    for lang in (language, "nl", "en"):
        value = obj.get(lang)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


# --------------------------------------------------------------------------- geo


def _point_in_ring(lon: float, lat: float, ring: Sequence[Sequence[float]]) -> bool:
    """Ray casting test; ring positions are [lon, lat]."""
    inside = False
    count = len(ring)
    if count < 3:
        return False
    j = count - 1
    for i in range(count):
        xi, yi = float(ring[i][0]), float(ring[i][1])
        xj, yj = float(ring[j][0]), float(ring[j][1])
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def _point_in_polygon(lon: float, lat: float, rings: Sequence[Any]) -> bool:
    if not rings:
        return False
    if not _point_in_ring(lon, lat, rings[0]):
        return False
    # Holes (not used by KNMI today, but valid GeoJSON).
    return not any(_point_in_ring(lon, lat, hole) for hole in rings[1:])


def point_in_geometry(latitude: float, longitude: float, geometry: Any) -> bool:
    """Return True if the point lies within a GeoJSON Polygon/MultiPolygon."""
    if not isinstance(geometry, Mapping):
        return False
    if geometry.get("type") == "Feature":
        return point_in_geometry(latitude, longitude, geometry.get("geometry"))
    if geometry.get("type") == "FeatureCollection":
        return any(
            point_in_geometry(latitude, longitude, feature)
            for feature in geometry.get("features") or []
        )
    geo_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    try:
        if geo_type == "Polygon":
            return _point_in_polygon(longitude, latitude, coordinates)
        if geo_type == "MultiPolygon":
            return any(
                _point_in_polygon(longitude, latitude, polygon)
                for polygon in coordinates
            )
        if geo_type == "GeometryCollection":
            return any(
                point_in_geometry(latitude, longitude, geom)
                for geom in geometry.get("geometries") or []
            )
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return False
    return False


# ----------------------------------------------------------------------- models


@dataclass(frozen=True, slots=True)
class WarningPart:
    """A single warning part, flattened with the data of its warning set."""

    set_uuid: str
    part_uuid: str
    version_id: str
    warning_type: str
    phenomenon: str
    color: str
    severity: str | None
    onset: datetime | None
    expires: datetime | None
    headline: str | None
    description: str | None
    detailed_description: str | None
    impact: str | None
    instruction: str | None
    area_description: str | None
    probability: str | None
    certainty: str | None
    response_type: str | None
    area: Mapping[str, Any] = field(repr=False, compare=False, hash=False)

    @property
    def is_warning(self) -> bool:
        """Return True for a real (code yellow/orange/red) warning."""
        return self.warning_type == WARNING_TYPE_WARNING

    @property
    def is_potentially_dangerous_weather(self) -> bool:
        """Return True for 'potentially dangerous weather' (not yet a warning)."""
        return self.warning_type == WARNING_TYPE_PDW

    @property
    def rank(self) -> int:
        """Return a sortable rank of the colour."""
        return COLOR_RANK.get(self.color, 0)

    @property
    def key(self) -> tuple[str, str]:
        """Return a key that changes when the part is re-issued."""
        return (self.part_uuid, self.version_id)

    def is_current(self, now: datetime) -> bool:
        """Return True if the part is in effect at ``now``."""
        if self.expires is not None and now >= self.expires:
            return False
        return self.onset is None or self.onset <= now

    def is_upcoming(self, now: datetime) -> bool:
        """Return True if the part starts after ``now``."""
        return self.onset is not None and self.onset > now

    def is_expired(self, now: datetime) -> bool:
        """Return True if the part is no longer valid."""
        return self.expires is not None and now >= self.expires

    def contains(self, latitude: float, longitude: float) -> bool:
        """Return True if the location lies in the warning area."""
        return point_in_geometry(latitude, longitude, self.area)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly representation for state attributes."""
        return {
            "phenomenon": self.phenomenon,
            "type": self.warning_type,
            "color": self.color,
            "severity": self.severity,
            "onset": self.onset.isoformat() if self.onset else None,
            "expires": self.expires.isoformat() if self.expires else None,
            "headline": self.headline,
            "description": self.description,
            "detailed_description": self.detailed_description,
            "impact": self.impact,
            "instruction": self.instruction,
            "area_description": self.area_description,
            "probability": self.probability,
            "certainty": self.certainty,
            "response_type": self.response_type,
            "warning_set_uuid": self.set_uuid,
            "part_uuid": self.part_uuid,
        }


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A parsed KNMI warning snapshot."""

    generated_at: datetime | None
    publication_type: str | None
    snapshot_uuid: str | None
    parts: tuple[WarningPart, ...]

    def for_location(
        self, latitude: float, longitude: float, now: datetime
    ) -> list[WarningPart]:
        """Return non-expired parts covering the location, most severe first."""
        matches = [
            part
            for part in self.parts
            if not part.is_expired(now) and part.contains(latitude, longitude)
        ]
        return sort_parts(matches)


def sort_parts(parts: Iterable[WarningPart]) -> list[WarningPart]:
    """Sort by colour (desc) and onset (asc)."""
    far_future = datetime.max.replace(tzinfo=UTC)
    return sorted(parts, key=lambda p: (-p.rank, p.onset or far_future, p.phenomenon))


def highest_color(parts: Iterable[WarningPart]) -> str:
    """Return the highest colour of the given parts, or green."""
    best = COLOR_GREEN
    for part in parts:
        if COLOR_RANK.get(part.color, 0) > COLOR_RANK[best]:
            best = part.color
    return best


def _color(part: Mapping[str, Any]) -> str:
    color = part.get("color")
    if isinstance(color, str) and color.lower() in COLOR_RANK:
        return color.lower()
    return SEVERITY_TO_COLOR.get(str(part.get("severity")), COLOR_GREEN)


def _str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def parse_snapshot(data: Mapping[str, Any], language: str = "nl") -> Snapshot:
    """Parse a snapshot into flattened, *actual* and *active* warning parts."""
    metadata = data.get("metadata") or {}
    parts: list[WarningPart] = []

    for warning_set in data.get("warnings") or []:
        if not isinstance(warning_set, Mapping):
            continue
        if warning_set.get("operational_status", ACTUAL) != ACTUAL:
            continue
        if warning_set.get("status", ACTIVE) != ACTIVE:
            continue

        texts = _localized(warning_set.get("texts"), language)
        set_onset = parse_datetime(warning_set.get("onset"))
        set_expires = parse_datetime(warning_set.get("expires"))
        phenomenon = str(warning_set.get("phenomenon") or "unknown")
        warning_type = str(warning_set.get("warning_type") or WARNING_TYPE_WARNING)
        set_uuid = str(warning_set.get("warning_set_uuid") or "")

        for index, part in enumerate(warning_set.get("parts") or []):
            if not isinstance(part, Mapping):
                continue
            if part.get("status", ACTIVE) != ACTIVE:
                continue
            guidance = _localized(part.get("guidance"), language)
            area_description = part.get(
                "area description", part.get("area_description")
            )
            if isinstance(area_description, Mapping):
                area_description = _localized_text(area_description, language)
            parts.append(
                WarningPart(
                    set_uuid=set_uuid,
                    part_uuid=str(part.get("part_uuid") or f"{set_uuid}-{index}"),
                    version_id=str(
                        part.get("version_id") or warning_set.get("version_id") or ""
                    ),
                    warning_type=warning_type,
                    phenomenon=phenomenon,
                    color=_color(part),
                    severity=_str(part.get("severity")),
                    onset=parse_datetime(part.get("onset")) or set_onset,
                    expires=parse_datetime(part.get("expires")) or set_expires,
                    headline=_str(texts.get("headline")),
                    description=_str(texts.get("description")),
                    detailed_description=_str(texts.get("detailed_description")),
                    impact=_str(guidance.get("impact")),
                    instruction=_str(guidance.get("instruction")),
                    area_description=_str(area_description),
                    probability=_str(part.get("probability_percentage_range")),
                    certainty=_str(part.get("certainty")),
                    response_type=_str(part.get("response_type")),
                    area=part.get("area") or {},
                )
            )

    return Snapshot(
        generated_at=parse_datetime(metadata.get("generated_at")),
        publication_type=_str(metadata.get("publication_type")),
        snapshot_uuid=_str(metadata.get("snapshot_uuid")),
        parts=tuple(parts),
    )


def _localized_text(obj: Mapping[str, Any], language: str) -> str | None:
    for lang in (language, "nl", "en"):
        value = obj.get(lang)
        if isinstance(value, str):
            return value
    return None
