#!/usr/bin/env python3
"""Deterministic SLUS_214.48 (Rule of Rose NTSC-U) function map & TOML generator.

Combines clean-room R5900 ELF binary analysis with ps2_analyzer's SceSymbolScanner,
MMIO detector, and jump-table recovery:
  1. All .gnu.linkonce.t.* ELF section headers (1,449 methods, exact addresses/sizes).
  2. .ctors, .dtors, and all 284 .gnu.linkonce.d._vt$* GCC2 virtual tables.
  3. Verified Sony SDK / Newlib / libgcc2 matches from ps2_analyzer (>= 0x0024B490
     plus verified libvu0 helpers).
  4. CFG-aware .text function discovery (e_entry, JAL targets, aligned .data/.rodata
     function pointers, non-bypassed post-epilogue jr $ra boundaries, and stack-frame
     prologues outside delayed-prologue windows and local branch/jump-table targets).
  5. Strict exclusion of .vutext, .vudata, and .DVP.* sections.
"""

from __future__ import annotations

import argparse
import bisect
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Set, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ELF = REPO_ROOT / "out" / "disc" / "SLUS_214.48"
DEFAULT_ANALYZER = REPO_ROOT / "out" / "build" / "baseline" / "ps2xAnalyzer" / "ps2_analyzer"
DEFAULT_TOML = REPO_ROOT / "config" / "slus_21448.toml"
DEFAULT_CSV = REPO_ROOT / "config" / "slus_21448.csv"
DEFAULT_RECOMP_OUT = REPO_ROOT / "out" / "recomp"

VUTEXT_START = 0x00291230
VUTEXT_END = 0x002953B0

KNOWN_ENGINE_NAMES: Dict[int, str] = {
    0x00100008: "_start",
    0x001005AC: "bedInitSystem",
    0x00101BCC: "BedPad_initialize",
    0x00101CCC: "BedPad_update",
    0x00117654: "vsyncHandler",
    0x00117990: "MagSystem_initialize",
    0x00117FC4: "MagSystem_run",
    0x001182DC: "MagSystem_update",
    0x00118754: "MagSystem_waitVSync",
    0x001AE6A0: "CSequenceCode_update",
    0x002045A8: "main",
    0x00280E08: "__do_global_ctors",
}

VERIFIED_EARLY_SDK_ADDRS: Set[int] = {
    0x00236AC8,  # sceVu0ClampVector
    0x00236CE8,  # sceVu0TransposeMatrix
    0x002374E0,  # sceVu0ClampVector
    0x00237508,  # sceVu0ClampVector
    0x00237788,  # sceVu0TransposeMatrix
}


def parse_elf_sections(elf_bytes: bytes) -> Tuple[int, List[Tuple[str, int, int, int, int, int]]]:
    """Return (e_entry, list of (name, sh_type, sh_flags, sh_addr, sh_offset, sh_size))."""
    if elf_bytes[:4] != b"\x7fELF":
        raise ValueError("Input file is not a valid ELF binary")
    e_entry, _e_phoff, e_shoff = struct.unpack_from("<III", elf_bytes, 0x18)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", elf_bytes, 0x2E)
    shstr_off, shstr_size = struct.unpack_from(
        "<II", elf_bytes, e_shoff + e_shstrndx * e_shentsize + 0x10
    )
    shstr = elf_bytes[shstr_off : shstr_off + shstr_size]

    def read_str(off: int) -> str:
        end = shstr.find(b"\x00", off)
        return shstr[off:end].decode("ascii", "replace")

    sections: List[Tuple[str, int, int, int, int, int]] = []
    for i in range(e_shnum):
        sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, *_ = struct.unpack_from(
            "<10I", elf_bytes, e_shoff + i * e_shentsize
        )
        sections.append((read_str(sh_name), sh_type, sh_flags, sh_addr, sh_offset, sh_size))
    return e_entry, sections


def is_excluded_vu_or_dvp(name: str) -> bool:
    return (
        name == ".vutext"
        or name.startswith(".vutext.")
        or name == ".vudata"
        or name.startswith(".vudata.")
        or name == ".DVP"
        or name.startswith(".DVP.")
    )


