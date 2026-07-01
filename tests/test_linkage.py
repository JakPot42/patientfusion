"""Tests for linkage.py — including an accuracy check against the real
answer key (data/ground_truth.csv) produced by data_prep/build_silos.py.
The app itself never reads ground_truth.csv; only this test does, to
measure the entity resolver's precision/recall on real fragmented data.
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from claude_adjudicator import adjudicate
from config import BASE_DIR
from entity_resolver import resolve_patients
from linkage import SILO_ORDER, build_master_patients
from silo_loader import group_by_identity, load_silo

GROUND_TRUTH_PATH = os.path.join(BASE_DIR, "data", "ground_truth.csv")


def _load_ground_truth_by_silo_row():
    gt = defaultdict(dict)
    counters = defaultdict(int)
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            silo = row["silo"]
            gt[silo][counters[silo]] = row["synthea_patient_id"]
            counters[silo] += 1
    return gt


def _resolve_with_ground_truth(adjudicator):
    silo_rows, silo_groups, raw_records = {}, {}, []
    for silo in SILO_ORDER:
        rows = load_silo(silo)
        groups = group_by_identity(rows)
        silo_rows[silo] = rows
        silo_groups[silo] = groups
        for i, g in enumerate(groups):
            raw_records.append({**g, "silo": silo, "_index": i})

    masters, assignment = resolve_patients(raw_records, adjudicator)

    gt_by_silo_row = _load_ground_truth_by_silo_row()
    true_pid_for_record = []
    for rec in raw_records:
        silo = rec["silo"]
        group = silo_groups[silo][rec["_index"]]
        true_ids = {gt_by_silo_row[silo][ri] for ri in group["row_indices"]}
        true_pid_for_record.append(true_ids)

    master_to_true_ids = defaultdict(set)
    for idx, master_idx in assignment.items():
        master_to_true_ids[master_idx] |= true_pid_for_record[idx]

    wrong_merges = {m: ids for m, ids in master_to_true_ids.items() if len(ids) > 1}

    true_id_to_masters = defaultdict(set)
    for master_idx, ids in master_to_true_ids.items():
        for tid in ids:
            true_id_to_masters[tid].add(master_idx)
    over_splits = {t: ms for t, ms in true_id_to_masters.items() if len(ms) > 1}

    return masters, wrong_merges, over_splits


class TestLinkageAgainstGroundTruth:
    def test_no_adjudicator_never_wrongly_merges_distinct_patients(self):
        """The dangerous failure mode (blending two real patients'
        histories) must never happen, even with no adjudicator at all."""
        _, wrong_merges, _ = _resolve_with_ground_truth(None)
        assert len(wrong_merges) == 0

    def test_no_adjudicator_may_over_split_but_stays_bounded(self):
        _, _, over_splits = _resolve_with_ground_truth(None)
        # Missed merges (safe failure mode) are expected without an
        # adjudicator, but should be a small minority of ~113 patients.
        assert 0 < len(over_splits) < 20

    def test_demo_adjudicator_never_wrongly_merges(self):
        _, wrong_merges, _ = _resolve_with_ground_truth(adjudicate)
        assert len(wrong_merges) == 0

    def test_demo_adjudicator_resolves_the_true_patient_count(self):
        masters, _, over_splits = _resolve_with_ground_truth(adjudicate)
        true_patient_count = len({
            pid for row in _load_ground_truth_by_silo_row().values() for pid in row.values()
        })
        assert len(over_splits) == 0
        assert len(masters) == true_patient_count


class TestBuildMasterPatients:
    def test_returns_patients_and_stats(self):
        patients, stats = build_master_patients(adjudicate)
        assert len(patients) == stats["master_patients"]
        assert stats["multi_silo_patients"] + stats["single_silo_patients"] == len(patients)

    def test_patient_ids_are_sequential_and_unique(self):
        patients, _ = build_master_patients(adjudicate)
        ids = [p.patient_id for p in patients]
        assert len(ids) == len(set(ids))
        assert ids[0] == "MP-00001"

    def test_multi_silo_patient_has_records_from_each_silo(self):
        patients, _ = build_master_patients(adjudicate)
        full = next(p for p in patients if len(p.silos_present) == 4)
        assert full.conditions and full.medications and full.labs and full.er_visits

    def test_name_variants_capture_cross_silo_noise(self):
        patients, _ = build_master_patients(adjudicate)
        noisy = [p for p in patients if len(p.name_variants) > 1]
        assert len(noisy) > 0
