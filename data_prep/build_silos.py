"""build_silos.py — one-time data prep script.

Reads MITRE Synthea's official sample synthetic patient export (CSV
format, downloaded from
https://synthetichealth.github.io/synthea-sample-data/downloads/latest/synthea_sample_data_csv_latest.zip
and unpacked into data/raw/) and splits it into four independent CSVs
that simulate real US healthcare fragmentation:

  data/silos/primary_care.csv  -- outpatient conditions (the "problem list")
  data/silos/pharmacy.csv      -- dispensed medications
  data/silos/labs.csv          -- a curated subset of lab results
  data/silos/er.csv            -- hospital-based acute care (ED, inpatient,
                                   urgent care) -- typically a separate
                                   hospital IT system from an independent
                                   outpatient clinic's EHR

Every row is still 100% Synthea-generated synthetic data. What changes is
presentation: no silo carries Synthea's internal patient UUID. Each silo
only knows the patient by name + date of birth, re-captured independently
per silo (as a real registration desk would), with realistic formatting
differences and a small rate of transcription noise. This is the actual
interoperability problem: the US has no national patient identifier
(Congress barred HHS from funding one in the 1998 appropriations act,
and the bar has been renewed every year since), so real health systems
link records the same way this project does -- fuzzy demographic
matching, not a shared key.

A separate data/ground_truth.csv maps every silo record back to the
Synthea patient it came from. The app never reads this file -- it exists
only so tests can measure the entity resolver's precision/recall against
a known-correct answer key.

Run once: `python data_prep/build_silos.py`
"""
from __future__ import annotations

import csv
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import LAB_TEST_MAP, RAW_DATA_DIR, SILO_DATA_DIR

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUND_TRUTH_PATH = os.path.join(BASE_DIR, "data", "ground_truth.csv")

RNG_SEED = 42

# Common legal-name -> nickname substitutions, applied to a deterministic
# subset of patients in the pharmacy silo to simulate a system that
# captured the name the patient goes by rather than the legal name.
NICKNAMES = {
    "robert": "bob", "william": "bill", "richard": "rick",
    "elizabeth": "beth", "margaret": "peg", "katherine": "kate",
    "michael": "mike", "christopher": "chris", "jennifer": "jen",
    "deborah": "debbie", "barbara": "barb", "susan": "sue",
    "patricia": "pat", "thomas": "tom", "james": "jim",
    "charles": "chuck", "daniel": "dan", "matthew": "matt",
    "steven": "steve", "kenneth": "ken", "joseph": "joe",
    "david": "dave", "anthony": "tony", "samuel": "sam",
    "benjamin": "ben", "nicholas": "nick", "andrew": "andy",
}

# Reverse map of LAB_TEST_MAP for fast lookup: raw DESCRIPTION -> test_key
_DESC_TO_KEY = {
    desc: key for key, descs in LAB_TEST_MAP.items() for desc in descs
}

_TRAILING_DIGITS = re.compile(r"\d+$")


def _clean_name(raw: str) -> str:
    """Strip Synthea's numeric uniqueness suffix (e.g. 'Malvina930' -> 'Malvina')."""
    if not raw:
        return raw
    return _TRAILING_DIGITS.sub("", raw).strip()


def _iso_to_mdy(iso_date: str) -> str:
    y, m, d = iso_date.split("-")
    return f"{int(m):02d}/{int(d):02d}/{y}"


def _iso_to_mdy_no_leading_zero(iso_date: str) -> str:
    y, m, d = iso_date.split("-")
    return f"{int(m)}/{int(d)}/{y}"


def _swap_day_month(iso_date: str) -> str:
    """Simulate a classic transcription slip: day/month swapped. Only
    applied when both are <=12 so the result is still a valid date."""
    y, m, d = iso_date.split("-")
    if int(m) <= 12 and int(d) <= 12 and m != d:
        return f"{y}-{d}-{m}"
    return iso_date


