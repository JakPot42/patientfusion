"""screenings.py — overdue population-screening flags and drug-specific
monitoring-gap flags.

SCREENING_RULES encodes real USPSTF / ACC-AHA population guidelines
(config.py). MONITORING_REQUIREMENTS encodes drug-specific monitoring
intervals from real clinical guidance -- this is the rule that answers
"show me everyone on warfarin without a recent INR check."
"""
from __future__ import annotations

from datetime import date

from config import MONITORING_REQUIREMENTS, SCREENING_RULES
from dates import age_on, parse_date
from entity_resolver import parse_dob
from models import MasterPatient


def most_recent_lab_date(patient: MasterPatient, test_key: str) -> date | None:
    dates = [
        parse_date(lab.get("test_date"))
        for lab in patient.labs
        if lab.get("test_key") == test_key
    ]
    dates = [d for d in dates if d is not None]
    return max(dates) if dates else None


def check_overdue_screenings(patient: MasterPatient, as_of: date) -> list[dict]:
    dob = parse_dob(patient.dob)
    if dob is None:
        return []
    age = age_on(dob, as_of)
    findings = []
    for rule in SCREENING_RULES:
        if age < rule["min_age"]:
            continue
        if rule["max_age"] is not None and age > rule["max_age"]:
            continue
        last = most_recent_lab_date(patient, rule["test_key"])
        days_since = (as_of - last).days if last else None
        overdue = last is None or days_since > rule["interval_days"]
        if overdue:
            findings.append({
                "rule_id": rule["id"],
                "label": rule["label"],
                "last_test_date": last.isoformat() if last else None,
                "days_since_last_test": days_since,
                "interval_days": rule["interval_days"],
                "citation": rule["citation"],
            })
    return findings


def _active_drugs(patient: MasterPatient) -> list[dict]:
    return patient.medications


def check_monitoring_gaps(patient: MasterPatient, as_of: date) -> list[dict]:
    findings = []
    for req in MONITORING_REQUIREMENTS:
        on_drug = [
            m for m in patient.medications
            if req["drug"].lower() in (m.get("drug_description") or "").lower()
        ]
        if not on_drug:
            continue
        last = most_recent_lab_date(patient, req["test_key"])
        days_since = (as_of - last).days if last else None
        overdue = last is None or days_since > req["interval_days"]
        if overdue:
            findings.append({
                "rule_id": req["id"],
                "drug": req["drug"],
                "required_test": req["test_key"],
                "last_test_date": last.isoformat() if last else None,
                "days_since_last_test": days_since,
                "interval_days": req["interval_days"],
                "citation": req["citation"],
            })
    return findings
