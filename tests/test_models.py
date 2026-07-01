"""Tests for models.py."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import MasterPatient


def _mp():
    return MasterPatient(patient_id="MP-00001", first_name="Jane", last_name="Doe", dob="1980-01-01", gender="F")


class TestMasterPatient:
    def test_full_name(self):
        assert _mp().full_name == "Jane Doe"

    def test_silos_present_empty_initially(self):
        assert _mp().silos_present == []

    def test_add_row_primary_care(self):
        p = _mp()
        p.add_row("primary_care", {"condition_description": "x", "first_name": "Jane", "last_name": "Doe", "dob": "1980-01-01"})
        assert p.silos_present == ["primary_care"]
        assert len(p.conditions) == 1

    def test_add_row_all_four_silos(self):
        p = _mp()
        for silo in ("primary_care", "pharmacy", "labs", "er"):
            p.add_row(silo, {"first_name": "Jane", "last_name": "Doe", "dob": "1980-01-01"})
        assert p.silos_present == ["primary_care", "pharmacy", "labs", "er"]

    def test_name_variants_tracks_per_silo_capture(self):
        p = _mp()
        p.add_row("pharmacy", {"first_name": "Jane", "last_name": "Doe", "dob": "01/01/1980"})
        assert ("pharmacy", "Jane Doe", "01/01/1980") in p.name_variants

    def test_unknown_silo_ignored_for_records_but_no_crash(self):
        p = _mp()
        p.add_row("unknown_silo", {"first_name": "Jane", "last_name": "Doe", "dob": "1980-01-01"})
        assert p.conditions == [] and p.medications == [] and p.labs == [] and p.er_visits == []
