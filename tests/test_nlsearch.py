"""Tests for nlsearch.py — Claude only extracts a filter; execute_filter is
plain deterministic code. DEMO_MODE keeps these tests offline."""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import MasterPatient
from nlsearch import SearchFilter, execute_filter, parse_query


def _patient(first, last, dob, gender, meds=None, labs=None):
    p = MasterPatient(patient_id=f"MP-{first}", first_name=first, last_name=last, dob=dob, gender=gender)
    p.medications = meds or []
    p.labs = labs or []
    return p


def _med(desc):
    return {"drug_description": desc, "start_date": "2020-01-01T00:00:00Z", "stop_date": ""}


def _lab(test_key, test_date):
    return {"test_key": test_key, "test_date": test_date, "value": "1.0", "units": ""}


class TestDemoParse:
    def test_extracts_warfarin_and_inr(self):
        filt = parse_query("show me everyone on warfarin without a recent INR check")
        assert filt.drug == "warfarin"
        assert filt.missing_lab_test == "inr"

    def test_extracts_metformin_and_egfr(self):
        filt = parse_query("patients on metformin without a recent eGFR check")
        assert filt.drug == "metformin"
        assert filt.missing_lab_test == "egfr"

    def test_no_trigger_phrase_no_lab_filter(self):
        filt = parse_query("patients on lisinopril")
        assert filt.drug == "lisinopril"
        assert filt.missing_lab_test is None

    def test_gender_female(self):
        filt = parse_query("show me female patients on warfarin")
        assert filt.gender == "F"

    def test_gender_male(self):
        filt = parse_query("show me male patients on warfarin")
        assert filt.gender == "M"

    def test_unknown_drug_returns_none(self):
        filt = parse_query("show me everyone with a cold")
        assert filt.drug is None


class TestExecuteFilter:
    def test_filters_by_drug(self):
        patients = [
            _patient("A", "One", "1980-01-01", "F", meds=[_med("Warfarin Sodium 5 MG Oral Tablet")]),
            _patient("B", "Two", "1980-01-01", "F", meds=[_med("Lisinopril 10 MG Oral Tablet")]),
        ]
        results = execute_filter(patients, SearchFilter(drug="warfarin"))
        assert [p.first_name for p in results] == ["A"]

    def test_filters_by_gender(self):
        patients = [
            _patient("A", "One", "1980-01-01", "F"),
            _patient("B", "Two", "1980-01-01", "M"),
        ]
        results = execute_filter(patients, SearchFilter(gender="M"))
        assert [p.first_name for p in results] == ["B"]

    def test_missing_lab_excludes_patients_with_recent_test(self):
        patients = [
            _patient("A", "One", "1980-01-01", "F",
                     meds=[_med("Warfarin Sodium 5 MG Oral Tablet")],
                     labs=[_lab("inr", "2020-05-20T00:00:00Z")]),
            _patient("B", "Two", "1980-01-01", "F",
                     meds=[_med("Warfarin Sodium 5 MG Oral Tablet")]),
        ]
        results = execute_filter(
            patients, SearchFilter(drug="warfarin", missing_lab_test="inr"),
            as_of=date(2020, 6, 1),
        )
        assert [p.first_name for p in results] == ["B"]

    def test_missing_lab_includes_patients_with_stale_test(self):
        # Last INR was over a year ago -- still counts as "missing recent"
        patients = [
            _patient("A", "One", "1980-01-01", "F",
                     meds=[_med("Warfarin Sodium 5 MG Oral Tablet")],
                     labs=[_lab("inr", "2015-01-01T00:00:00Z")]),
        ]
        results = execute_filter(
            patients, SearchFilter(drug="warfarin", missing_lab_test="inr"),
            as_of=date(2020, 6, 1),
        )
        assert len(results) == 1

    def test_no_filters_returns_everyone(self):
        patients = [_patient("A", "One", "1980-01-01", "F"), _patient("B", "Two", "1980-01-01", "M")]
        results = execute_filter(patients, SearchFilter())
        assert len(results) == 2
