"""polypharmacy.py — deterministic polypharmacy detection.

Definition and threshold are cited (config.POLYPHARMACY_CITATION), not
invented: 5+ concurrently active medications is the most commonly used
definition in the geriatric pharmacology literature.
"""
from __future__ import annotations

from datetime import date

from config import POLYPHARMACY_THRESHOLD
from dates import parse_date
from models import MasterPatient

FAR_FUTURE = date(2100, 1, 1)


def active_medications_on(patient: MasterPatient, as_of: date) -> list[dict]:
    active = []
    for med in patient.medications:
        start = parse_date(med.get("start_date"))
        stop = parse_date(med.get("stop_date")) or FAR_FUTURE
        if start is not None and start <= as_of <= stop:
            active.append(med)
    return active


def check_polypharmacy(patient: MasterPatient, as_of: date) -> dict:
    active = active_medications_on(patient, as_of)
    distinct_drugs = {m.get("drug_description") for m in active}
    return {
        "as_of": as_of.isoformat(),
        "active_medication_count": len(distinct_drugs),
        "is_polypharmacy": len(distinct_drugs) >= POLYPHARMACY_THRESHOLD,
        "threshold": POLYPHARMACY_THRESHOLD,
        "active_medications": sorted(distinct_drugs),
    }
