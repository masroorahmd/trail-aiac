"""Unit tests for the comment-listing condenser.

A `list_comments` call is the single biggest read a persona makes, and
because a handover always starts with a fresh context it is paid on every
turn. `_condense_comments` is what keeps it affordable — and what must not
silently swallow the one comment the pickup step was looking for.
"""

from plane_extras_mcp.server import _condense_comments, _html_to_text


def _comment(html: str, **extra):
    return {
        "id": "c-1",
        "created_at": "2026-08-20T10:00:00+02:00",
        "workspace": "w-1",
        "project": "p-1",
        "issue": "i-1",
        "actor": "a-1",
        "comment_html": html,
        "comment_stripped": "",
        "comment_json": {"type": "doc", "content": [{"big": "payload"}]},
        **extra,
    }


def test_html_becomes_readable_text():
    text = _html_to_text(
        "<h2>Security review</h2><p>Two findings.</p>"
        "<ul><li>SR-1 medium</li><li>SR-2 low</li></ul>"
    )
    assert text.startswith("## Security review")
    assert "Two findings." in text
    assert "- SR-1 medium" in text
    assert "<" not in text


def test_entities_are_decoded_not_left_raw():
    assert _html_to_text("<p>a &lt; b &amp;&amp; c &gt; d</p>") == "a < b && c > d"


def test_short_comment_is_returned_whole_and_unflagged():
    out = _condense_comments([_comment("<p>Short note.</p>")])[0]
    assert out["comment"] == "Short note."
    assert "truncated" not in out


def test_long_comment_is_cut_and_flagged_with_its_id():
    body = "<p>Security review (security-reviewer)</p>" + "<p>x</p>" * 4000
    out = _condense_comments([_comment(body)])[0]
    assert out["truncated"] is True
    assert out["full_length"] > len(out["comment"])
    assert out["id"] == "c-1"
    assert "retrieve_comment" in out["note"]
    # The head must still carry the line a pickup step selects on.
    assert out["comment"].startswith("Security review (security-reviewer)")


def test_plane_metadata_and_tiptap_json_are_dropped():
    out = _condense_comments([_comment("<p>Note.</p>")])[0]
    assert set(out) == {"id", "created_at", "comment"}


def test_empty_comment_stripped_does_not_win_over_html():
    """Self-hosted Plane leaves `comment_stripped` empty; the text is in
    the HTML. Preferring the empty field would silently blank the thread.
    """
    out = _condense_comments([_comment("<p>The actual text.</p>")])[0]
    assert out["comment"] == "The actual text."


def test_a_comment_with_no_body_at_all_survives():
    out = _condense_comments([_comment("", comment_html=None)])[0]
    assert out["comment"] == ""
