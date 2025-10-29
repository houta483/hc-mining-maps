"""Tests for interval parser."""

import pytest
from src.interval_parser import (
    parse_hole_id_from_title,
    parse_interval_from_title,
    parse_location_cell,
)


class TestHoleIDParsing:
    """Test hole ID extraction from filenames."""

    def test_simple_hole_id(self):
        assert parse_hole_id_from_title("QC Gradation Report T3 5_10.xlsx") == "T3"

    def test_dash_separated(self):
        assert parse_hole_id_from_title("Report T-3 10_15.xlsx") == "T3"

    def test_space_separated(self):
        assert parse_hole_id_from_title("Report T 3 15_20.xlsx") == "T3"

    def test_bore_hole_format(self):
        assert parse_hole_id_from_title("Bore Hole 5 20_25.xlsx") == "5"

    def test_no_hole_id(self):
        assert parse_hole_id_from_title("Report 5_10.xlsx") is None


class TestIntervalParsing:
    """Test interval extraction from filenames."""

    def test_underscore_separator(self):
        assert parse_interval_from_title("Report T3 5_10.xlsx") == (5, 10)

    def test_dash_separator(self):
        assert parse_interval_from_title("Report T3 10-15.xlsx") == (10, 15)

    def test_to_keyword(self):
        assert parse_interval_from_title("Report 15 to 20.xlsx") == (15, 20)

    def test_with_feet_marker(self):
        assert parse_interval_from_title("Report 5' 10 ft.xlsx") == (5, 10)

    def test_invalid_interval(self):
        with pytest.raises(ValueError):
            parse_interval_from_title("Report 10_5.xlsx")  # start >= end

    def test_no_interval(self):
        assert parse_interval_from_title("Report T3.xlsx") is None


class TestLocationParsing:
    """Test coordinate parsing from Location cells."""

    def test_decimal_format(self):
        lat, lon = parse_location_cell("32.483210, -96.361122")
        assert lat == 32.483210
        assert lon == -96.361122

    def test_decimal_with_ns(self):
        lat, lon = parse_location_cell("32.483210 N, 96.361122 W")
        assert lat == 32.483210
        assert lon == -96.361122

    def test_dms_format(self):
        lat, lon = parse_location_cell("32°28'59.6\" N, 96°21'40.0\" W")
        assert abs(lat - 32.483222) < 0.01
        assert abs(lon - (-96.361111)) < 0.01

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_location_cell("Invalid location")
