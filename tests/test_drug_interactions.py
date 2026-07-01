"""Tests for drug_interactions.py — synthetic fixtures for precise control."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from drug_interactions import check_interactions
from models import MasterPatient


def _patient(meds):
    p = MasterPatient(patient_id="MP-TEST", first_name="Test", last_name="Patient", dob="1980-01-01", gender="F")
    p.medications = meds
    return p


def _med(desc, start, stop=""):
    return {"drug_description": desc, "start_date": start, "stop_date": stop}


class TestWarfarinNsaid:
    def test_overlapping_warfarin_and_ibuprofen_flags(self):
        meds = [
            _med("Warfarin Sodium 5 MG Oral Tablet", "2020-01-01T00:00:00Z", "2020-06-01T00:00:00Z"),
            _med("Ibuprofen 400 MG Oral Tablet [Ibu]", "2020-03-01T00:00:00Z", "2020-04-01T00:00:00Z"),
        ]
        findings = check_interactions(_patient(meds))
        assert any(f["rule_id"] == "warfarin_nsaid" for f in findings)

    def test_non_overlapping_does_not_flag(self):
        meds = [
            _med("Warfarin Sodium 5 MG Oral Tablet", "2020-01-01T00:00:00Z", "2020-02-01T00:00:00Z"),
            _med("Ibuprofen 400 MG Oral Tablet [Ibu]", "2021-01-01T00:00:00Z", "2021-02-01T00:00:00Z"),
        ]
        findings = check_interactions(_patient(meds))
        assert not any(f["rule_id"] == "warfarin_nsaid" for f in findings)

    def test_ongoing_medication_no_stop_date_still_overlaps(self):
        meds = [
            _med("Warfarin Sodium 5 MG Oral Tablet", "2020-01-01T00:00:00Z", ""),
            _med("Naproxen sodium 220 MG Oral Tablet", "2022-01-01T00:00:00Z", "2022-02-01T00:00:00Z"),
        ]
        findings = check_interactions(_patient(meds))
        assert any(f["rule_id"] == "warfarin_nsaid" for f in findings)


class TestDigoxinVerapamil:
    def test_flags_when_overlapping(self):
        meds = [
            _med("Digoxin 0.125 MG Oral Tablet", "2020-01-01T00:00:00Z", ""),
            _med("verapamil hydrochloride 80 MG Oral Tablet [Calan]", "2020-02-01T00:00:00Z", ""),
        ]
        findings = check_interactions(_patient(meds))
        assert any(f["rule_id"] == "digoxin_verapamil" and f["severity"] == "MAJOR" for f in findings)


class TestOpioidBenzodiazepine:
    def test_flags_oxycodone_and_diazepam(self):
        meds = [
            _med("Abuse-Deterrent 12 HR Oxycodone Hydrochloride 10 MG Extended Release Oral Tablet [Oxycontin]", "2020-01-01T00:00:00Z", ""),
            _med("Diazepam 5 MG Oral Tablet", "2020-01-15T00:00:00Z", "2020-02-01T00:00:00Z"),
        ]
        findings = check_interactions(_patient(meds))
        assert any(f["rule_id"] == "opioid_benzodiazepine" for f in findings)


class TestNoInteractions:
    def test_single_medication_no_findings(self):
        meds = [_med("Lisinopril 10 MG Oral Tablet", "2020-01-01T00:00:00Z", "")]
        assert check_interactions(_patient(meds)) == []

    def test_no_medications_no_findings(self):
        assert check_interactions(_patient([])) == []

    def test_unrelated_drugs_no_findings(self):
        meds = [
            _med("Sodium fluoride 0.0272 MG/MG Oral Gel", "2020-01-01T00:00:00Z", ""),
            _med("Acetaminophen 325 MG Oral Tablet [Tylenol]", "2020-01-01T00:00:00Z", ""),
        ]
        assert check_interactions(_patient(meds)) == []


class TestDeduplication:
    def test_repeated_prescriptions_do_not_duplicate_finding(self):
        meds = [
            _med("Warfarin Sodium 5 MG Oral Tablet", "2020-01-01T00:00:00Z", ""),
            _med("Ibuprofen 400 MG Oral Tablet [Ibu]", "2020-01-15T00:00:00Z", "2020-02-01T00:00:00Z"),
            _med("Ibuprofen 400 MG Oral Tablet [Ibu]", "2020-03-01T00:00:00Z", "2020-04-01T00:00:00Z"),
        ]
        findings = [f for f in check_interactions(_patient(meds)) if f["rule_id"] == "warfarin_nsaid"]
        assert len(findings) == 1


class TestEveryRuleHasACitation:
    def test_all_rules_produce_citation_and_mechanism(self):
        from config import DRUG_INTERACTIONS
        for rule in DRUG_INTERACTIONS:
            assert rule["citation"]
            assert rule["mechanism"]
            assert rule["severity"] in ("MAJOR", "MODERATE")
