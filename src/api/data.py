"""Data API endpoints."""

import json
import logging
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, request

from src.api.middleware import require_auth

logger = logging.getLogger(__name__)

data_bp = Blueprint("data", __name__, url_prefix="/api")

STATUS_PATH = Path("/app/logs/pipeline_status.json")
TRIGGER_PATH = Path("/app/logs/manual_trigger.json")


def _read_pipeline_status() -> dict:
    """Read pipeline status file if present."""

    if STATUS_PATH.exists():
        try:
            return json.loads(STATUS_PATH.read_text())
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.error("Failed to read pipeline status: %s", exc, exc_info=True)
    return {"state": "unknown"}


def _read_pending_trigger() -> dict:
    """Return queued manual trigger metadata if present."""

    if TRIGGER_PATH.exists():
        try:
            data = json.loads(TRIGGER_PATH.read_text())
            data.setdefault("source", "manual")
            return data
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.error("Failed to read manual trigger file: %s", exc, exc_info=True)
            return {"source": "manual"}
    return {}


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

    pipeline_status = _read_pipeline_status()
    pending_trigger = _read_pending_trigger()
    if pending_trigger:
        pipeline_status["pending_trigger"] = pending_trigger

    status_data = {
        "status": "running",
        "kmz_exists": kmz_path.exists(),
        "kmz_size": kmz_path.stat().st_size if kmz_path.exists() else 0,
        "kmz_modified": (kmz_path.stat().st_mtime if kmz_path.exists() else None),
        "pipeline": pipeline_status,
    }

    return jsonify(status_data)


@data_bp.route("/pipeline/run", methods=["POST"])
@require_auth
def trigger_pipeline_run():
    """Queue a manual pipeline run (requires authentication)."""

    pipeline_status = _read_pipeline_status()
    if pipeline_status.get("state") == "running":
        return (
            jsonify(
                {
                    "status": "running",
                    "message": "Pipeline is already running",
                    "pipeline": pipeline_status,
                }
            ),
            409,
        )

    if TRIGGER_PATH.exists():
        existing_trigger = _read_pending_trigger()
        return (
            jsonify(
                {
                    "status": "queued",
                    "message": "A manual pipeline run is already queued",
                    "trigger": existing_trigger,
                }
            ),
            202,
        )

    trigger_payload = {
        "id": str(uuid.uuid4()),
        "requested_at": datetime.utcnow().isoformat() + "Z",
        "requested_by": getattr(request, "username", "unknown"),
        "source": "manual",
    }

    TRIGGER_PATH.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = TRIGGER_PATH.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(trigger_payload, indent=2))
        tmp_path.replace(TRIGGER_PATH)
    except Exception as exc:  # pragma: no cover - operational guardrail
        logger.error("Failed to queue manual pipeline run: %s", exc, exc_info=True)
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return (
            jsonify({"error": "Unable to queue manual pipeline run"}),
            500,
        )

    return jsonify({"status": "queued", "trigger": trigger_payload}), 202
