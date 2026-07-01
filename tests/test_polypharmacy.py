"""Tests for polypharmacy.py."""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import MasterPatient
from polypharmacy import active_medications_on, check_polypharmacy


def _patient(meds):
    p = MasterPatient(patient_id="MP-TEST", first_name="Test", last_name="Patient", dob="1980-01-01", gender="F")
    p.medications = meds
    return p


def _med(desc, start, stop=""):
    return {"drug_description": desc, "start_date": start, "stop_date": stop}


class TestActiveMedicationsOn:
    def test_active_within_range(self):
        meds = [_med("Drug A", "2020-01-01T00:00:00Z", "2020-06-01T00:00:00Z")]
        active = active_medications_on(_patient(meds), date(2020, 3, 1))
        assert len(active) == 1

    def test_not_yet_started_excluded(self):
        meds = [_med("Drug A", "2020-06-01T00:00:00Z", "2020-12-01T00:00:00Z")]
        active = active_medications_on(_patient(meds), date(2020, 1, 1))
        assert active == []

    def test_already_stopped_excluded(self):
        meds = [_med("Drug A", "2019-01-01T00:00:00Z", "2019-06-01T00:00:00Z")]
        active = active_medications_on(_patient(meds), date(2020, 1, 1))
        assert active == []

    def test_open_ended_still_active(self):
        meds = [_med("Drug A", "2019-01-01T00:00:00Z", "")]
        active = active_medications_on(_patient(meds), date(2030, 1, 1))
        assert len(active) == 1


class TestCheckPolypharmacy:
    def test_below_threshold_not_flagged(self):
        meds = [_med(f"Drug {i}", "2020-01-01T00:00:00Z", "") for i in range(4)]
        result = check_polypharmacy(_patient(meds), date(2020, 6, 1))
        assert result["is_polypharmacy"] is False
        assert result["active_medication_count"] == 4

    def test_at_threshold_flagged(self):
        meds = [_med(f"Drug {i}", "2020-01-01T00:00:00Z", "") for i in range(5)]
        result = check_polypharmacy(_patient(meds), date(2020, 6, 1))
        assert result["is_polypharmacy"] is True

    def test_distinct_drug_names_not_row_count(self):
        # Two prescriptions of the SAME drug shouldn't count as 2 distinct meds
        meds = [_med("Drug A", "2020-01-01T00:00:00Z", "2020-02-01T00:00:00Z"),
                _med("Drug A", "2020-03-01T00:00:00Z", "")]
        result = check_polypharmacy(_patient(meds), date(2020, 6, 1))
        assert result["active_medication_count"] == 1

    def test_no_medications(self):
        result = check_polypharmacy(_patient([]), date(2020, 6, 1))
        assert result["is_polypharmacy"] is False
        assert result["active_medication_count"] == 0
