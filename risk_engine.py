"""risk_engine.py — aggregates every decision-layer rule for one patient.

Pure orchestration: each check is independently deterministic (see
drug_interactions.py, polypharmacy.py, screenings.py, readmission_risk.py).
This module just calls them and packages the results together for the
dashboard and CLI.
"""
from __future__ import annotations

from datetime import date

from drug_interactions import check_interactions
from models import MasterPatient
from polypharmacy import check_polypharmacy
from readmission_risk import compute_lace_score
from screenings import check_monitoring_gaps, check_overdue_screenings


def evaluate_patient(patient: MasterPatient, as_of: date | None = None) -> dict:
    if as_of is None:
        as_of = date.today()
    return {
        "drug_interactions": check_interactions(patient),
        "polypharmacy": check_polypharmacy(patient, as_of),
        "overdue_screenings": check_overdue_screenings(patient, as_of),
        "monitoring_gaps": check_monitoring_gaps(patient, as_of),
        "readmission_risk": compute_lace_score(patient, as_of),
    }


def population_heatmap_rows(patients: list[MasterPatient], as_of: date | None = None) -> list[dict]:
    if as_of is None:
        as_of = date.today()
    rows = []
    for p in patients:
        findings = evaluate_patient(p, as_of)
        lace = findings["readmission_risk"]
        rows.append({
            "patient_id": p.patient_id,
            "name": p.full_name,
            "lace_score": lace["lace_score"] if lace else None,
            "risk_tier": lace["risk_tier"] if lace else None,
            "interaction_count": len(findings["drug_interactions"]),
            "polypharmacy": findings["polypharmacy"]["is_polypharmacy"],
            "monitoring_gap_count": len(findings["monitoring_gaps"]),
        })
    return rows
