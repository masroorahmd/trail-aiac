"""pytest plugin: log each review step on the video's clock, for captions.

A review-run spec encodes one test per numbered review step. This plugin
writes down, per step, when it ran on the video's clock, which
requirements it checks and how it ended — `steps.json` in the run's
evidence directory. `caption_video.py` (next to this file) turns that
log plus the Playwright video into captions and chapters. The captions
are built from what the test did, never from a model's account of it.

Load it, point it at the evidence directory:

    PYTHONPATH=.claude/skills/browser-review/scripts \
        python -m pytest <spec> -p review_video \
        --review-video=.claude/review-runs/<ID>/round-<N> \
        [--review-video-dwell=1.0,1.5]

In the spec's conftest, mark t=0 right after the page is created
(Playwright starts a page's video then) — guarded, so the spec still
runs where the plugin is not on the path:

    try:
        import review_video
    except ImportError:
        review_video = None
    ...
    page = context.new_page()
    if review_video:
        review_video.video_started(page)

Tag each step with the requirement IDs its review step names:

    @pytest.mark.req("AC-11", "AC-13")
    def test_step_07_filtered_empty_swaps_the_affordances(page): ...

Without `--review-video` the plugin records nothing and holds no dwell.

`steps.json` — the contract `caption_video.py` reads, so a non-pytest
harness can write it too:

    {"video": "<path to .webm, or null>",
     "steps": [{"step": 7, "title": "Filtered empty swaps the affordances",
                "req": ["AC-11", "AC-13"],
                "start": 20.29,         # caption appears (seconds on the video's clock)
                "end": 21.76,           # step finished; verdict caption from here
                "shown_until": 23.26,   # verdict caption ends
                "verdict": "PASS",      # PASS | FAIL | XFAIL | SKIP
                "message": "..."}]}     # optional, FAIL only
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import pytest

_STATE: dict[str, Any] = {"dir": None, "lead": 0.0, "tail": 0.0, "t0": None, "video": None, "steps": []}
_STEP_NAME = re.compile(r"^test_step_(\d+)_(.+)$")


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("review-video")
    group.addoption("--review-video", metavar="DIR", help="write steps.json for captioning into DIR")
    group.addoption(
        "--review-video-dwell",
        metavar="LEAD,TAIL",
        default="1.0,1.5",
        help="seconds to hold before / after each step so captions stay readable (default 1.0,1.5; 0,0 = off)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "req(*ids): requirement IDs a review step checks (AC-N, NFR-N, EC-N, ...)")
    target = config.getoption("--review-video")
    if not target:
        return
    lead, tail = (float(x) for x in str(config.getoption("--review-video-dwell")).split(","))
    _STATE.update(dir=Path(target), lead=lead, tail=tail)


def video_started(page: Any) -> None:
    """Mark t=0 of the video. Call right after `context.new_page()`."""
    if _STATE["dir"] is None:
        return
    _STATE["t0"] = time.monotonic()
    try:
        _STATE["video"] = str(page.video.path()) if page.video else None
    except Exception:  # noqa: BLE001 - a missing path only costs the auto-lookup
        _STATE["video"] = None


def _now() -> float | None:
    t0 = _STATE["t0"]
    return None if t0 is None else round(time.monotonic() - t0, 3)


def _describe(item: pytest.Item) -> tuple[int | None, str]:
    name = item.name.split("[", 1)[0]
    match = _STEP_NAME.match(name)
    number = int(match.group(1)) if match else None
    obj = getattr(item, "obj", None)
    doc = (obj.__doc__ or "").strip() if obj is not None else ""
    if doc:
        return number, doc.splitlines()[0].rstrip(".")
    words = match.group(2) if match else name.removeprefix("test_")
    return number, words.replace("_", " ").capitalize()


def _short(exc: BaseException) -> str:
    """One line a viewer can read. Playwright's first line is usually just
    'Timeout 30000ms exceeded'; the reason sits in the call log below it."""
    lines = [ln.strip() for ln in str(exc).strip().splitlines() if ln.strip()]
    if not lines:
        return type(exc).__name__
    head = lines[0]
    if "Timeout" in head:
        reasons = [ln.lstrip("- ") for ln in lines if ln.lstrip("- ").startswith(("element is", "element was"))]
        if reasons:
            head = f"{head} ({reasons[-1]})"
    return head[:160]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item):
    if _STATE["dir"] is None:
        yield
        return
    number, title = _describe(item)
    marker = item.get_closest_marker("req")
    step: dict[str, Any] = {
        "nodeid": item.nodeid,
        "step": number,
        "title": title,
        "req": list(marker.args) if marker else [],
        "start": _now(),
    }
    time.sleep(_STATE["lead"])  # caption on screen before the step acts
    outcome = yield
    step["end"] = _now()
    excinfo = outcome.excinfo
    if excinfo is None:
        step["verdict"] = "PASS"
    elif isinstance(excinfo[1], pytest.skip.Exception):
        step["verdict"] = "SKIP"
    elif isinstance(excinfo[1], pytest.xfail.Exception) or item.get_closest_marker("xfail"):
        step["verdict"] = "XFAIL"
    else:
        step["verdict"] = "FAIL"
        step["message"] = _short(excinfo[1])
    time.sleep(_STATE["tail"])  # verdict on screen after the step
    step["shown_until"] = _now()
    _STATE["steps"].append(step)


def pytest_sessionfinish(session: pytest.Session) -> None:  # noqa: ARG001 - pytest hook signature
    target = _STATE["dir"]
    if target is None or not _STATE["steps"]:
        return
    target.mkdir(parents=True, exist_ok=True)
    payload = {"video": _STATE["video"], "steps": _STATE["steps"]}
    (target / "steps.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
