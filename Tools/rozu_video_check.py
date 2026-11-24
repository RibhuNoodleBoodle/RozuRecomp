#!/usr/bin/env python3
"""M06 / Gate G4a automated verification for Rule of Rose (CP_LOGO.PSS + post-logo + title + audio + dual-run GSR determinism)."""

import argparse
import array
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import wave

from PIL import Image


WINDOWS = [
    ("warn", 800, 3),
    ("logo", 2000, 3),
    ("post", 2350, 3),
    ("title", 2800, 3),
]

EXPECTED_IOP_MODULES = (
    "MODULES/SIO2MAN.IRX",
    "MODULES/SIO2D.IRX",
    "MODULES/DBCMAN.IRX",
    "MODULES/PAD2/DS1O_D.IRX",
    "MODULES/MCMAN.IRX",
    "MODULES/MCSERV.IRX",
    "MODULES/LIBSD.IRX",
    "MODULES/RXSNDDRV.IRX",
)


def inspect_gsr_vram(gsr_path: Path) -> dict:
    data = gsr_path.read_bytes()
    if not data.startswith(b"PS2XGSR1"):
        raise ValueError(f"Invalid GSR header in {gsr_path}")
    pos = 8
    checkpoints = []
    while pos + 5 <= len(data):
        op = data[pos]
        size = struct.unpack_from("<I", data, pos + 1)[0]
        payload = data[pos + 5 : pos + 5 + size]
        pos += 5 + size
        if op in (1, 10, 13):
            tick = struct.unpack_from("<Q", payload, 0)[0]
            vsize = struct.unpack_from("<I", payload, 64)[0]
            vram = payload[-4194304:] if vsize == 4194304 and len(payload) >= 4194304 else b""
            nonzero = 0
            for i in range(0, len(vram), 4):
                if vram[i] or vram[i + 1] or vram[i + 2]:
                    nonzero += 1
            total = max(1, len(vram) // 4)
            checkpoints.append(
                {
                    "tick": tick,
                    "vsize": vsize,
                    "nonzero_words": nonzero,
                    "nonblack_pct": round(100.0 * nonzero / total, 2),
                }
            )
    max_pct = max((c["nonblack_pct"] for c in checkpoints), default=0.0)
    return {"checkpoints": checkpoints, "max_vram_nonblack_pct": max_pct}


def inspect_png(png_path: Path) -> dict:
    im = Image.open(png_path).convert("RGB")
    px = im.tobytes()
    nonzero = 0
    for i in range(0, len(px), 3):
        if px[i] or px[i + 1] or px[i + 2]:
            nonzero += 1
    total = max(1, len(px) // 3)
    return {
        "width": im.width,
        "height": im.height,
        "nonblack_pct": round(100.0 * nonzero / total, 2),
    }


def inspect_wav(wav_path: Path) -> dict:
    with wave.open(str(wav_path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        channels = wav.getnchannels()
        samples = array.array("h", wav.readframes(frames))
    peak = max((abs(v) for v in samples), default=0)
    nonzero = sum(1 for v in samples if v != 0)
    rms = round(math.sqrt(sum(v * v for v in samples) / len(samples)), 2) if samples else 0.0
    return {
        "rate": rate,
        "channels": channels,
        "frames": frames,
        "duration_sec": round(frames / max(1, rate), 2),
        "peak": peak,
        "rms": rms,
        "nonzero_samples": nonzero,
    }


def compare_gsr(repo: Path, a: Path, b: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(repo / "Tools/gsr_compare.py"), str(a), str(b)],
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "").strip()
    ok = proc.returncode == 0 and "checkpoints SAME" in out and "hashes SAME" in out and "ops SAME" in out
    return ok, out


def run_once(
    repo: Path,
    exe: Path,
    iso: Path,
    fields: int,
    timeout: float,
    out_dir: Path,
    run_idx: int,
    headless: bool,
    save_state: str | None,
) -> dict:
    run_dir = out_dir / f"run_{run_idx}"
    shots_dir = run_dir / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    gsr_specs = []
    gsr_files = {}
    for name, first, count in WINDOWS:
        if first + count <= fields:
            path = run_dir / f"{name}.gsr"
            gsr_files[name] = path
            gsr_specs.append(f"{first}:{count}:{path}")

    env = os.environ.copy()
    env["PS2X_GS_GPU"] = "0"
    env["PS2X_MTVU"] = "0"
    env["PS2X_VU1_RECOMP"] = "0"
    env["ROZU_VSYNC"] = "0"
    env["ROZU_FPS_LIMIT"] = "0"
    env["PS2X_MEMCARD"] = "1"
    env["ROZU_VIDEO_MODE"] = "NTSC"
    env["ROZU_TRACE"] = "BOOT,IOP,FILE,GAME"
    env["ROZU_STOP_AFTER_FIELDS"] = str(fields)
    env["ROZU_TIMELINE"] = str(run_dir / "timeline.txt")
    env["PS2X_AUDIO_DUMP"] = str(run_dir / "audio.wav")
    env["PS2X_GS_RECORD"] = ";".join(gsr_specs)
    env["PS2X_GS_RECORD_HASH"] = "1"
    if fields >= 2800:
        env["PS2X_PAD_SCRIPT"] = "2500v:start:10"
    else:
        env.pop("PS2X_PAD_SCRIPT", None)
    env.pop("ROZU_MISSING_FUNCTION", None)

    if headless:
        env["ROZU_HEADLESS"] = "1"
    else:
        env.pop("ROZU_HEADLESS", None)
        env["PS2X_SCREENSHOT_FIELDS"] = ",".join(str(f) for _, f, _ in WINDOWS if f <= fields)
        env["PS2X_SCREENSHOT_DIR"] = str(shots_dir)

    if save_state and run_idx == 1:
        env["PS2X_STATE_SAVE_AT"] = save_state
    else:
        env.pop("PS2X_STATE_SAVE_AT", None)

    cmd = [str(exe.resolve()), "--iso", str(iso.resolve())]
    t0 = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True, timeout=timeout)
        exit_code = proc.returncode
        log_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -1
        out_s = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err_s = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        log_text = out_s + "\n" + err_s + f"\n[video_check] TIMEOUT after {timeout}s\n"

    elapsed = round(time.monotonic() - t0, 2)
    (run_dir / "run.log").write_text(log_text, encoding="utf-8")

    missing_modules = [m for m in EXPECTED_IOP_MODULES if m not in log_text.replace("\\", "/")]
    failures = [
        line.strip()
        for line in log_text.splitlines()
        if any(tok in line for tok in ("No exact recompiled function", "Unhandled guest", "SIGSEGV", "FATAL", "[rozu] CRASH"))
    ]
    stopped = f"stopping cleanly after {fields} VSync fields" in log_text
    rxsnd_started = "Start RX - sound RPC server" in log_text

    gsr_stats = {}
    for name, path in gsr_files.items():
        if path.exists():
            gsr_stats[name] = inspect_gsr_vram(path)

    png_stats = {}
    for png in sorted(shots_dir.glob("field-*.png")):
        png_stats[png.name] = inspect_png(png)

    wav_stats = inspect_wav(run_dir / "audio.wav") if (run_dir / "audio.wav").exists() else {}

    vram_ok = all(
        name in gsr_stats and gsr_stats[name]["max_vram_nonblack_pct"] > 5.0
        for name in ("warn", "logo", "post", "title")
        if name in gsr_files
    )
    png_ok = True if headless else all(
        stat["nonblack_pct"] > 5.0 for stat in png_stats.values()
    ) and len(png_stats) == sum(1 for _, f, _ in WINDOWS if f <= fields)
    audio_ok = (
        wav_stats.get("rate") == 48000
        and wav_stats.get("channels") == 2
        and wav_stats.get("peak", 0) > 0
        and wav_stats.get("nonzero_samples", 0) > 0
    ) if fields >= 2800 else True

    run_pass = (
        not timed_out
        and exit_code == 0
        and stopped
        and rxsnd_started
        and not missing_modules
        and not failures
        and vram_ok
        and png_ok
        and audio_ok
    )
    return {
        "run": run_idx,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "elapsed_sec": elapsed,
        "stopped_cleanly": stopped,
        "rxsnd_started": rxsnd_started,
        "missing_modules": missing_modules,
        "failures": failures,
        "gsr": {k: str(v) for k, v in gsr_files.items()},
        "gsr_stats": gsr_stats,
        "png_stats": png_stats,
        "wav_stats": wav_stats,
        "pass": run_pass,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=Path("build/linux/bin/rozu"))
    parser.add_argument("--iso", type=Path, default=Path("Game/Rule of Rose (USA).iso"))
    parser.add_argument("--fields", type=int, default=2900)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--save-state", type=str, default="")
    parser.add_argument("--out", type=Path, default=Path("build/test_artifacts/G4a/video_check"))
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    out_dir = (repo / args.out).resolve() if not args.out.is_absolute() else args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    save_spec = args.save_state or None
    if save_spec and ":" in save_spec:
        tick_str, path_str = save_spec.split(":", 1)
        p = Path(path_str)
        if not p.is_absolute():
            p = (repo / p).resolve()
        save_spec = f"{tick_str}:{p}"

    runs = []
    overall = True
    for i in range(1, args.runs + 1):
        res = run_once(repo, args.exe, args.iso, args.fields, args.timeout, out_dir, i, args.headless, save_spec)
        runs.append(res)
        if not res["pass"]:
            overall = False
        vram_summary = [f"{k}:{v['max_vram_nonblack_pct']}%" for k, v in res["gsr_stats"].items()]
        print(
            f"[video_check] run {i}/{args.runs}: exit={res['exit_code']} elapsed={res['elapsed_sec']}s "
            f"stopped={res['stopped_cleanly']} wav_peak={res['wav_stats'].get('peak', 0)} "
            f"vram={vram_summary} "
            f"-> {'PASS' if res['pass'] else 'FAIL'}"
        )

    gsr_diffs = {}
    if len(runs) >= 2:
        for name in runs[0]["gsr"]:
            ok, msg = compare_gsr(repo, Path(runs[0]["gsr"][name]), Path(runs[1]["gsr"][name]))
            gsr_diffs[name] = {"same": ok, "detail": msg}
            print(f"[video_check] gsr_compare({name}): {msg} -> {'PASS' if ok else 'FAIL'}")
            if not ok:
                overall = False

    summary = {"gate": "G4a", "overall_pass": overall, "runs": runs, "gsr_compare": gsr_diffs}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[video_check] summary written: {out_dir / 'summary.json'} (overall_pass={overall})")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
