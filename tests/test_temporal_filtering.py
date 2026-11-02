"""Timestamp parsing for decks: the formats the corpus actually contains."""

from __future__ import annotations

from datetime import datetime

from ml.utils.temporal_filtering import get_deck_timestamp, parse_timestamp


def test_iso_and_zulu():
    assert parse_timestamp("2024-05-01") == datetime(2024, 5, 1)
    assert parse_timestamp("2026-01-30T12:00:00Z").year == 2026


def test_ordinal_day_month_name():
    """12,000 Pokemon decks use "13th February 2026"."""
    assert parse_timestamp("13th February 2026") == datetime(2026, 2, 13)
    assert parse_timestamp("1st January 2020") == datetime(2020, 1, 1)
    assert parse_timestamp("22nd March 2021") == datetime(2021, 3, 22)


def test_month_name_forms():
    assert parse_timestamp("January 9, 1999") == datetime(1999, 1, 9)
    assert parse_timestamp("9 January 1999") == datetime(1999, 1, 9)


def test_slash_forms():
    assert parse_timestamp("1999/01/09") == datetime(1999, 1, 9)


def test_invalid_is_none_not_wrong():
    # 2025-22-02 has month 22: it must not be coerced into something plausible.
    assert parse_timestamp("2025-22-02") is None
    assert parse_timestamp("") is None
    assert parse_timestamp(None) is None


def test_deck_keys():
    assert get_deck_timestamp({"created_at": "2024-01-02"}) == datetime(2024, 1, 2)
    # scraped_at was missing from the key list, so dated decks were dropped.
    assert get_deck_timestamp({"scraped_at": "2024-05-01"}) == datetime(2024, 5, 1)
    assert get_deck_timestamp({"published_at": "2023-11-30"}) == datetime(2023, 11, 30)


def test_deck_falls_through_unparseable_keys():
    """A bad created_at must not hide a good scraped_at."""
    deck = {"created_at": "not a date", "scraped_at": "2024-05-01"}
    assert get_deck_timestamp(deck) == datetime(2024, 5, 1)


def test_undated_deck_is_none():
    assert get_deck_timestamp({"name": "no date here"}) is None
