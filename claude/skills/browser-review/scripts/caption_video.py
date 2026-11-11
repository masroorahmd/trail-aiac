"""Caption a review-run video from its step log.

Reads `<dir>/steps.json` (written by `review_video.py`, or by any
harness that writes the same shape — see that file) and the video it
names, and writes next to them:

- `review.vtt`   WebVTT captions: which step, which requirements, then
                 the verdict once the step has run
- `review.mkv`   the video with those captions as a switchable track
                 (CC) and one chapter per step; plays in mpv / VLC
- `review.mp4`   with `--burn`: captions burned into the picture, for
                 players and browsers that show no subtitle track

    python3 .claude/skills/browser-review/scripts/caption_video.py \
        .claude/review-runs/<ID>/round-<N> --burn

Stdlib only. Needs ffmpeg on PATH; `--burn` needs one built with libass.
Exit 2 = nothing to caption (no ffmpeg, no steps.json, no clock, no video).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

MARK = {"PASS": "✓ PASS", "FAIL": "✗ FAIL", "XFAIL": "✗ expected failure", "SKIP": "– skipped"}


def _ts(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def _heading(step: dict) -> str:
    label = f"Step {step['step']}" if step.get("step") is not None else step["nodeid"].rsplit("::", 1)[-1]
    return f"{label} · {', '.join(step['req'])}" if step["req"] else label


def build_vtt(steps: list[dict]) -> str:
    cues = ["WEBVTT", ""]
    for i, step in enumerate(steps, 1):
        heading, title = _heading(step), step["title"]
        cues += [f"{i}a", f"{_ts(step['start'])} --> {_ts(step['end'])}", heading, title, ""]
        verdict = MARK.get(step["verdict"], step["verdict"])
        if step.get("message"):
            verdict = f"{verdict} — {step['message']}"
        cues += [f"{i}b", f"{_ts(step['end'])} --> {_ts(step['shown_until'])}", f"{heading} — {verdict}", title, ""]
    last = steps[-1]["shown_until"]
    tally: dict[str, int] = {}
    for step in steps:
        tally[step["verdict"]] = tally.get(step["verdict"], 0) + 1
    summary = ", ".join(f"{n} {v.lower()}" for v, n in tally.items())
    cues += ["end", f"{_ts(last)} --> {_ts(last + 4)}", "Review run finished", summary, ""]
    return "\n".join(cues)


def build_chapters(steps: list[dict]) -> str:
    lines = [";FFMETADATA1"]
    for step in steps:
        title = f"{_heading(step)} — {step['title']} [{step['verdict']}]"
        title = title.replace("\\", "\\\\").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#")
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={int(step['start'] * 1000)}",
            f"END={int(step['shown_until'] * 1000)}",
            f"title={title}",
        ]
    return "\n".join(lines) + "\n"


def _find_video(run_dir: Path, log: dict, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    if log.get("video") and Path(log["video"]).exists():
        return Path(log["video"])
    videos = sorted(run_dir.rglob("*.webm"), key=lambda p: p.stat().st_mtime)
    if not videos:
        _give_up(f"no .webm under {run_dir}; pass --video")
    return videos[-1]


def _give_up(reason: str) -> NoReturn:
    print(f"caption_video: {reason}", file=sys.stderr)
    sys.exit(2)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--video", help="video file (default: the one steps.json names, else the newest .webm)")
    ap.add_argument("--burn", action="store_true", help="also write review.mp4 with captions burned in")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        _give_up("ffmpeg not on PATH")
    log_path = args.run_dir / "steps.json"
    if not log_path.is_file():
        _give_up(f"no {log_path}")
    log = json.loads(log_path.read_text())
    steps = log["steps"]
    if any(s.get("start") is None for s in steps):
        _give_up("steps.json has no video clock — the spec never called review_video.video_started(page)")
    video = _find_video(args.run_dir, log, args.video)

    vtt = args.run_dir / "review.vtt"
    chapters = args.run_dir / "chapters.txt"
    vtt.write_text(build_vtt(steps))
    chapters.write_text(build_chapters(steps))

    mkv = args.run_dir / "review.mkv"
    _ffmpeg(
        "-i", str(video), "-i", str(vtt), "-i", str(chapters),
        "-map", "0:v", "-map", "1:s", "-map_metadata", "2", "-map_chapters", "2",
        "-c:v", "copy", "-c:s", "webvtt",
        "-metadata:s:s:0", "language=eng", "-metadata:s:s:0", "title=Review steps",
        "-disposition:s:0", "default",
        str(mkv),
    )  # fmt: skip
    print(mkv)

    if args.burn:
        mp4 = args.run_dir / "review.mp4"
        style = "FontName=DejaVu Sans,FontSize=13,Outline=1,Shadow=0,BorderStyle=3,BackColour=&H80000000,MarginV=12"
        escaped = str(vtt).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        _ffmpeg(
            "-i", str(video), "-i", str(chapters), "-map_metadata", "1", "-map_chapters", "1",
            "-vf", f"subtitles='{escaped}':force_style='{style}'",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-movflags", "+faststart",
            str(mp4),
        )  # fmt: skip
        print(mp4)


if __name__ == "__main__":
    main()