def _load_patients() -> dict[str, dict]:
    patients = {}
    with open(os.path.join(RAW_DATA_DIR, "patients.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            patients[row["Id"]] = {
                "first": _clean_name(row["FIRST"]),
                "last": _clean_name(row["LAST"]),
                "dob": row["BIRTHDATE"],
                "gender": row["GENDER"],
                "address": row["ADDRESS"],
                "city": row["CITY"],
                "state": row["STATE"],
                "zip": row["ZIP"],
            }
    return patients


def _make_variant_builder(rng: random.Random, patients: dict[str, dict]):
    """Assign each patient a per-silo name/DOB presentation, decided once
    per patient so the same patient is consistently noisy across all of
    their records in a given silo (a real system wouldn't re-randomize a
    patient's name on every visit)."""
    variants: dict[str, dict[str, dict]] = {}
    for pid in patients:
        first, last, dob = patients[pid]["first"], patients[pid]["last"], patients[pid]["dob"]
        roll = rng.random()

        # primary_care: clean legal name, ISO DOB -- the "reference" record
        pc = {"first": first, "last": last, "dob": dob}

        # pharmacy: ~35% nickname substitution, MM/DD/YYYY DOB
        rx_first = first
        if roll < 0.35 and first.lower() in NICKNAMES:
            rx_first = NICKNAMES[first.lower()].capitalize()
        rx = {"first": rx_first, "last": last, "dob": _iso_to_mdy(dob)}

        # labs: ~10% one-character transcription slip in last name,
        # ~8% day/month swap in DOB (independent rolls)
        lab_last = last
        if rng.random() < 0.10 and len(last) > 3:
            i = rng.randrange(1, len(last) - 1)
            lab_last = last[:i] + last[i + 1] + last[i] + last[i + 2:]
        lab_dob = dob
        if rng.random() < 0.08:
            lab_dob = _swap_day_month(dob)
        labs = {"first": first, "last": lab_last, "dob": lab_dob}

        # er: rushed intake -- no leading zeros in DOB, and ~15% middle-
        # initial-only first name never applies here since Synthea FIRST
        # is already a single given name; instead vary case/formatting
        er = {"first": first, "last": last, "dob": _iso_to_mdy_no_leading_zero(dob)}

        variants[pid] = {"primary_care": pc, "pharmacy": rx, "labs": labs, "er": er}
    return variants


def build() -> None:
    os.makedirs(SILO_DATA_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(GROUND_TRUTH_PATH), exist_ok=True)
    rng = random.Random(RNG_SEED)

    patients = _load_patients()
    variants = _make_variant_builder(rng, patients)

    ground_truth_rows: list[tuple[str, str, str]] = []  # (silo, record_id, synthea_patient_id)

    # --- primary_care.csv (conditions) ---
    pc_path = os.path.join(SILO_DATA_DIR, "primary_care.csv")
    with open(os.path.join(RAW_DATA_DIR, "conditions.csv"), encoding="utf-8") as f_in, \
         open(pc_path, "w", newline="", encoding="utf-8") as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.writer(f_out)
        writer.writerow([
            "pc_record_id", "first_name", "last_name", "dob", "gender",
            "address", "city", "state", "zip",
            "condition_code", "condition_description", "onset_date", "resolved_date",
        ])
        n = 0
        for row in reader:
            pid = row["PATIENT"]
            if pid not in patients:
                continue
            n += 1
            rec_id = f"PC-{n:06d}"
            v = variants[pid]["primary_care"]
            p = patients[pid]
            writer.writerow([
                rec_id, v["first"], v["last"], v["dob"], p["gender"],
                p["address"], p["city"], p["state"], p["zip"],
                row["CODE"], row["DESCRIPTION"], row["START"], row["STOP"],
            ])
            ground_truth_rows.append(("primary_care", rec_id, pid))

    # --- pharmacy.csv (medications) ---
    rx_path = os.path.join(SILO_DATA_DIR, "pharmacy.csv")
    with open(os.path.join(RAW_DATA_DIR, "medications.csv"), encoding="utf-8") as f_in, \
         open(rx_path, "w", newline="", encoding="utf-8") as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.writer(f_out)
        writer.writerow([
            "rx_record_id", "first_name", "last_name", "dob", "gender",
            "drug_code", "drug_description", "start_date", "stop_date",
        ])
        n = 0
        for row in reader:
            pid = row["PATIENT"]
            if pid not in patients:
                continue
            n += 1
            rec_id = f"RX-{n:06d}"
            v = variants[pid]["pharmacy"]
            p = patients[pid]
            writer.writerow([
                rec_id, v["first"], v["last"], v["dob"], p["gender"],
                row["CODE"], row["DESCRIPTION"], row["START"], row["STOP"],
            ])
            ground_truth_rows.append(("pharmacy", rec_id, pid))

    # --- labs.csv (curated lab observations only) ---
    labs_path = os.path.join(SILO_DATA_DIR, "labs.csv")
    with open(os.path.join(RAW_DATA_DIR, "observations.csv"), encoding="utf-8") as f_in, \
         open(labs_path, "w", newline="", encoding="utf-8") as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.writer(f_out)
        writer.writerow([
            "lab_record_id", "first_name", "last_name", "dob", "gender",
            "test_key", "test_date", "value", "units",
        ])
        n = 0
        for row in reader:
            if row["CATEGORY"] != "laboratory":
                continue
            test_key = _DESC_TO_KEY.get(row["DESCRIPTION"])
            if test_key is None:
                continue
            pid = row["PATIENT"]
            if pid not in patients:
                continue
            n += 1
            rec_id = f"LAB-{n:06d}"
            v = variants[pid]["labs"]
            p = patients[pid]
            writer.writerow([
                rec_id, v["first"], v["last"], v["dob"], p["gender"],
                test_key, row["DATE"], row["VALUE"], row["UNITS"],
            ])
            ground_truth_rows.append(("labs", rec_id, pid))

    # --- er.csv (hospital-based acute care: ED + inpatient + urgent care) ---
    er_path = os.path.join(SILO_DATA_DIR, "er.csv")
    acute_classes = {"emergency", "inpatient", "urgentcare"}
    with open(os.path.join(RAW_DATA_DIR, "encounters.csv"), encoding="utf-8") as f_in, \
         open(er_path, "w", newline="", encoding="utf-8") as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.writer(f_out)
        writer.writerow([
            "er_record_id", "first_name", "last_name", "dob", "gender",
            "encounter_class", "visit_date", "discharge_date",
            "length_of_stay_days", "chief_complaint",
        ])
        n = 0
        for row in reader:
            if row["ENCOUNTERCLASS"] not in acute_classes:
                continue
            pid = row["PATIENT"]
            if pid not in patients:
                continue
            n += 1
            rec_id = f"ER-{n:06d}"
            v = variants[pid]["er"]
            p = patients[pid]
            start_date = row["START"][:10]
            stop_date = row["STOP"][:10]
            los = (
                _days_between(start_date, stop_date)
                if start_date and stop_date else 0
            )
            writer.writerow([
                rec_id, v["first"], v["last"], v["dob"], p["gender"],
                row["ENCOUNTERCLASS"], start_date, stop_date, los,
                row["DESCRIPTION"],
            ])
            ground_truth_rows.append(("er", rec_id, pid))

    with open(GROUND_TRUTH_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["silo", "record_id", "synthea_patient_id"])
        writer.writerows(ground_truth_rows)

    print(f"primary_care.csv: {sum(1 for r in ground_truth_rows if r[0]=='primary_care')} rows")
    print(f"pharmacy.csv:     {sum(1 for r in ground_truth_rows if r[0]=='pharmacy')} rows")
    print(f"labs.csv:         {sum(1 for r in ground_truth_rows if r[0]=='labs')} rows")
    print(f"er.csv:           {sum(1 for r in ground_truth_rows if r[0]=='er')} rows")
    print(f"{len(patients)} unique patients across all silos")


def _days_between(iso_a: str, iso_b: str) -> int:
    from datetime import date
    ya, ma, da = (int(x) for x in iso_a.split("-"))
    yb, mb, db = (int(x) for x in iso_b.split("-"))
    return (date(yb, mb, db) - date(ya, ma, da)).days


if __name__ == "__main__":
    build()
