"""Tests for silo_loader.py."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from silo_loader import group_by_identity, load_silo


class TestLoadSilo:
    def test_loads_all_four_silos(self):
        for silo in ("primary_care", "pharmacy", "labs", "er"):
            rows = load_silo(silo)
            assert len(rows) > 0

    def test_primary_care_has_expected_columns(self):
        rows = load_silo("primary_care")
        assert "condition_description" in rows[0]
        assert "first_name" in rows[0]
        assert "dob" in rows[0]

    def test_pharmacy_dob_is_slash_format(self):
        rows = load_silo("pharmacy")
        assert "/" in rows[0]["dob"]

    def test_primary_care_dob_is_iso_format(self):
        rows = load_silo("primary_care")
        assert "-" in rows[0]["dob"]


class TestGroupByIdentity:
    def test_groups_rows_by_name_and_dob(self):
        rows = [
            {"first_name": "Jane", "last_name": "Doe", "dob": "1980-01-01", "gender": "F"},
            {"first_name": "Jane", "last_name": "Doe", "dob": "1980-01-01", "gender": "F"},
            {"first_name": "Bob", "last_name": "Smith", "dob": "1990-03-03", "gender": "M"},
        ]
        groups = group_by_identity(rows)
        assert len(groups) == 2

    def test_row_indices_preserved(self):
        rows = [
            {"first_name": "Jane", "last_name": "Doe", "dob": "1980-01-01", "gender": "F"},
            {"first_name": "Bob", "last_name": "Smith", "dob": "1990-03-03", "gender": "M"},
            {"first_name": "Jane", "last_name": "Doe", "dob": "1980-01-01", "gender": "F"},
        ]
        groups = group_by_identity(rows)
        jane_group = next(g for g in groups if g["first_name"] == "Jane")
        assert jane_group["row_indices"] == [0, 2]

    def test_empty_input(self):
        assert group_by_identity([]) == []

    def test_real_primary_care_groups_fewer_than_rows(self):
        rows = load_silo("primary_care")
        groups = group_by_identity(rows)
        # Many condition rows per patient -> far fewer identity groups than rows
        assert len(groups) < len(rows)
        assert len(groups) > 0
