"""Data API endpoints."""

import logging
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from flask import Blueprint, jsonify

from src.api.middleware import require_auth

logger = logging.getLogger(__name__)

data_bp = Blueprint("data", __name__, url_prefix="/api")


@data_bp.route("/geojson", methods=["GET"])
@require_auth
def get_geojson():
    """Convert KMZ to GeoJSON for Mapbox (auth required)."""
    output_dir = Path("/app/output")
    kmz_path = output_dir / "hc_mining_UP-B_fm.kmz"

    if not kmz_path.exists():
        return jsonify({"type": "FeatureCollection", "features": []}), 200

    try:
        # Extract KML from KMZ
        features = []
        with zipfile.ZipFile(kmz_path, "r") as kmz:
            # Find KML file in KMZ
            kml_files = [f for f in kmz.namelist() if f.endswith(".kml")]
            if not kml_files:
                return jsonify({"type": "FeatureCollection", "features": []}), 200

            kml_content = kmz.read(kml_files[0])
            root = ET.fromstring(kml_content)

            # Parse KML and convert to GeoJSON
            ns = {"kml": "http://www.opengis.net/kml/2.2"}

            for placemark in root.findall(".//kml:Placemark", ns):
                name_elem = placemark.find("kml:name", ns)
                name = name_elem.text if name_elem is not None else "Unknown"

                # Extract coordinates
                coords_elem = placemark.find(".//kml:coordinates", ns)
                if coords_elem is None:
                    continue

                coords_str = coords_elem.text.strip()
                # KML format: "lon,lat,alt" or "lon,lat"
                coords = coords_str.split(",")
                if len(coords) < 2:
                    continue

                lon = float(coords[0])
                lat = float(coords[1])

                # Extract description/properties
                desc_elem = placemark.find("kml:description", ns)
                description = desc_elem.text if desc_elem is not None else ""

                # Try to parse hole ID from name
                hole_id = name.replace("Hole ", "").replace("T", "").strip()

                feature = {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "name": name,
                        "hole_id": hole_id,
                        "description": description,
                    },
                }
                features.append(feature)

        geojson = {"type": "FeatureCollection", "features": features}

        logger.info(f"Converted KMZ to GeoJSON: {len(features)} features")
        return jsonify(geojson)

    except Exception as e:
        logger.error(f"Error converting KMZ to GeoJSON: {e}", exc_info=True)
        return jsonify({"type": "FeatureCollection", "features": []}), 200


@data_bp.route("/status", methods=["GET"])
@require_auth
def status():
    """Pipeline status (requires authentication)."""
    output_dir = Path("/app/output")
    kmz_path = output_dir / "hc_mining_UP-B_fm.kmz"

    status_data = {
        "status": "running",
        "kmz_exists": kmz_path.exists(),
        "kmz_size": kmz_path.stat().st_size if kmz_path.exists() else 0,
        "kmz_modified": (kmz_path.stat().st_mtime if kmz_path.exists() else None),
    }

    return jsonify(status_data)
