"""Tests for dates.py."""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dates import age_on, parse_date


class TestParseDate:
    def test_plain_iso_date(self):
        assert parse_date("2020-06-01") == date(2020, 6, 1)

    def test_iso_datetime_with_t(self):
        assert parse_date("2020-06-01T13:57:52Z") == date(2020, 6, 1)

    def test_none_input(self):
        assert parse_date(None) is None

    def test_empty_string(self):
        assert parse_date("") is None

    def test_garbage_input(self):
        assert parse_date("not-a-date") is None


class TestAgeOn:
    def test_birthday_already_passed_this_year(self):
        assert age_on(date(1980, 1, 1), date(2020, 6, 1)) == 40

    def test_birthday_not_yet_this_year(self):
        assert age_on(date(1980, 12, 31), date(2020, 6, 1)) == 39

    def test_exact_birthday(self):
        assert age_on(date(1980, 6, 1), date(2020, 6, 1)) == 40
