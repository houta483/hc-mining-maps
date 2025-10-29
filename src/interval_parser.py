"""Parser for extracting hole IDs, intervals, coordinates, and FM from filenames and Excel files."""

import logging
import re
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
from openpyxl import load_workbook

logger = logging.getLogger(__name__)

# Regex patterns for hole ID extraction
HOLE_RES = [
    re.compile(r"\bT[-_ ]?([A-Za-z0-9]+)\b", re.I),  # T3, T-3, T 3
    re.compile(r"\bBore[-_ ]?Hole[-_ ]?([A-Za-z0-9]+)\b", re.I),
]

# Regex patterns for interval extraction
INTERVAL_RES = [
    re.compile(r"\b(\d+)\s*[_-]\s*(\d+)\s*(?:ft|feet|'|\")?\b", re.I),  # 5_10, 5-10
    re.compile(r"\b(\d+)\s*to\s*(\d+)\s*(?:ft|feet|'|\")?\b", re.I),  # 5 to 10
]


def parse_hole_id_from_title(title: str) -> Optional[str]:
    """Extract hole ID from filename or folder name.

    Args:
        title: Filename or folder name

    Returns:
        Hole ID (e.g., "T3") or None if not found
    """
    for rx in HOLE_RES:
        m = rx.search(title)
        if m:
            return m.group(1).upper()
    return None


def parse_interval_from_title(title: str) -> Optional[Tuple[int, int]]:
    """Extract depth interval from filename.

    Args:
        title: Filename

    Returns:
        Tuple of (start_ft, end_ft) or None if not found

    Raises:
        ValueError: If interval is invalid (start >= end)
    """
    # Normalize various dash/quotes
    t = title.replace("'", "'").replace("–", "-").replace("—", "-")  # noqa: E501

    for rx in INTERVAL_RES:
        m = rx.search(t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a >= b:
                msg = f"Invalid interval in title: {title} (start >= end)"
                raise ValueError(msg)
            return a, b
    return None


def parse_location_cell(raw: str) -> Tuple[float, float]:
    """Parse location cell to extract latitude and longitude.

    Supports:
    - Decimal: 32.483210, -96.361122
    - Decimal with N/W: 32.483210 N, 96.361122 W
    - DMS: 32°28'59.6" N, 96°21'40.0" W

    Args:
        raw: Raw location string from Excel cell

    Returns:
        Tuple of (latitude, longitude)

    Raises:
        ValueError: If location format is unrecognized
    """
    s = raw.strip()

    # Try decimal format first
    m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)", s)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))

        # Handle N/S W/E suffix flipping
        ns = re.search(r"([NS])", s, re.I)
        ew = re.search(r"([EW])", s, re.I)

        if ns and ns.group(1).upper() == "S":
            lat = -abs(lat)
        if ew and ew.group(1).upper() == "W":
            lon = -abs(lon)

        return lat, lon

    # Try DMS format
    m = re.search(
        r"(\d+)[°\s]+(\d+)[\'\s]+([\d.]+)\"?\s*([NS])\s*,\s*"
        r"(\d+)[°\s]+(\d+)[\'\s]+([\d.]+)\"?\s*([EW])",
        s,
        re.I,
    )
    if m:

        def dms_to_dd(sign, d, mnt, sec):
            return sign * (abs(d) + mnt / 60 + sec / 3600)

        lat = dms_to_dd(
            1 if m.group(4).upper() == "N" else -1,
            int(m.group(1)),
            int(m.group(2)),
            float(m.group(3)),
        )
        lon = dms_to_dd(
            1 if m.group(8).upper() == "E" else -1,
            int(m.group(5)),
            int(m.group(6)),
            float(m.group(7)),
        )
        return lat, lon

    msg = f"Unrecognized Location format: {raw}"
    raise ValueError(msg)


def extract_fm_from_xlsx(path: str) -> float:
    """Extract Fineness Modulus from Excel file.

    Tries multiple strategies:
    1. Find "Fineness Modulus" or "FM" label and extract numeric value
    2. Compute from sieve table if present (fallback)

    Args:
        path: Path to Excel file

    Returns:
        Fineness Modulus value

    Raises:
        ValueError: If FM cannot be found or computed
    """
    wb = load_workbook(path, data_only=True)
    sh = wb.active

    # Strategy 1: Find FM label and extract value
    for row in sh.iter_rows(values_only=True):
        for c, v in enumerate(row):
            if isinstance(v, str) and (
                "fineness modulus" in v.lower() or v.strip().lower() == "fm"
            ):
                # Look right within 8 cells for numeric value
                for off in range(1, 9):
                    if c + off < len(row):
                        nv = row[c + off]
                        if isinstance(nv, (int, float)) and not pd.isna(nv):
                            val = float(nv)
                            # Validate reasonable range
                            if 0.5 <= val <= 7.0:
                                filename = Path(path).name
                                logger.debug(
                                    f"Found FM value {val} from label in {filename}"
                                )
                                return val

    # Strategy 2: Compute from sieve table (fallback)
    filename = Path(path).name
    logger.warning(
        f"FM label not found, attempting to compute from sieve table in {filename}"
    )
    try:
        fm = compute_fm_from_sieve_table(sh)
        logger.info(f"Computed FM value {fm} from sieve table in {Path(path).name}")
        return fm
    except Exception as e:
        logger.error(f"Could not compute FM from sieve table: {e}")
        raise ValueError(f"FM not found and cannot be computed from {path}")


