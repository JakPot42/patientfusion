"""Tests for risk_engine.py — orchestration only; each rule is tested on
its own elsewhere."""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import MasterPatient
from risk_engine import evaluate_patient, population_heatmap_rows


def _patient(pid="MP-TEST", meds=None, er_visits=None):
    p = MasterPatient(patient_id=pid, first_name="Test", last_name="Patient", dob="1970-01-01", gender="F")
    p.medications = meds or []
    p.er_visits = er_visits or []
    return p


class TestEvaluatePatient:
    def test_returns_all_five_keys(self):
        result = evaluate_patient(_patient(), as_of=date(2020, 1, 1))
        assert set(result.keys()) == {
            "drug_interactions", "polypharmacy", "overdue_screenings",
            "monitoring_gaps", "readmission_risk",
        }

    def test_no_er_visits_readmission_risk_is_none(self):
        result = evaluate_patient(_patient(), as_of=date(2020, 1, 1))
        assert result["readmission_risk"] is None

    def test_with_er_visit_readmission_risk_present(self):
        er = [{"visit_date": "2020-01-01", "length_of_stay_days": 0, "encounter_class": "emergency", "chief_complaint": "x"}]
        result = evaluate_patient(_patient(er_visits=er), as_of=date(2020, 1, 1))
        assert result["readmission_risk"] is not None


class TestPopulationHeatmapRows:
    def test_one_row_per_patient(self):
        patients = [_patient("MP-1"), _patient("MP-2")]
        rows = population_heatmap_rows(patients, as_of=date(2020, 1, 1))
        assert len(rows) == 2
        assert {r["patient_id"] for r in rows} == {"MP-1", "MP-2"}

    def test_row_has_expected_fields(self):
        rows = population_heatmap_rows([_patient()], as_of=date(2020, 1, 1))
        row = rows[0]
        for key in ("patient_id", "name", "lace_score", "risk_tier", "interaction_count", "polypharmacy", "monitoring_gap_count"):
            assert key in row
