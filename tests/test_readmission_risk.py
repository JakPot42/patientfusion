"""Tests for readmission_risk.py — simplified LACE index."""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import MasterPatient
from readmission_risk import compute_lace_score


def _patient(er_visits=None, conditions=None):
    p = MasterPatient(patient_id="MP-TEST", first_name="Test", last_name="Patient", dob="1970-01-01", gender="F")
    p.er_visits = er_visits or []
    p.conditions = conditions or []
    return p


def _er(visit_date, los=0, encounter_class="emergency"):
    return {
        "visit_date": visit_date, "length_of_stay_days": los,
        "encounter_class": encounter_class, "discharge_date": visit_date,
        "chief_complaint": "test",
    }


def _cond(desc):
    return {"condition_description": desc, "onset_date": "2000-01-01", "resolved_date": ""}


class TestNoErVisits:
    def test_returns_none(self):
        assert compute_lace_score(_patient()) is None


class TestLengthOfStayPoints:
    def test_zero_day_stay_low_score(self):
        p = _patient(er_visits=[_er("2020-06-01", los=0)])
        result = compute_lace_score(p)
        assert result["l_points"] == 0

    def test_long_stay_maxes_out(self):
        p = _patient(er_visits=[_er("2020-06-01", los=20)])
        result = compute_lace_score(p)
        assert result["l_points"] == 7


class TestAcuityPoints:
    def test_emergency_class_scores_acute(self):
        p = _patient(er_visits=[_er("2020-06-01", encounter_class="emergency")])
        result = compute_lace_score(p)
        assert result["is_acute_admission"] is True
        assert result["a_points"] == 3

    def test_inpatient_class_not_acute(self):
        p = _patient(er_visits=[_er("2020-06-01", encounter_class="inpatient")])
        result = compute_lace_score(p)
        assert result["is_acute_admission"] is False
        assert result["a_points"] == 0


class TestComorbidityPoints:
    def test_no_conditions_zero_points(self):
        p = _patient(er_visits=[_er("2020-06-01")], conditions=[])
        result = compute_lace_score(p)
        assert result["c_points"] == 0

    def test_diabetes_condition_counted(self):
        p = _patient(er_visits=[_er("2020-06-01")], conditions=[_cond("Diabetes mellitus type 2 (disorder)")])
        result = compute_lace_score(p)
        assert result["comorbidity_count"] >= 1

    def test_comorbidity_points_capped(self):
        conds = [_cond(kw) for kw in ["diabetes", "stroke", "dementia", "hiv", "cirrhosis"]]
        p = _patient(er_visits=[_er("2020-06-01")], conditions=conds)
        result = compute_lace_score(p)
        assert result["c_points"] == 3  # LACE_COMORBIDITY_POINTS_CAP


class TestPriorEdVisits:
    def test_visits_within_six_months_counted(self):
        p = _patient(er_visits=[
            _er("2020-01-01"),
            _er("2020-06-01"),  # index -- most recent
        ])
        result = compute_lace_score(p)
        assert result["prior_ed_visits_6mo"] == 1

    def test_visits_outside_lookback_not_counted(self):
        p = _patient(er_visits=[
            _er("2019-01-01"),  # >6 months before index
            _er("2020-06-01"),
        ])
        result = compute_lace_score(p)
        assert result["prior_ed_visits_6mo"] == 0

    def test_e_points_capped_at_four(self):
        p = _patient(er_visits=[
            _er("2020-01-10"), _er("2020-02-10"), _er("2020-03-10"),
            _er("2020-04-10"), _er("2020-05-10"), _er("2020-06-01"),
        ])
        result = compute_lace_score(p)
        assert result["e_points"] == 4


class TestRiskTiers:
    def test_low_tier(self):
        p = _patient(er_visits=[_er("2020-06-01", los=0, encounter_class="ambulatory")])
        result = compute_lace_score(p)
        assert result["risk_tier"] == "LOW"

    def test_high_tier(self):
        p = _patient(
            er_visits=[
                _er("2020-01-10"), _er("2020-02-10"), _er("2020-03-10"),
                _er("2020-04-10"), _er("2020-06-01", los=20, encounter_class="emergency"),
            ],
            conditions=[_cond("diabetes"), _cond("stroke"), _cond("dementia")],
        )
        result = compute_lace_score(p)
        assert result["risk_tier"] == "HIGH"
        assert result["lace_score"] >= 10

    def test_index_visit_is_most_recent_by_date(self):
        p = _patient(er_visits=[_er("2019-01-01", los=0), _er("2020-06-01", los=5)])
        result = compute_lace_score(p)
        assert result["index_visit_date"] == "2020-06-01"
