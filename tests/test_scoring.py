"""Scoring: highest single-color count wins, with documented tie-breaks."""

from __future__ import annotations

from skittles.domain.colors import Color
from skittles.sim.scoring import score_run

from .conftest import make_exchange


def test_winner_has_highest_single_color_count():
    ex = make_exchange(
        {
            "a": {Color.RED: 70, Color.BLUE: 10},
            "b": {Color.GREEN: 40, Color.YELLOW: 40},
            "c": {Color.BLUE: 55},
        }
    )
    board = score_run(ex)
    assert board.winner.agent_id == "a"
    assert board.winner.leading_color == Color.RED
    assert board.winner.leading_count == 70
    assert [s.agent_id for s in board.ranking] == ["a", "c", "b"]


def test_tie_breaks_on_grand_total_then_id():
    ex = make_exchange(
        {
            "a": {Color.RED: 30, Color.BLUE: 5},   # leading 30, total 35
            "b": {Color.RED: 30, Color.BLUE: 20},  # leading 30, total 50 -> wins tie
        }
    )
    board = score_run(ex)
    assert board.winner.agent_id == "b"


def test_score_after_cancel_counts_only_available():
    # Reserved skittles (open order) are excluded until cancelled/settled.
    ex = make_exchange({"solo": {Color.RED: 40, Color.BLUE: 10}})
    from skittles.market.order import Side

    ex.place_order("solo", Side.SELL, Color.RED, Color.BLUE, quantity=15, price=1)
    board_mid = score_run(ex)
    assert board_mid.winner.leading_count == 25  # 40 - 15 reserved

    ex.cancel_all("solo")
    board_end = score_run(ex)
    assert board_end.winner.leading_count == 40
