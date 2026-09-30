from datetime import date

import pytest

from chessstats.pipeline import display_name, range_start


@pytest.mark.parametrize(
    "range_key, today, expected",
    [
        ("year", date(2026, 9, 28), (2026, 1)),
        ("year", date(2026, 1, 1), (2026, 1)),
        ("12months", date(2026, 9, 28), (2025, 10)),
        ("12months", date(2026, 1, 5), (2025, 2)),
        ("12months", date(2026, 12, 31), (2026, 1)),
        ("all", date(2026, 9, 28), None),
    ],
)
def test_range_start(range_key, today, expected):
    assert range_start(range_key, today) == expected


def test_unknown_range():
    with pytest.raises(ValueError):
        range_start("decade", date(2026, 1, 1))


def test_display_name_uses_chess_com_capitalisation():
    raw = [{"white": {"username": "Someone"}, "black": {"username": "LegendaryBean123"}}]
    assert display_name(raw, "legendarybean123") == "LegendaryBean123"
    assert display_name([], "legendarybean123") == "legendarybean123"
