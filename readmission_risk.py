"""readmission_risk.py — simplified LACE readmission risk score.

LACE (van Walraven et al. 2010, CMAJ — see config.LACE_CITATION) is a
real, validated instrument, not an invented scoring scheme. The
simplification made here (Comorbidity as a presence-count over a curated
Charlson-category keyword list, rather than the full weighted Charlson
Comorbidity Index) is disclosed in config.py and the README, not hidden.

  L - Length of stay of the index encounter
  A - Acute admission (index encounter arrived via emergency)
  C - Comorbidity count (Charlson-category conditions on record)
  E - number of ED/urgent-care/inpatient encounters in prior 6 months
"""
from __future__ import annotations

from datetime import date, timedelta

from config import (
    CHARLSON_KEYWORDS,
    LACE_ACUTE_ADMISSION_POINTS,
    LACE_COMORBIDITY_POINTS_CAP,
    LACE_ED_VISIT_LOOKBACK_DAYS,
    LACE_ED_VISIT_POINTS_CAP,
    LACE_LOS_POINTS,
    LACE_LOS_POINTS_MAX,
    LACE_RISK_TIER_DEFAULT,
    LACE_RISK_TIERS,
)
from dates import parse_date
from models import MasterPatient


def _los_points(los_days: int) -> int:
    for max_days, points in LACE_LOS_POINTS:
        if los_days <= max_days:
            return points
    return LACE_LOS_POINTS_MAX


def _comorbidity_count(patient: MasterPatient) -> int:
    hits = set()
    for cond in patient.conditions:
        desc = (cond.get("condition_description") or "").lower()
        for kw in CHARLSON_KEYWORDS:
            if kw in desc:
                hits.add(kw)
    return len(hits)


def _comorbidity_points(count: int) -> int:
    return min(count, LACE_COMORBIDITY_POINTS_CAP)


def _tier_for_score(score: int) -> str:
    for ceiling, tier in LACE_RISK_TIERS:
        if score <= ceiling:
            return tier
    return LACE_RISK_TIER_DEFAULT


def compute_lace_score(patient: MasterPatient, as_of: date | None = None) -> dict | None:
    """Uses the patient's most recent ER-silo encounter (by visit_date) as
    the index event. Returns None if the patient has no ER-silo encounters
    -- LACE is only meaningful relative to an acute-care admission."""
    if not patient.er_visits:
        return None

    visits = sorted(
        patient.er_visits,
        key=lambda v: parse_date(v.get("visit_date")) or date.min,
    )
    index = visits[-1]
    index_date = parse_date(index.get("visit_date"))
    if index_date is None:
        return None
    if as_of is None:
        as_of = index_date

    los_days = int(index.get("length_of_stay_days") or 0)
    is_acute = index.get("encounter_class") == "emergency"

    lookback_start = index_date - timedelta(days=LACE_ED_VISIT_LOOKBACK_DAYS)
    prior_visits = [
        v for v in visits[:-1]
        if (d := parse_date(v.get("visit_date"))) and lookback_start <= d < index_date
    ]

    comorbidity_count = _comorbidity_count(patient)

    l_pts = _los_points(los_days)
    a_pts = LACE_ACUTE_ADMISSION_POINTS if is_acute else 0
    c_pts = _comorbidity_points(comorbidity_count)
    e_pts = min(len(prior_visits), LACE_ED_VISIT_POINTS_CAP)

    total = l_pts + a_pts + c_pts + e_pts

    return {
        "index_visit_date": index_date.isoformat(),
        "index_encounter_class": index.get("encounter_class"),
        "length_of_stay_days": los_days,
        "l_points": l_pts,
        "is_acute_admission": is_acute,
        "a_points": a_pts,
        "comorbidity_count": comorbidity_count,
        "c_points": c_pts,
        "prior_ed_visits_6mo": len(prior_visits),
        "e_points": e_pts,
        "lace_score": total,
        "risk_tier": _tier_for_score(total),
    }
