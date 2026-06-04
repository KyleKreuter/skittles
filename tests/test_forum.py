"""Broadcast forum: posting, the shared feed, tool wiring and the on/off switch."""

from __future__ import annotations

from skittles.agents.tools import ToolContext, dispatch, tool_specs
from skittles.domain.colors import Color
from skittles.social.forum import MAX_MESSAGE_LENGTH, Forum

from .conftest import make_exchange


def test_post_recent_and_counts():
    forum = Forum()
    forum.post("alice", "hello", round_index=1)
    forum.post("bob", "hi alice", round_index=1)
    forum.post("alice", "selling RED cheap", round_index=2)

    assert [p.agent_id for p in forum.recent(2)] == ["bob", "alice"]
    assert forum.count_by_agent() == {"alice": 2, "bob": 1}


def test_message_is_trimmed_and_capped():
    forum = Forum()
    post = forum.post("alice", "  " + "x" * (MAX_MESSAGE_LENGTH + 50) + "  ", round_index=1)
    assert len(post.message) == MAX_MESSAGE_LENGTH


def test_event_sink_receives_broadcast():
    events = []
    forum = Forum(event_sink=lambda kind, payload: events.append((kind, payload)))
    forum.post("alice", "gm", round_index=3)
    assert events[0][0] == "broadcast"
    assert events[0][1]["agent_id"] == "alice"
    assert events[0][1]["message"] == "gm"


def test_all_agents_share_one_feed():
    ex = make_exchange({"alice": {Color.RED: 10}, "bob": {Color.RED: 10}})
    forum = Forum()
    alice = ToolContext(ex, "alice", round_index=1, rounds_total=5, forum=forum)
    bob = ToolContext(ex, "bob", round_index=1, rounds_total=5, forum=forum)

    res = dispatch(alice, "broadcast", {"message": "I want all the RED"})
    assert res["ok"] is True

    # Bob sees Alice's named message in the shared feed.
    feed = dispatch(bob, "view_forum", {})["posts"]
    assert feed == [{"round": 1, "name": "alice", "message": "I want all the RED"}]


def test_broadcast_rejects_empty_message():
    ex = make_exchange({"a": {Color.RED: 10}, "b": {Color.RED: 10}})
    ctx = ToolContext(ex, "a", round_index=1, rounds_total=5, forum=Forum())
    res = dispatch(ctx, "broadcast", {"message": ""})
    assert "error" in res


def test_broadcast_without_forum_returns_error():
    ex = make_exchange({"a": {Color.RED: 10}, "b": {Color.RED: 10}})
    ctx = ToolContext(ex, "a", round_index=1, rounds_total=5, forum=None)
    res = dispatch(ctx, "broadcast", {"message": "hi"})
    assert "error" in res


def test_tool_specs_toggle_forum():
    with_forum = {t["function"]["name"] for t in tool_specs(forum_enabled=True)}
    without = {t["function"]["name"] for t in tool_specs(forum_enabled=False)}
    assert {"broadcast", "view_forum"} <= with_forum
    assert {"broadcast", "view_forum"}.isdisjoint(without)