def run_ps2_analyzer(analyzer_bin: Path, elf_path: Path, out_toml: Path) -> str:
    env = os.environ.copy()
    tmp_dir = REPO_ROOT / "out" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    env.setdefault("TMPDIR", str(tmp_dir))
    proc = subprocess.run(
        [str(analyzer_bin), str(elf_path), str(out_toml)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.stdout + "\n" + proc.stderr


def parse_analyzer_toml(toml_text: str) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]], str, str]:
    """Extract trusted stubs, entry_points, [mmio] block, and [jump_tables] block."""
    def extract_selector_list(key: str) -> List[Tuple[str, int]]:
        m = re.search(rf"^{key}\s*=\s*\[(.*?)\]", toml_text, re.M | re.S)
        if not m:
            return []
        items: List[Tuple[str, int]] = []
        for full, hex_addr in re.findall(r'"([^"]+)@0x([0-9A-Fa-f]+)"', m.group(1)):
            items.append((full, int(hex_addr, 16)))
        return items

    stubs_raw = extract_selector_list("stubs")
    entries_raw = extract_selector_list("entry_points")

    # Keep only verified SDK range (>= 0x0024B490) or verified early libvu0 routines in stubs
    # so false-positive short-sequence matches inside game code are never stubbed.
    stubs = [
        (name, addr)
        for name, addr in stubs_raw
        if addr >= 0x0024B490 or addr in VERIFIED_EARLY_SDK_ADDRS
    ]
    entries = [
        (KNOWN_ENGINE_NAMES.get(addr, name), addr)
        for name, addr in entries_raw
        if addr >= 0x0024B490 or addr in VERIFIED_EARLY_SDK_ADDRS
    ]

    mmio_match = re.search(r"(\[mmio\].*?)(?=\n\[(?:jump_tables|patches|performance)\])", toml_text, re.S)
    mmio_block = mmio_match.group(1).strip() if mmio_match else ""

    jt_match = re.search(r"(\[jump_tables\].*?)(?=\n\[(?:patches|performance)\])", toml_text, re.S)
    jt_block = jt_match.group(1).strip() if jt_match else ""

    return stubs, entries, mmio_block, jt_block


def is_stack_prologue(ins: int) -> bool:
    op = ins >> 26
    rs = (ins >> 21) & 0x1F
    rt = (ins >> 16) & 0x1F
    imm = ins & 0xFFFF
    return op in (9, 0x19) and rs == 29 and rt == 29 and (imm & 0x8000) != 0


def is_save_ra_or_prologue(ins: int) -> bool:
    if is_stack_prologue(ins):
        return True
    op = ins >> 26
    rs = (ins >> 21) & 0x1F
    rt = (ins >> 16) & 0x1F
    return op in (0x2B, 0x3F, 0x1E) and rs == 29 and rt == 31


