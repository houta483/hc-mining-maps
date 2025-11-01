"""API endpoints for managing drone overlay uploads."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from flask import Blueprint, abort, jsonify, request, send_file
from werkzeug.utils import secure_filename

from src.api.middleware import require_auth

logger = logging.getLogger(__name__)

overlay_bp = Blueprint("overlay", __name__, url_prefix="/api/overlay")

OVERLAY_ROOT = Path(os.environ.get("OVERLAY_OUTPUT_DIR", "/app/output/overlays"))
OVERLAY_ROOT.mkdir(parents=True, exist_ok=True)

LATEST_METADATA_PATH = OVERLAY_ROOT / "latest.json"
SUPPORTED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}
MAX_UPLOAD_BYTES = int(
    os.environ.get("OVERLAY_MAX_UPLOAD_BYTES", str(200 * 1024 * 1024))
)


def _run_cli(command: List[str]) -> str:
    """Run a GDAL CLI command and raise detailed error on failure."""

    import subprocess

    logger.debug("Running command: %s", " ".join(command))
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.error(
            "Command failed (%s): %s",
            command[0],
            result.stderr.strip(),
        )
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def _validate_control_points(
    raw_control_points: str,
) -> List[Dict[str, Tuple[float, float]]]:
    try:
        control_points = json.loads(raw_control_points)
    except json.JSONDecodeError as exc:  # pragma: no cover - explicit message
        raise ValueError("controlPoints must be valid JSON") from exc

    if not isinstance(control_points, list) or len(control_points) != 4:
        raise ValueError("Provide exactly four control points.")

    validated: List[Dict[str, Tuple[float, float]]] = []
    for index, point in enumerate(control_points):
        try:
            pixel = point["pixel"]
            coords = point["coordinates"]
            px = float(pixel["x"])
            py = float(pixel["y"])
            lng = float(coords["lng"])
            lat = float(coords["lat"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid control point at index {index}: {exc}") from exc

        validated.append({"pixel": (px, py), "coordinates": (lng, lat)})

    return validated


def _load_latest_metadata() -> Dict[str, object] | None:
    if not LATEST_METADATA_PATH.exists():
        return None

    try:
        with LATEST_METADATA_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to read overlay metadata: %s", exc)
        return None


def _write_latest_metadata(metadata: Dict[str, object]) -> None:
    temp_path = LATEST_METADATA_PATH.with_name(
        f".{LATEST_METADATA_PATH.name}.{uuid.uuid4().hex}"
    )
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
    temp_path.replace(LATEST_METADATA_PATH)


@overlay_bp.route("/latest", methods=["GET"])
@require_auth
def get_latest_overlay():
    """Return the most recent overlay metadata."""

    metadata = _load_latest_metadata()
    return jsonify({"overlay": metadata}), 200


@overlay_bp.route("/image/<path:relative_path>", methods=["GET"])
@require_auth
def get_overlay_image(relative_path: str):
    """Stream the processed overlay image (PNG)."""

    safe_root = OVERLAY_ROOT.resolve()
    requested_path = (OVERLAY_ROOT / relative_path).resolve()

    if (
        not str(requested_path).startswith(str(safe_root))
        or not requested_path.is_file()
    ):
        abort(404)

    return send_file(requested_path, mimetype="image/png", conditional=True)


@overlay_bp.route("", methods=["POST"])
@require_auth
def upload_overlay():
    """Upload an orthomosaic image and queue its georeferenced overlay."""

    image_file = request.files.get("image")
    if not image_file or not image_file.filename:
        return jsonify({"error": "Image file is required."}), 400

    if image_file.mimetype not in SUPPORTED_IMAGE_TYPES:
        return (
            jsonify({"error": "Unsupported image type. Use PNG/JPEG/WebP."}),
            400,
        )

    image_file.seek(0, os.SEEK_END)
    size_bytes = image_file.tell()
    image_file.seek(0)
    if size_bytes > MAX_UPLOAD_BYTES:
        return (
            jsonify({"error": "Image exceeds the 200 MB upload limit."}),
            400,
        )

    image_corners_raw = request.form.get("imageCorners")
    map_corners_raw = request.form.get("mapCorners")
    if not image_corners_raw or not map_corners_raw:
        return (
            jsonify({"error": "imageCorners and mapCorners are required."}),
            400,
        )

    try:
        image_corners = json.loads(image_corners_raw)
        map_corners = json.loads(map_corners_raw)
    except json.JSONDecodeError:
        return jsonify({"error": "Corners payload must be valid JSON."}), 400

    if not isinstance(image_corners, list) or len(image_corners) != 4:
        return (
            jsonify({"error": "imageCorners must contain four points."}),
            400,
        )

    if not isinstance(map_corners, list) or len(map_corners) != 4:
        return (
            jsonify({"error": "mapCorners must contain four points."}),
            400,
        )

    overlay_name = (
        request.form.get("name") or image_file.filename or "Drone Overlay"
    ).strip()
    capture_date = request.form.get("captureDate") or ""
    opacity = float(request.form.get("opacity", 0.85))
    visible = request.form.get("visible", "true").lower() != "false"

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    output_folder = OVERLAY_ROOT / timestamp
    output_folder.mkdir(parents=True, exist_ok=True)

    secure_name = secure_filename(image_file.filename)
    filename_stem = Path(secure_name).stem or f"overlay-{timestamp}"
    final_png_path = output_folder / f"{filename_stem}.png"

    with tempfile.TemporaryDirectory(prefix="overlay-upload-") as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        uploaded_path = tmp_dir_path / secure_name
        image_file.save(uploaded_path)

        gcps_path = tmp_dir_path / "with_gcps.tif"
        warped_tif_path = tmp_dir_path / "warped.tif"

        translate_command = [
            "gdal_translate",
            "-of",
            "GTiff",
            "-a_srs",
            "EPSG:4326",
        ]
        for pixel, coords in zip(image_corners, map_corners):
            translate_command.extend(
                [
                    str(pixel[0]),
                    str(pixel[1]),
                    str(coords[0]),
                    str(coords[1]),
                ]
            )
        translate_command.extend([str(uploaded_path), str(gcps_path)])
        _run_cli(translate_command)

        warp_command = [
            "gdalwarp",
            "-t_srs",
            "EPSG:4326",
            "-r",
            "bilinear",
            "-dstalpha",
            str(gcps_path),
            str(warped_tif_path),
        ]
        _run_cli(warp_command)

        png_command = [
            "gdal_translate",
            "-of",
            "PNG",
            "-co",
            "ZLEVEL=9",
            str(warped_tif_path),
            str(final_png_path),
        ]
        _run_cli(png_command)

    coordinates = map_corners

    image_url = f"/api/overlay/image/{timestamp}/{final_png_path.name}?v={timestamp}"

    metadata = {
        "name": overlay_name,
        "captureDate": capture_date,
        "imageUrl": image_url,
        "coordinates": coordinates,
        "opacity": opacity,
        "visible": visible,
        "updatedAt": datetime.utcnow().isoformat() + "Z",
        "storage": {
            "path": f"{timestamp}/{final_png_path.name}",
        },
    }

    _write_latest_metadata(metadata)

    return jsonify({"message": "Overlay upload succeeded.", "overlay": metadata}), 201
