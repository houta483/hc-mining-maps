"""KML/KMZ builder for Google Earth placemarks."""

import logging
import math
from pathlib import Path
from typing import Dict, List

import simplekml

logger = logging.getLogger(__name__)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates in meters.

    Args:
        lat1, lon1: First coordinate
        lat2, lon2: Second coordinate

    Returns:
        Distance in meters
    """
    R = 6371000  # Earth radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def calculate_median_coordinates(
    coordinates: List[tuple], max_spread_meters: float = 10.0
) -> tuple:
    """Calculate median coordinates from a list.

    Validates that coordinates are within max_spread_meters of each other.

    Args:
        coordinates: List of (lat, lon) tuples
        max_spread_meters: Maximum allowed spread in meters

    Returns:
        Tuple of (median_lat, median_lon)

    Raises:
        ValueError: If coordinate spread exceeds max_spread_meters
    """
    if not coordinates:
        raise ValueError("Empty coordinates list")

    if len(coordinates) == 1:
        return coordinates[0]

    # Calculate median
    lats = [c[0] for c in coordinates]
    lons = [c[1] for c in coordinates]

    median_lat = sorted(lats)[len(lats) // 2]
    median_lon = sorted(lons)[len(lons) // 2]

    # Validate spread
    max_distance = 0
    for lat, lon in coordinates:
        dist = haversine_distance(median_lat, median_lon, lat, lon)
        max_distance = max(max_distance, dist)

    if max_distance > max_spread_meters:
        raise ValueError(
            f"Coordinate spread {max_distance:.1f}m exceeds maximum {max_spread_meters}m"
        )

    logger.debug(
        f"Calculated median coordinates: ({median_lat}, {median_lon}), spread: {max_distance:.1f}m"
    )

    return median_lat, median_lon


def build_description_card(mine_area: str, hole_id: str, intervals: List[Dict]) -> str:
    """Build HTML description card for placemark.

    Args:
        mine_area: Mine area name (e.g., "UP-B")
        hole_id: Hole ID (e.g., "T3")
        intervals: List of interval dicts with start, end, fm, box_link

    Returns:
        HTML string for description
    """
    lines = []
    # Sort intervals by start depth
    # Handle both start_ft/end_ft and start/end keys
    sorted_intervals = sorted(
        intervals, key=lambda x: x.get("start_ft") or x.get("start", 0)
    )

    for interval in sorted_intervals:
        box_link = interval.get("box_link", "#")
        # Handle both start_ft/end_ft and start/end keys, and fm_value/fm
        start = interval.get("start_ft") or interval.get("start", 0)
        end = interval.get("end_ft") or interval.get("end", 0)
        fm = interval.get("fm_value") or interval.get("fm", 0)
        lines.append(
            f"{start}–{end} ft → FM {fm:.2f} "
            f'<a href="{box_link}" target="_blank">Box Report</a><br>'
        )

    html = f"""
<div style="width:300px;padding:8px;border-radius:8px;background:#fff;border:1px solid #ccc;font-family:Arial;">
  <b>{mine_area}, Bore Hole {hole_id}, Gradation</b><br>
  {''.join(lines)}
</div>""".strip()

    return html


def validate_intervals(intervals: List[Dict]) -> List[str]:
    """Validate intervals for overlaps and ordering.

    Args:
        intervals: List of interval dicts with start and end

    Returns:
        List of warning messages (empty if no issues)
    """
    warnings = []
    # Handle both start_ft/end_ft and start/end keys
    sorted_intervals = sorted(
        intervals, key=lambda x: x.get("start_ft") or x.get("start", 0)
    )

    for i in range(len(sorted_intervals) - 1):
        current = sorted_intervals[i]
        next_interval = sorted_intervals[i + 1]

        # Get start/end values (handle both key formats)
        current_start = current.get("start_ft") or current.get("start", 0)
        current_end = current.get("end_ft") or current.get("end", 0)
        next_start = next_interval.get("start_ft") or next_interval.get("start", 0)
        next_end = next_interval.get("end_ft") or next_interval.get("end", 0)

        # Check for overlap
        if current_end > next_start:
            warnings.append(
                f"Overlapping intervals: {current_start}-{current_end} ft "
                f"and {next_start}-{next_end} ft"
            )

    return warnings


def build_kmz(
    mine_area: str,
    hole_data: Dict[str, List[Dict]],
    output_path: str,
    max_spread_meters: float = 10.0,
) -> str:
    """Build KMZ file with placemarks for each hole.

    Args:
        mine_area: Mine area name
        hole_data: Dict mapping hole_id to list of interval dicts
        output_path: Output file path for KMZ
        max_spread_meters: Maximum coordinate spread per hole

    Returns:
        Path to created KMZ file
    """
    kml = simplekml.Kml()

    for hole_id, intervals in hole_data.items():
        if not intervals:
            continue

        # Extract coordinates from intervals
        coordinates = [
            (
                interval.get("latitude") or interval.get("lat"),
                interval.get("longitude") or interval.get("lon"),
            )
            for interval in intervals
        ]

        try:
            median_lat, median_lon = calculate_median_coordinates(
                coordinates, max_spread_meters
            )
        except ValueError as e:
            logger.warning(f"Skipping hole {hole_id}: {e}")
            continue

        # Validate intervals
        warnings = validate_intervals(intervals)
        if warnings:
            for warning in warnings:
                logger.warning(f"Hole {hole_id}: {warning}")

        # Build description
        interval_list = [
            {
                "start": interval["start_ft"],
                "end": interval["end_ft"],
                "fm": interval["fm_value"],
                "box_link": interval.get("box_link", "#"),
            }
            for interval in intervals
        ]

        description = build_description_card(mine_area, hole_id, interval_list)

        # Create placemark
        pnt = kml.newpoint(name=f"{mine_area}, {hole_id}")
        pnt.coords = [(median_lon, median_lat)]  # KML uses lon, lat
        pnt.description = description

        # Add extended data for machine reading
        pnt.extendeddata.newdata(name="mine_area", value=mine_area)
        pnt.extendeddata.newdata(name="hole_id", value=hole_id)
        pnt.extendeddata.newdata(name="num_intervals", value=str(len(intervals)))

    # Save as KMZ
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    kml.savekmz(str(output_path))

    logger.info(f"Created KMZ file: {output_path} with {len(hole_data)} holes")

    return str(output_path)
