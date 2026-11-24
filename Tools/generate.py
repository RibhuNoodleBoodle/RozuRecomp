#!/usr/bin/env python3
"""Cross-platform Rule of Rose (SLUS-21448 v1.00) code generation orchestrator.

Pipeline:
  1. Verify ISO & prepare annotated ELF + CSV via Tools/ror_prepare.py
  2. Invoke ps2_recomp into build/generated_staging/
  3. Validate 0 decode failures, 0 unhandled instructions, 0 .vutext entries
  4. Content-preserving sync to Port/generated/
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from ror_prepare import ROOT, DEFAULT_PROFILE, load_profile, parse_hex  # noqa: E402

DEFAULT_TOML = os.path.join(ROOT, "Port", "recomp", "rozu.toml")
DEFAULT_PREPARE = os.path.join(ROOT, "build", "prepare")
DEFAULT_STAGING = os.path.join(ROOT, "build", "generated_staging")
DEFAULT_OUT = os.path.join(ROOT, "Port", "generated")
DEFAULT_ADDR_MAP = os.path.join(ROOT, "Analysis", "ADDRESS_MAP.generated.csv")


def find_iso(explicit_iso, profile):
    expected_size = int(profile["disc"]["size"])
    if explicit_iso:
        if not os.path.isfile(explicit_iso):
            raise RuntimeError(f"ISO not found: {explicit_iso}")
        return os.path.abspath(explicit_iso)
    env_iso = os.environ.get("ROZU_ISO", "").strip()
    if env_iso and os.path.isfile(env_iso):
        return os.path.abspath(env_iso)
    game_dir = os.path.join(ROOT, "Game")
    for pattern in ("*.iso", "*.ISO"):
        for cand in sorted(glob.glob(os.path.join(game_dir, pattern))):
            if os.path.getsize(cand) == expected_size:
                return os.path.abspath(cand)
    raise RuntimeError(
        f"No matching ISO found ({expected_size} bytes). Pass --iso <path> or set ROZU_ISO."
    )


def find_binary(explicit_path, name, extra_candidates):
    if explicit_path:
        if os.path.isfile(explicit_path):
            return os.path.abspath(explicit_path)
        raise RuntimeError(f"Explicit {name} binary not found: {explicit_path}")
    exe = f"{name}.exe" if os.name == "nt" else name
    candidates = [os.path.join(c, exe) if os.path.isdir(c) else c for c in extra_candidates]
    which = shutil.which(name)
    if which:
        candidates.append(which)
    for cand in candidates:
        if cand and os.path.isfile(cand):
            return os.path.abspath(cand)
    raise RuntimeError(f"Could not locate {name}; build it first or pass explicit flag")


def run_step(cmd, label):
    print(f"[generate] {label}: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {proc.returncode}")
    return (proc.stdout or "") + "\n" + (proc.stderr or "")


def write_staged_toml(base_toml_path, staged_toml_path, input_elf, csv_path, staged_out_dir):
    with open(base_toml_path, "r", encoding="utf-8") as f:
        text = f.read()

    def replace_key(src, key, new_val):
        escaped = new_val.replace("\\", "/")
        pat = re.compile(rf'^({re.escape(key)}\s*=\s*)"[^"]*"', re.MULTILINE)
        out, count = pat.subn(rf'\1"{escaped}"', src, count=1)
        if count != 1:
            raise RuntimeError(f"Expected key '{key}' once in {base_toml_path}, found {count}")
        return out

    text = replace_key(text, "input", input_elf)
    text = replace_key(text, "ghidra_output", csv_path)
    text = replace_key(text, "output", staged_out_dir)

    os.makedirs(os.path.dirname(staged_toml_path), exist_ok=True)
    with open(staged_toml_path, "w", encoding="utf-8") as f:
        f.write(text)


def verify_recomp_report(output_text, staged_dir, profile):
    decode_m = re.search(r"decode failures:\s*(\d+)", output_text)
    unhandled_m = re.search(r"Unhandled instructions:\s*(\d+)", output_text)
    errors_m = re.search(r"errors:\s*(\d+)", output_text)
    discovered_m = re.search(r"Functions discovered:\s*(\d+)", output_text)
    generated_m = re.search(r"Generated functions:\s*(\d+)", output_text)
    stubs_m = re.search(r"\bstubs:\s*(\d+)", output_text)

    if not decode_m or not unhandled_m or not errors_m:
        raise RuntimeError("Missing PS2Recomp summary report metrics in ps2_recomp output")

    decode_failures = int(decode_m.group(1))
    unhandled = int(unhandled_m.group(1))
    errors = int(errors_m.group(1))
    if decode_failures != 0 or unhandled != 0 or errors != 0:
        raise RuntimeError(
            f"ps2_recomp reported failures: decode_failures={decode_failures}, "
            f"unhandled={unhandled}, errors={errors}"
        )

    for req in (
        "register_functions.cpp",
        "ps2_recompiled_functions.h",
        "ps2_recompiled_stubs.h",
        "rozu_layout_generated.h",
    ):
        p = os.path.join(staged_dir, req)
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            raise RuntimeError(f"Missing or empty generated artifact: {p}")

    reg_path = os.path.join(staged_dir, "register_functions.cpp")
    with open(reg_path, "r", encoding="utf-8") as f:
        reg_text = f.read()

    entry_addr = parse_hex(profile["boot_elf"]["entry"])
    if not re.search(rf"0x0*{entry_addr:x}\b", reg_text, re.IGNORECASE):
        raise RuntimeError(f"Boot entry 0x{entry_addr:08X} not registered in register_functions.cpp")

    vutext_start = parse_hex(profile["vutext_exclude"]["start"])
    vutext_end = parse_hex(profile["vutext_exclude"]["end"])
    for m in re.finditer(r"0x([0-9a-fA-F]+)", reg_text):
        val = int(m.group(1), 16)
        if vutext_start <= val < vutext_end:
            raise RuntimeError(
                f"Forbidden .vutext address 0x{val:08X} found in register_functions.cpp!"
            )

    return {
        "discovered": int(discovered_m.group(1)) if discovered_m else -1,
        "generated": int(generated_m.group(1)) if generated_m else -1,
        "stubs": int(stubs_m.group(1)) if stubs_m else -1,
        "decode_failures": decode_failures,
        "unhandled": unhandled,
        "errors": errors,
    }


def sync_tree(src_dir, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    written = 0
    unchanged = 0
    removed = 0

    src_rel_files = set()
    for cur_root, _, files in os.walk(src_dir):
        rel_root = os.path.relpath(cur_root, src_dir)
        for fn in files:
            rel = fn if rel_root == "." else os.path.join(rel_root, fn)
            src_rel_files.add(rel)
            s_path = os.path.join(cur_root, fn)
            d_path = os.path.join(dst_dir, rel)
            os.makedirs(os.path.dirname(d_path), exist_ok=True)
            with open(s_path, "rb") as sf:
                data = sf.read()
            if os.path.isfile(d_path):
                with open(d_path, "rb") as df:
                    if df.read() == data:
                        unchanged += 1
                        continue
            tmp = d_path + ".tmp"
            with open(tmp, "wb") as tf:
                tf.write(data)
            os.replace(tmp, d_path)
            written += 1

    for cur_root, dirs, files in os.walk(dst_dir, topdown=False):
        rel_root = os.path.relpath(cur_root, dst_dir)
        for fn in files:
            rel = fn if rel_root == "." else os.path.join(rel_root, fn)
            if rel not in src_rel_files:
                os.remove(os.path.join(cur_root, fn))
                removed += 1
        if cur_root != dst_dir and not os.listdir(cur_root):
            os.rmdir(cur_root)

    return written, unchanged, removed


def main():
    ap = argparse.ArgumentParser(description="Generate statically recompiled Rule of Rose C++ sources")
    ap.add_argument("--iso", help="Path to Rule of Rose (USA) ISO image")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, help="Path to SLUS-21448_v1.00.json")
    ap.add_argument("--toml", default=DEFAULT_TOML, help="Path to Port/recomp/rozu.toml")
    ap.add_argument("--prepare-dir", default=DEFAULT_PREPARE, help="Preparation artifact directory")
    ap.add_argument("--staging-dir", default=DEFAULT_STAGING, help="Temporary staging output directory")
    ap.add_argument("--out-dir", default=DEFAULT_OUT, help="Final synced Port/generated directory")
    ap.add_argument("--address-map", default=DEFAULT_ADDR_MAP, help="Symbol map CSV path")
    ap.add_argument("--recomp", help="Path to ps2_recomp binary")
    ap.add_argument("--analyzer", help="Path to ps2_analyzer binary")
    ap.add_argument("--skip-prepare", action="store_true", help="Reuse existing verified --prepare-dir")
    ap.add_argument("--verify-full-disc-sha256", action="store_true", help="Verify full 3.2 GiB disc SHA-256")
    args = ap.parse_args()

    profile = load_profile(args.profile)
    prepare_dir = os.path.abspath(args.prepare_dir)
    staging_dir = os.path.abspath(args.staging_dir)
    out_dir = os.path.abspath(args.out_dir)

    recomp_bin = find_binary(
        args.recomp,
        "ps2_recomp",
        [
            os.path.join(ROOT, "build", "linux", "External", "PS2Recomp", "ps2xRecomp"),
            os.path.join(ROOT, "build", "port", "External", "PS2Recomp", "ps2xRecomp"),
            os.path.join(ROOT, "build", "Release", "External", "PS2Recomp", "ps2xRecomp"),
        ],
    )

    prepare_py = os.path.join(SCRIPT_DIR, "ror_prepare.py")
    if args.skip_prepare:
        run_step([sys.executable, prepare_py, "--profile", args.profile, "--verify-output", prepare_dir], "ror_prepare verify")
    else:
        iso_path = find_iso(args.iso, profile)
        prep_cmd = [
            sys.executable,
            prepare_py,
            "--profile",
            args.profile,
            "--iso",
            iso_path,
            "--out",
            prepare_dir,
            "--address-map",
            args.address_map,
        ]
        if args.analyzer:
            prep_cmd.extend(["--analyzer", os.path.abspath(args.analyzer)])
        if args.verify_full_disc_sha256:
            prep_cmd.append("--verify-full-disc-sha256")
        run_step(prep_cmd, "ror_prepare")
        run_step([sys.executable, prepare_py, "--profile", args.profile, "--verify-output", prepare_dir], "ror_prepare verify")

    if os.path.isdir(staging_dir):
        shutil.rmtree(staging_dir)
    os.makedirs(staging_dir, exist_ok=True)

    staged_toml = os.path.join(os.path.dirname(staging_dir), "rozu_recomp_staged.toml")
    ann_elf = os.path.join(prepare_dir, "slus_21448_annotated.elf")
    csv_path = os.path.join(prepare_dir, "rozu_functions.csv")
    write_staged_toml(args.toml, staged_toml, ann_elf, csv_path, staging_dir)

    recomp_out = run_step([recomp_bin, staged_toml], "ps2_recomp")

    layout_src = os.path.join(prepare_dir, "rozu_layout_generated.h")
    shutil.copyfile(layout_src, os.path.join(staging_dir, "rozu_layout_generated.h"))

    stats = verify_recomp_report(recomp_out, staging_dir, profile)
    written, unchanged, removed = sync_tree(staging_dir, out_dir)
    cpp_count = sum(1 for fn in os.listdir(out_dir) if fn.endswith(".cpp"))
    print(
        f"[generate] COMPLETE: {cpp_count} .cpp files in {out_dir} "
        f"(discovered={stats['discovered']}, generated={stats['generated']}, stubs={stats['stubs']}, "
        f"decode_failures={stats['decode_failures']}, unhandled={stats['unhandled']}; "
        f"sync written={written}, unchanged={unchanged}, removed={removed})"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
