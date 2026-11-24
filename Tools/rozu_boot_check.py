#!/usr/bin/env python3
"""Deterministic headless boot verification harness for RozuRecomp (Gate G3)."""

import argparse
import json
import os
import re
import subprocess
import sys
import time

EXPECTED_IOP_MODULES = [
    "IOPRP300.IMG",
    "SIO2MAN.IRX",
    "SIO2D.IRX",
    "DBCMAN.IRX",
    "DS1O_D.IRX",
    "MCMAN.IRX",
    "MCSERV.IRX",
    "LIBSD.IRX",
    "RXSNDDRV.IRX",
]

FAILURE_PATTERNS = [
    re.compile(r"\[crash\]", re.IGNORECASE),
    re.compile(r"missing.*function", re.IGNORECASE),
    re.compile(r"unhandled.*instruction", re.IGNORECASE),
    re.compile(r"unhandled.*exception", re.IGNORECASE),
    re.compile(r"unresolved\s+import", re.IGNORECASE),
    re.compile(r"segmentation fault", re.IGNORECASE),
    re.compile(r"failed to load module", re.IGNORECASE),
    re.compile(r"\[ps2xIOP:error\]", re.IGNORECASE),
]


def parse_run_log(log_text, exit_code):
    lines = log_text.splitlines()
    failures = []
    for ln in lines:
        for pat in FAILURE_PATTERNS:
            if pat.search(ln):
                failures.append(ln.strip())
                break

    verified_disc = bool(
        re.search(r"SLUS-21448", log_text)
        and re.search(r"(verified|SHA-256|disc image)", log_text, re.IGNORECASE)
    )
    entered_boot = bool(re.search(r"starting guest at 0x0*100008\b", log_text, re.IGNORECASE))

    loaded_modules = []
    seen_mods = set()
    for ln in lines:
        upper = ln.upper()
        for mod in EXPECTED_IOP_MODULES:
            if mod in upper and mod not in seen_mods:
                seen_mods.add(mod)
                loaded_modules.append(mod)

    missing_modules = [m for m in EXPECTED_IOP_MODULES if m not in seen_mods]
    rxsnd_started = bool(re.search(r"Start RX\s*-\s*sound RPC server", log_text, re.IGNORECASE))

    cdrom_files = []
    seen_files = set()
    for m in re.finditer(r"cdrom0?:[/\\]([A-Za-z0-9_./\\;-]+)", log_text, re.IGNORECASE):
        f = m.group(1).upper().replace("\\", "/")
        if f not in seen_files:
            seen_files.add(f)
            cdrom_files.append(f)

    stop_fields_m = re.search(r"stopping cleanly after (\d+) VSync fields", log_text)
    stopped_fields = int(stop_fields_m.group(1)) if stop_fields_m else 0

    return {
        "exit_code": exit_code,
        "verified_disc": verified_disc,
        "entered_boot_0x100008": entered_boot,
        "loaded_modules": loaded_modules,
        "missing_modules": missing_modules,
        "rxsnd_started": rxsnd_started,
        "cdrom_files": cdrom_files,
        "stopped_fields": stopped_fields,
        "failure_lines": failures,
    }


def main():
    ap = argparse.ArgumentParser(description="Run deterministic headless boot checks for rozu")
    ap.add_argument("--exe", default="build/linux/bin/rozu", help="Path to rozu binary")
    ap.add_argument("--iso", default="Game/Rule of Rose (USA).iso", help="Path to Rule of Rose ISO")
    ap.add_argument("--fields", type=int, default=300, help="ROZU_STOP_AFTER_FIELDS value")
    ap.add_argument("--timeout", type=int, default=120, help="Per-run timeout in seconds")
    ap.add_argument("--runs", type=int, default=2, help="Number of consecutive deterministic runs")
    ap.add_argument("--out", default="build/test_artifacts/G3", help="Output log/report directory")
    args = ap.parse_args()

    if not os.path.isfile(args.exe):
        print(f"ERROR: rozu executable not found: {args.exe}", file=sys.stderr)
        return 2
    if not os.path.isfile(args.iso):
        print(f"ERROR: ISO not found: {args.iso}", file=sys.stderr)
        return 2

    os.makedirs(args.out, exist_ok=True)
    run_results = []
    overall_ok = True

    for run_idx in range(1, args.runs + 1):
        env = os.environ.copy()
        env["ROZU_HEADLESS"] = "1"
        env["PS2X_GS_GPU"] = "0"
        env["PS2X_MTVU"] = "0"
        env["PS2X_VU1_RECOMP"] = "0"
        env["ROZU_TRACE"] = "BOOT,IOP,FILE,GAME"
        env["ROZU_STOP_AFTER_FIELDS"] = str(args.fields)
        env.pop("ROZU_MISSING_FUNCTION", None)

        cmd = [os.path.abspath(args.exe), "--iso", os.path.abspath(args.iso)]
        t0 = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=args.timeout,
            )
            exit_code = proc.returncode
            combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = -1
            out_s = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            err_s = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            combined = out_s + "\n" + err_s + f"\n[boot_check] TIMEOUT after {args.timeout}s\n"

        elapsed = round(time.monotonic() - t0, 3)
        log_path = os.path.join(args.out, f"run_{run_idx}.log")
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(combined)

        parsed = parse_run_log(combined, exit_code)
        parsed["run"] = run_idx
        parsed["elapsed_sec"] = elapsed
        parsed["timed_out"] = timed_out
        parsed["log_path"] = log_path
        run_results.append(parsed)

        run_pass = (
            not timed_out
            and exit_code == 0
            and parsed["verified_disc"]
            and parsed["entered_boot_0x100008"]
            and not parsed["missing_modules"]
            and parsed["rxsnd_started"]
            and len(parsed["cdrom_files"]) >= 1
            and not parsed["failure_lines"]
        )
        if not run_pass:
            overall_ok = False
        print(
            f"[boot_check] run {run_idx}/{args.runs}: exit={exit_code} timed_out={timed_out} "
            f"elapsed={elapsed}s fields={parsed['stopped_fields']} "
            f"mods={len(parsed['loaded_modules'])}/{len(EXPECTED_IOP_MODULES)} "
            f"rxsnd={parsed['rxsnd_started']} files={len(parsed['cdrom_files'])} "
            f"failures={len(parsed['failure_lines'])} -> {'PASS' if run_pass else 'FAIL'}"
        )

    reproducible = True
    if len(run_results) >= 2:
        ref = (run_results[0]["loaded_modules"], run_results[0]["cdrom_files"])
        for rr in run_results[1:]:
            if (rr["loaded_modules"], rr["cdrom_files"]) != ref:
                reproducible = False
                overall_ok = False
                print("[boot_check] FAIL: boot milestones differed across runs!", file=sys.stderr)

    summary = {
        "gate": "G3",
        "overall_pass": overall_ok,
        "reproducible": reproducible,
        "runs": run_results,
    }
    summary_path = os.path.join(args.out, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as sf:
        json.dump(summary, sf, indent=2)
    print(f"[boot_check] summary written: {summary_path} (overall_pass={overall_ok})")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
