"""Tests for entity_resolver.py — all pure logic, no network or DB."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from entity_resolver import (
    dob_match,
    name_similarity,
    normalize_name,
    parse_dob,
    resolve_patients,
)


class TestNormalizeName:
    def test_basic(self):
        assert normalize_name("Jane", "Doe") == "jane doe"

    def test_lowercases(self):
        assert normalize_name("JANE", "DOE") == "jane doe"

    def test_strips_punctuation(self):
        assert normalize_name("Jane-Ann", "O'Doe") == "jane ann o doe"

    def test_empty(self):
        assert normalize_name("", "") == ""

    def test_none_safe(self):
        assert normalize_name(None, None) == ""


class TestNameSimilarity:
    def test_identical(self):
        a = {"first_name": "Jane", "last_name": "Doe"}
        b = {"first_name": "Jane", "last_name": "Doe"}
        assert name_similarity(a, b) == 100.0

    def test_empty_names(self):
        a = {"first_name": "", "last_name": ""}
        b = {"first_name": "Jane", "last_name": "Doe"}
        assert name_similarity(a, b) == 0.0

    def test_completely_different(self):
        a = {"first_name": "Jane", "last_name": "Doe"}
        b = {"first_name": "Zzyx", "last_name": "Qorp"}
        assert name_similarity(a, b) < 50

    def test_one_char_typo_high(self):
        a = {"first_name": "Jamel", "last_name": "Pagac"}
        b = {"first_name": "Jamel", "last_name": "Pagca"}
        assert name_similarity(a, b) >= 85

    def test_word_order_reversal(self):
        a = {"first_name": "Jane", "last_name": "Doe"}
        b = {"first_name": "Doe", "last_name": "Jane"}
        assert name_similarity(a, b) == 100.0


class TestParseDob:
    def test_iso_format(self):
        d = parse_dob("2001-12-29")
        assert (d.year, d.month, d.day) == (2001, 12, 29)

    def test_slash_format(self):
        d = parse_dob("12/29/2001")
        assert (d.year, d.month, d.day) == (2001, 12, 29)

    def test_slash_no_leading_zero(self):
        d = parse_dob("1/5/1980")
        assert (d.year, d.month, d.day) == (1980, 1, 5)

    def test_empty_string(self):
        assert parse_dob("") is None

    def test_garbage(self):
        assert parse_dob("not-a-date") is None


class TestDobMatch:
    def test_exact_match_different_formats(self):
        a = {"dob": "2001-12-29"}
        b = {"dob": "12/29/2001"}
        assert dob_match(a, b) == "exact"

    def test_day_month_swap_is_near(self):
        a = {"dob": "1963-08-09"}
        b = {"dob": "1963-09-08"}
        assert dob_match(a, b) == "near"

    def test_off_by_one_day_is_near(self):
        a = {"dob": "1980-05-10"}
        b = {"dob": "1980-05-11"}
        assert dob_match(a, b) == "near"

    def test_different_year_is_none(self):
        a = {"dob": "1980-05-10"}
        b = {"dob": "1981-05-10"}
        assert dob_match(a, b) == "none"

    def test_missing_dob_is_none(self):
        a = {"dob": ""}
        b = {"dob": "1980-05-10"}
        assert dob_match(a, b) == "none"


class TestResolvePatients:
    def _rec(self, first, last, dob, gender="F", silo="primary_care", index=0):
        return {
            "first_name": first, "last_name": last, "dob": dob,
            "gender": gender, "silo": silo, "_index": index,
        }

    def test_exact_duplicate_merges_automatically(self):
        records = [
            self._rec("Jane", "Doe", "1980-01-01", silo="primary_care"),
            self._rec("Jane", "Doe", "1980-01-01", silo="pharmacy"),
        ]
        masters, assignment = resolve_patients(records)
        assert len(masters) == 1
        assert assignment[0] == assignment[1]

    def test_different_dob_never_merges_even_with_adjudicator(self):
        records = [
            self._rec("Jane", "Doe", "1980-01-01"),
            self._rec("Jane", "Doe", "1955-06-15"),
        ]
        masters, _ = resolve_patients(records, adjudicator=lambda a, b: True)
        assert len(masters) == 2

    def test_completely_distinct_patients_stay_separate(self):
        records = [
            self._rec("Jane", "Doe", "1980-01-01"),
            self._rec("Bob", "Smith", "1990-03-03"),
        ]
        masters, _ = resolve_patients(records)
        assert len(masters) == 2

    def test_ambiguous_band_unmerged_without_adjudicator(self):
        # High name similarity (one-letter transposition typo) but only a
        # DOB *near* match (day/month transposed, not exact): must NOT
        # auto-merge without an adjudicator (missed merge is the safe
        # failure mode; auto-merge requires an exact DOB match).
        records = [
            self._rec("Ira", "Jaskolski", "1963-08-09"),
            self._rec("Ira", "Jaskolsik", "1963-09-08"),
        ]
        masters, _ = resolve_patients(records)
        assert len(masters) == 2

    def test_ambiguous_band_merges_when_adjudicator_says_yes(self):
        records = [
            self._rec("Ira", "Jaskolski", "1963-08-09"),
            self._rec("Ira", "Jaskolsik", "1963-09-08"),
        ]
        masters, assignment = resolve_patients(records, adjudicator=lambda a, b: True)
        assert len(masters) == 1

    def test_shared_surname_and_dob_different_first_name_stays_split_by_default(self):
        # The real edge case found in the demo dataset: two distinct
        # people can share a surname AND a birthdate by coincidence.
        records = [
            self._rec("Anderson", "Senger", "1969-05-31", gender="M"),
            self._rec("Shon", "Senger", "1969-05-31", gender="M"),
        ]
        masters, _ = resolve_patients(records)
        assert len(masters) == 2

    def test_adjudicator_called_at_most_once_per_pair_memoized(self):
        calls = []

        def counting_adjudicator(a, b):
            calls.append((a["first_name"], b["first_name"]))
            return True

        # Near (not exact) DOB match forces every one of these into the
        # adjudication band rather than auto-merging.
        records = [
            self._rec("Ira", "Jaskolski", "1963-08-09", silo="primary_care"),
            self._rec("Ira", "Jaskolsik", "1963-09-08", silo="pharmacy"),
            self._rec("Ira", "Jaskolsik", "1963-09-08", silo="labs"),
        ]
        resolve_patients(records, adjudicator=counting_adjudicator)
        # The repeated identical pair should hit the memo, not re-ask
        assert len(calls) <= 2

    def test_gap_fill_does_not_overwrite_known_field(self):
        records = [
            self._rec("Jane", "Doe", "1980-01-01", gender="F"),
            self._rec("Jane", "Doe", "1980-01-01", gender=""),
        ]
        masters, _ = resolve_patients(records)
        assert masters[0]["gender"] == "F"