def discover_text_functions(
    e_entry: int,
    elf_bytes: bytes,
    sections: List[Tuple[str, int, int, int, int, int]],
    sdk_names: Dict[int, str],
    jt_block: str,
) -> List[Tuple[str, int, int]]:
    text_sec = next((s for s in sections if s[0] == ".text"), None)
    if text_sec is None:
        raise RuntimeError(".text section missing from ELF")
    _, _, _, text_va, text_off, text_sz = text_sec
    text_end = text_va + text_sz
    text_words = struct.unpack_from(f"<{text_sz // 4}I", elf_bytes, text_off)
    nwords = len(text_words)

    def in_text(va: int) -> bool:
        return text_va <= va < text_end and (va & 3) == 0

    def rword(va: int) -> int:
        return text_words[(va - text_va) >> 2]

    # Scan JAL targets across ALL executable non-VU/non-DVP sections
    jals: Set[int] = set()
    fwd_branch_map: Dict[int, int] = {}
    local_targets: Set[int] = set()

    for name, _stype, sh_flags, sh_addr, sh_off, sh_size in sections:
        if (sh_flags & 4) == 0 or sh_size == 0 or is_excluded_vu_or_dvp(name):
            continue
        sec_words = struct.unpack_from(f"<{sh_size // 4}I", elf_bytes, sh_off)
        for idx, ins in enumerate(sec_words):
            va = sh_addr + idx * 4
            op = ins >> 26
            if op == 3:  # JAL
                target = ((va + 4) & 0xF0000000) | ((ins & 0x03FFFFFF) << 2)
                if in_text(target):
                    jals.add(target)

    for idx, ins in enumerate(text_words):
        va = text_va + idx * 4
        op = ins >> 26
        is_branch = (
            op in (1, 4, 5, 6, 7, 0x14, 0x15, 0x16, 0x17)
            or (op == 0x11 and ((ins >> 21) & 0x1F) == 8)
            or (op == 0x12 and ((ins >> 21) & 0x1F) == 8)
        )
        if is_branch:
            off16 = ins & 0xFFFF
            if off16 & 0x8000:
                off16 -= 0x10000
            target = va + 4 + (off16 << 2)
            if in_text(target):
                local_targets.add(target)
                if target > va:
                    fwd_branch_map[va] = target

    for hex_addr in re.findall(r'target\s*=\s*"0x([0-9A-Fa-f]+)"', jt_block):
        target = int(hex_addr, 16)
        if in_text(target):
            local_targets.add(target)

    # Tier 1 trusted entry points: e_entry, JALs, .ctors/.dtors, vtables, SDK matches
    trusted: Set[int] = {e_entry} | jals | {addr for addr in sdk_names if in_text(addr)}
    for addr in KNOWN_ENGINE_NAMES:
        if in_text(addr):
            trusted.add(addr)

    for name, _stype, _sh_flags, _sh_addr, sh_off, sh_size in sections:
        if name in (".ctors", ".dtors") or name.startswith(".gnu.linkonce.d._vt$"):
            raw = elf_bytes[sh_off : sh_off + sh_size]
            for (word,) in struct.iter_unpack("<I", raw):
                if in_text(word):
                    trusted.add(word)

    # Valid function pointers in .data and .rodata (guarded against non-code integers)
    data_ptrs: Set[int] = set()
    for name, _stype, _sh_flags, _sh_addr, sh_off, sh_size in sections:
        if name in (".data", ".rodata"):
            raw = elf_bytes[sh_off : sh_off + sh_size]
            for (word,) in struct.iter_unpack("<I", raw):
                if in_text(word) and word not in local_targets:
                    first_ins = rword(word)
                    if is_save_ra_or_prologue(first_ins) or first_ins == 0x03E00008:
                        data_ptrs.add(word)

    seeds: Set[int] = trusted | data_ptrs

    # Post-epilogue (jr $ra; delay; nops) scan guarded by active forward branches
    after_jr: Set[int] = set()
    max_fwd = text_va
    i = (e_entry - text_va) // 4
    while i < nwords - 2:
        va = text_va + i * 4
        if va in seeds:
            max_fwd = va
        if va in fwd_branch_map and fwd_branch_map[va] > max_fwd:
            max_fwd = fwd_branch_map[va]
        if text_words[i] == 0x03E00008:  # jr $ra
            k = i + 2
            while k < nwords and text_words[k] == 0:
                k += 1
            if k < nwords:
                next_va = text_va + k * 4
                if next_va > max_fwd and next_va not in local_targets:
                    if not (
                        text_words[k] == 0x03E00008
                        and k + 1 < nwords
                        and is_stack_prologue(text_words[k + 1])
                    ):
                        after_jr.add(next_va)
                        max_fwd = next_va
        i += 1

    combined = sorted(seeds | after_jr)

    # Prologue sweep outside delayed-prologue windows and local branch targets
    prologues: Set[int] = set()
    for idx, ins in enumerate(text_words):
        va = text_va + idx * 4
        if va < e_entry or va in local_targets or not is_stack_prologue(ins):
            continue
        pos = bisect.bisect_right(combined, va) - 1
        prev_seed = combined[pos] if pos >= 0 else 0
        if va - prev_seed <= 24:
            continue
        prologues.add(va)

    starts = sorted(set(combined) | prologues)

    result: List[Tuple[str, int, int]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else text_end
        if end <= start:
            continue
        if start in KNOWN_ENGINE_NAMES:
            fname = KNOWN_ENGINE_NAMES[start]
        elif start in sdk_names:
            fname = sdk_names[start]
        else:
            # Non-sub_ prefix ensures ElfParser::extractFunctions treats CSV bounds authoritatively.
            fname = f"rozu_{start:08x}"
        result.append((fname, start, end))
    return result


def collect_linkonce_functions(
    sections: List[Tuple[str, int, int, int, int, int]],
) -> List[Tuple[str, int, int]]:
    funcs: List[Tuple[str, int, int]] = []
    seen: Set[int] = set()
    for name, _stype, sh_flags, sh_addr, _sh_off, sh_size in sections:
        if (sh_flags & 4) == 0 or sh_size == 0 or is_excluded_vu_or_dvp(name):
            continue
        if not name.startswith(".gnu.linkonce.t."):
            continue
        if sh_addr in seen:
            continue
        seen.add(sh_addr)
        suffix = name[len(".gnu.linkonce.t.") :] or name
        if "," in suffix or any(ch.isspace() for ch in suffix):
            raise ValueError(f"Unsupported CSV characters in section name: {name}")
        funcs.append((suffix, sh_addr, sh_addr + sh_size))
    funcs.sort(key=lambda item: item[1])
    return funcs


def validate_functions(functions: List[Tuple[str, int, int]]) -> None:
    if len(functions) < 8900:
        raise AssertionError(f"Expected >= 8900 functions, found {len(functions)}")
    prev_end = 0
    for name, start, end in functions:
        if (start & 3) != 0 or (end & 3) != 0:
            raise AssertionError(f"Unaligned function {name}: [0x{start:08x}, 0x{end:08x})")
        if end <= start:
            raise AssertionError(f"Invalid size for {name}: [0x{start:08x}, 0x{end:08x})")
        if not (end <= VUTEXT_START or start >= VUTEXT_END):
            raise AssertionError(f"Function {name} overlaps .vutext: [0x{start:08x}, 0x{end:08x})")
        if start < prev_end:
            raise AssertionError(
                f"Overlapping function {name} at 0x{start:08x} (prev end 0x{prev_end:08x})"
            )
        prev_end = end


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate config/slus_21448.toml and CSV function map.")
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--analyzer", type=Path, default=DEFAULT_ANALYZER)
    parser.add_argument("--toml", type=Path, default=DEFAULT_TOML)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RECOMP_OUT)
    parser.add_argument("--analyzer-toml", type=Path, default=None, help="Optional cached analyzer TOML.")
    args = parser.parse_args()

    elf_bytes = args.elf.read_bytes()
    e_entry, sections = parse_elf_sections(elf_bytes)

    tmp_dir_obj = None
    if args.analyzer_toml is not None and args.analyzer_toml.exists():
        analyzer_toml_text = args.analyzer_toml.read_text(encoding="utf-8")
    else:
        if not args.analyzer.exists():
            raise FileNotFoundError(f"ps2_analyzer binary not found: {args.analyzer}")
        tmp_dir_obj = tempfile.TemporaryDirectory(dir=str(REPO_ROOT / "out" / "tmp"))
        tmp_toml = Path(tmp_dir_obj.name) / "analyzer.toml"
        run_ps2_analyzer(args.analyzer, args.elf, tmp_toml)
        analyzer_toml_text = tmp_toml.read_text(encoding="utf-8")
    if tmp_dir_obj is not None:
        tmp_dir_obj.cleanup()

    stubs, entry_points, mmio_block, jt_block = parse_analyzer_toml(analyzer_toml_text)
    sdk_names: Dict[int, str] = {}
    for name, addr in entry_points + stubs:
        sdk_names[addr] = name

    text_funcs = discover_text_functions(e_entry, elf_bytes, sections, sdk_names, jt_block)
    linkonce_funcs = collect_linkonce_functions(sections)
    all_funcs = sorted(text_funcs + linkonce_funcs, key=lambda item: item[1])
    validate_functions(all_funcs)

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", encoding="utf-8", newline="\n") as f:
        f.write("Name,Start,End,Size\n")
        for name, start, end in all_funcs:
            size = end - start
            f.write(f"{name},0x{start:08x},0x{end:08x},0x{size:x}\n")

    output_dir_str = str(args.output_dir).rstrip("/") + "/"
    args.toml.parent.mkdir(parents=True, exist_ok=True)
    with args.toml.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# PS2Recomp configuration for Rule of Rose (SLUS-21448 NTSC-U v1.00)\n")
        f.write("# Generated deterministically by tools/generate_slus21448_toml.py\n\n")
        f.write("[general]\n")
        f.write(f'input = "{args.elf}"\n')
        f.write(f'ghidra_output = "{args.csv}"\n')
        f.write(f'output = "{output_dir_str}"\n\n')
        f.write("single_file_output = false\n\n")
        f.write("patch_syscalls = false\n")
        f.write("patch_cop0 = true\n")
        f.write("patch_cache = true\n\n")

        f.write("stubs = [\n")
        for name, addr in stubs:
            f.write(f'  "{name}@0x{addr:08X}",\n')
        f.write("]\n\n")

        f.write("entry_points = [\n")
        for name, addr in entry_points:
            f.write(f'  "{name}@0x{addr:08X}",\n')
        f.write("]\n\n")

        f.write("skip = []\n\n")
        if mmio_block:
            f.write(mmio_block + "\n\n")
        if jt_block:
            f.write(jt_block + "\n\n")

        f.write("[performance]\n")
        f.write("critical = []\n")

    print(
        f"Generated {args.csv} and {args.toml}: "
        f"total={len(all_funcs)} (.text={len(text_funcs)}, .gnu.linkonce.t.*={len(linkonce_funcs)}, "
        f"stubs={len(stubs)}, entry_points={len(entry_points)}, .vutext=0)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