def compute_fm_from_sieve_table(sheet) -> float:
    """Compute FM from sieve data table.

    Standard sieve sizes: 3/8", No.4, No.8, No.16, No.30, No.50, No.100, No.200
    FM = (sum of cumulative % retained) / 100

    Args:
        sheet: OpenPyXL worksheet object

    Returns:
        Computed Fineness Modulus

    Raises:
        ValueError: If sieve data cannot be found or parsed
    """
    # Read sheet into pandas for easier data extraction
    df = pd.read_excel(sheet.parent, sheet_name=sheet.title, header=None)

    # Look for sieve sizes row
    sieve_sizes = [
        "3/8",
        "No.4",
        "No.8",
        "No.16",
        "No.30",
        "No.50",
        "No.100",
        "No.200",
    ]

    cumulative_retained = []

    # Search for sieve headers and extract cumulative % retained
    for idx, row in df.iterrows():
        row_str = " ".join([str(x).lower() for x in row if pd.notna(x)])

        # Check if this row contains sieve sizes
        found_sieves = []
        for sieve in sieve_sizes:
            if sieve.lower().replace(".", "") in row_str:
                found_sieves.append(sieve)

        if len(found_sieves) >= 4:  # Found at least 4 sieve sizes
            # Look for cumulative % retained in next few rows
            for next_idx in range(idx + 1, min(idx + 5, len(df))):
                next_row = df.iloc[next_idx]

                # Check if this row contains cumulative retained data
                values = []
                for val in next_row:
                    if isinstance(val, (int, float)) and 0 <= val <= 100:
                        values.append(float(val))

                if len(values) >= len(found_sieves):
                    # Found cumulative retained values
                    cumulative_retained = values[: len(found_sieves)]
                    break

            if cumulative_retained:
                break

    if not cumulative_retained:
        raise ValueError("Cannot find sieve table data in sheet")

    # Calculate FM
    fm = sum(cumulative_retained) / 100.0
    return round(fm, 2)


def extract_location_from_xlsx(path: str) -> Tuple[float, float]:
    """Extract location coordinates from Excel file.

    Looks for a cell labeled "Location" and parses its value.

    Args:
        path: Path to Excel file

    Returns:
        Tuple of (latitude, longitude)

    Raises:
        ValueError: If Location cell not found or unparseable
    """
    wb = load_workbook(path, data_only=True)
    sh = wb.active

    # Search for "Location" cell
    for row in sh.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and "location" in cell.value.lower():
                # Found Location label, get value from adjacent cell
                next_cell = sh.cell(row=cell.row, column=cell.column + 1)
                if next_cell.value:
                    return parse_location_cell(str(next_cell.value))

    # Alternative: Look in a specific cell (e.g., B1, A2, etc.)
    common_location_cells = ["B1", "A2", "B2", "C1"]
    for cell_ref in common_location_cells:
        try:
            cell = sh[cell_ref]
            if cell.value:
                return parse_location_cell(str(cell.value))
        except Exception:
            continue

    filename = Path(path).name
    raise ValueError(f"Location cell not found in {filename}")


def parse_file(file_path: str, hole_id: Optional[str] = None) -> dict:
    """Parse a gradation report Excel file to extract all metadata.

    Args:
        file_path: Path to Excel file
        hole_id: Optional hole ID (if not in filename)

    Returns:
        Dictionary with hole_id, start_ft, end_ft, latitude, longitude, fm_value

    Raises:
        ValueError: If required data cannot be extracted
    """
    filename = Path(file_path).name

    # Extract hole ID
    if not hole_id:
        hole_id = parse_hole_id_from_title(filename)
        if not hole_id:
            raise ValueError(f"Cannot extract hole ID from filename: {filename}")

    # Extract interval
    interval = parse_interval_from_title(filename)
    if not interval:
        raise ValueError(f"Cannot extract interval from filename: {filename}")

    start_ft, end_ft = interval

    # Extract location
    try:
        lat, lon = extract_location_from_xlsx(file_path)
    except Exception as e:
        logger.error(f"Error extracting location from {filename}: {e}")
        raise ValueError(f"Location extraction failed for {filename}: {e}")

    # Extract FM
    try:
        fm_value = extract_fm_from_xlsx(file_path)
    except Exception as e:
        logger.error(f"Error extracting FM from {filename}: {e}")
        raise ValueError(f"FM extraction failed for {filename}: {e}")

    return {
        "hole_id": hole_id,
        "start_ft": start_ft,
        "end_ft": end_ft,
        "latitude": lat,
        "longitude": lon,
        "fm_value": fm_value,
        "filename": filename,
    }
