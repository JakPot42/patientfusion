"""Tests for claude_adjudicator.py — DEMO_MODE path only (no network)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from claude_adjudicator import _demo_adjudicator, adjudicate


class TestDemoAdjudicator:
    def test_similar_first_names_merge(self):
        a = {"first_name": "Rocco", "last_name": "Zulauf", "dob": "1973-01-11", "gender": "M"}
        b = {"first_name": "Rocco", "last_name": "Zualuf", "dob": "1973-01-11", "gender": "M"}
        assert _demo_adjudicator(a, b) is True

    def test_different_first_names_do_not_merge(self):
        a = {"first_name": "Anderson", "last_name": "Senger", "dob": "1969-05-31", "gender": "M"}
        b = {"first_name": "Shon", "last_name": "Senger", "dob": "1969-05-31", "gender": "M"}
        assert _demo_adjudicator(a, b) is False

    def test_missing_first_name_does_not_merge(self):
        a = {"first_name": "", "last_name": "Senger", "dob": "1969-05-31", "gender": "M"}
        b = {"first_name": "Shon", "last_name": "Senger", "dob": "1969-05-31", "gender": "M"}
        assert _demo_adjudicator(a, b) is False


class TestAdjudicateUsesDemoModeByDefault:
    def test_public_entry_point_matches_demo_heuristic(self):
        a = {"first_name": "Rocco", "last_name": "Zulauf", "dob": "1973-01-11", "gender": "M"}
        b = {"first_name": "Rocco", "last_name": "Zualuf", "dob": "1973-01-11", "gender": "M"}
        assert adjudicate(a, b) == _demo_adjudicator(a, b)
