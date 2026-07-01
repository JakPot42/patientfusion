"""Tests for screenings.py — overdue population screenings and drug
monitoring gaps."""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import MasterPatient
from screenings import check_monitoring_gaps, check_overdue_screenings, most_recent_lab_date


def _patient(dob, labs=None, meds=None):
    p = MasterPatient(patient_id="MP-TEST", first_name="Test", last_name="Patient", dob=dob, gender="F")
    p.labs = labs or []
    p.medications = meds or []
    return p


def _lab(test_key, test_date, value="1.0"):
    return {"test_key": test_key, "test_date": test_date, "value": value, "units": ""}


def _med(desc, start="2020-01-01T00:00:00Z", stop=""):
    return {"drug_description": desc, "start_date": start, "stop_date": stop}


class TestMostRecentLabDate:
    def test_returns_max_date(self):
        p = _patient("1970-01-01", labs=[_lab("a1c", "2019-01-01T00:00:00Z"), _lab("a1c", "2021-06-01T00:00:00Z")])
        result = most_recent_lab_date(p, "a1c")
        assert result == date(2021, 6, 1)

    def test_no_matching_test_returns_none(self):
        p = _patient("1970-01-01", labs=[_lab("egfr", "2020-01-01T00:00:00Z")])
        assert most_recent_lab_date(p, "a1c") is None


class TestOverdueScreenings:
    def test_a1c_overdue_for_eligible_age_with_no_lab(self):
        p = _patient("1980-01-01")  # age 40 on 2020-01-01
        findings = check_overdue_screenings(p, date(2020, 1, 1))
        assert any(f["rule_id"] == "diabetes_a1c" for f in findings)

    def test_a1c_not_overdue_when_recent(self):
        p = _patient("1980-01-01", labs=[_lab("a1c", "2019-06-01T00:00:00Z")])
        findings = check_overdue_screenings(p, date(2020, 1, 1))
        assert not any(f["rule_id"] == "diabetes_a1c" for f in findings)

    def test_a1c_overdue_when_stale(self):
        p = _patient("1980-01-01", labs=[_lab("a1c", "2010-01-01T00:00:00Z")])
        findings = check_overdue_screenings(p, date(2020, 1, 1))
        assert any(f["rule_id"] == "diabetes_a1c" for f in findings)

    def test_too_young_not_flagged(self):
        p = _patient("2010-01-01")  # age 10
        findings = check_overdue_screenings(p, date(2020, 1, 1))
        assert not any(f["rule_id"] == "diabetes_a1c" for f in findings)

    def test_too_old_for_a1c_not_flagged(self):
        p = _patient("1940-01-01")  # age 80, above max_age 70
        findings = check_overdue_screenings(p, date(2020, 1, 1))
        assert not any(f["rule_id"] == "diabetes_a1c" for f in findings)

    def test_lipid_panel_has_no_max_age(self):
        p = _patient("1940-01-01")  # age 80
        findings = check_overdue_screenings(p, date(2020, 1, 1))
        assert any(f["rule_id"] == "lipid_panel" for f in findings)

    def test_missing_dob_returns_no_findings(self):
        p = _patient("")
        assert check_overdue_screenings(p, date(2020, 1, 1)) == []

    def test_every_rule_has_citation(self):
        from config import SCREENING_RULES
        for rule in SCREENING_RULES:
            assert rule["citation"]


class TestMonitoringGaps:
    def test_warfarin_without_inr_flagged(self):
        p = _patient("1970-01-01", meds=[_med("Warfarin Sodium 5 MG Oral Tablet")])
        findings = check_monitoring_gaps(p, date(2020, 6, 1))
        assert any(f["rule_id"] == "warfarin_inr" for f in findings)

    def test_warfarin_with_recent_inr_not_flagged(self):
        p = _patient(
            "1970-01-01",
            meds=[_med("Warfarin Sodium 5 MG Oral Tablet")],
            labs=[_lab("inr", "2020-05-20T00:00:00Z")],
        )
        findings = check_monitoring_gaps(p, date(2020, 6, 1))
        assert not any(f["rule_id"] == "warfarin_inr" for f in findings)

    def test_warfarin_with_stale_inr_flagged(self):
        p = _patient(
            "1970-01-01",
            meds=[_med("Warfarin Sodium 5 MG Oral Tablet")],
            labs=[_lab("inr", "2019-01-01T00:00:00Z")],
        )
        findings = check_monitoring_gaps(p, date(2020, 6, 1))
        assert any(f["rule_id"] == "warfarin_inr" for f in findings)

    def test_no_matching_drug_no_findings(self):
        p = _patient("1970-01-01", meds=[_med("Lisinopril 10 MG Oral Tablet")])
        assert check_monitoring_gaps(p, date(2020, 6, 1)) == []

    def test_metformin_annual_egfr_requirement(self):
        p = _patient(
            "1970-01-01",
            meds=[_med("24 HR Metformin hydrochloride 500 MG Extended Release Oral Tablet")],
            labs=[_lab("egfr", "2019-01-01T00:00:00Z")],
        )
        # >365 days since last egfr as of 2020-06-01 -> overdue
        findings = check_monitoring_gaps(p, date(2020, 6, 1))
        assert any(f["rule_id"] == "metformin_renal_function" for f in findings)
