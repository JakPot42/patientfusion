"""drug_interactions.py — deterministic drug-drug interaction checker.

Every rule in config.DRUG_INTERACTIONS cites a real FDA Drug Safety
Communication or peer-reviewed systematic review (see config.py). This
module only matches medication text and overlapping active date ranges;
it never invents a severity or a threshold that isn't in that cited
source.
"""
from __future__ import annotations

from datetime import date

from config import DRUG_INTERACTIONS
from dates import parse_date
from models import MasterPatient

FAR_FUTURE = date(2100, 1, 1)


def _matches_any(description: str, keywords: list[str]) -> bool:
    desc = description.lower()
    return any(kw.lower() in desc for kw in keywords)


def _active_range(med: dict) -> tuple[date | None, date]:
    start = parse_date(med.get("start_date"))
    stop = parse_date(med.get("stop_date")) or FAR_FUTURE
    return start, stop


def _overlaps(a: dict, b: dict) -> bool:
    a_start, a_stop = _active_range(a)
    b_start, b_stop = _active_range(b)
    if a_start is None or b_start is None:
        return False
    return a_start <= b_stop and b_start <= a_stop


def check_interactions(patient: MasterPatient) -> list[dict]:
    """Returns one finding per (rule, med_a, med_b) triple where the
    patient had both drugs active at an overlapping time."""
    findings = []
    seen: set[tuple[str, str, str]] = set()
    for rule in DRUG_INTERACTIONS:
        a_keywords = rule.get("drug_a_any") or [rule["drug_a"]]
        b_keywords = rule["drug_b_any"]
        meds_a = [m for m in patient.medications if _matches_any(m.get("drug_description", ""), a_keywords)]
        meds_b = [m for m in patient.medications if _matches_any(m.get("drug_description", ""), b_keywords)]
        for med_a in meds_a:
            for med_b in meds_b:
                if med_a is med_b:
                    continue
                if not _overlaps(med_a, med_b):
                    continue
                key = (rule["id"], med_a.get("drug_description", ""), med_b.get("drug_description", ""))
                if key in seen:
                    continue
                seen.add(key)
                findings.append({
                    "rule_id": rule["id"],
                    "severity": rule["severity"],
                    "drug_a": med_a.get("drug_description"),
                    "drug_b": med_b.get("drug_description"),
                    "mechanism": rule["mechanism"],
                    "citation": rule["citation"],
                })
    return findings
