#!/usr/bin/env python3
"""Rule of Rose (SLUS-21448 v1.00) ISO9660 validator, ELF checker, and layout header emitter."""

import argparse
import hashlib
import json
import os
import struct
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from iso9660 import Iso9660

ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_PROFILE = os.path.join(ROOT, "Port", "profile", "SLUS-21448_v1.00.json")

ELFCLASS32 = 1
ELFDATA2LSB = 1
ET_EXEC = 2
EM_MIPS = 8
SHT_RELA = 4
SHT_STRTAB = 3
SHT_REL = 9


def parse_hex(value):
    return int(value, 16) if isinstance(value, str) else int(value)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 22)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_profile(profile_path):
    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)


def emit_layout_header(profile, header_path):
    os.makedirs(os.path.dirname(os.path.abspath(header_path)), exist_ok=True)
    disc = profile["disc"]
    elf = profile["boot_elf"]
    vutext = profile["vutext_exclude"]
    lines = [
        "#pragma once",
        "",
        "#include <cstddef>",
        "#include <cstdint>",
        "",
        "namespace rozu::generated",
        "{",
        f'    inline constexpr const char *kSerial = "{profile["serial"]}";',
        f'    inline constexpr const char *kTitle = "{profile["title"]}";',
        f'    inline constexpr const char *kRegion = "{profile["region"]}";',
        f'    inline constexpr const char *kVersion = "{profile["version"]}";',
        f'    inline constexpr const char *kVmode = "{profile["vmode"]}";',
        f'    inline constexpr uint64_t kDiscSize = {int(disc["size"])}ULL;',
        f'    inline constexpr const char *kDiscSha256 = "{disc["sha256"]}";',
        f'    inline constexpr const char *kBootElfDiscPath = "{elf["disc_path"]}";',
        f'    inline constexpr uint64_t kBootElfSize = {int(elf["size"])}ULL;',
        f'    inline constexpr const char *kBootElfSha256 = "{elf["sha256"]}";',
        f'    inline constexpr uint32_t kBootEntry = 0x{parse_hex(elf["entry"]):08X}u;',
        f'    inline constexpr uint32_t kGpValue = 0x{parse_hex(elf["gp"]):08X}u;',
        f'    inline constexpr uint32_t kTextStart = 0x{parse_hex(elf["text_start"]):08X}u;',
        f'    inline constexpr uint32_t kTextEnd = 0x{parse_hex(elf["text_end"]):08X}u;',
        f'    inline constexpr uint32_t kBssEnd = 0x{parse_hex(elf["bss_end"]):08X}u;',
        f'    inline constexpr uint32_t kVutextStart = 0x{parse_hex(vutext["start"]):08X}u;',
        f'    inline constexpr uint32_t kVutextEnd = 0x{parse_hex(vutext["end"]):08X}u;',
        "",
        "    struct RequiredFile",
        "    {",
        "        const char *discPath;",
        "        uint64_t size;",
        "        const char *sha256;",
        "    };",
        "",
        "    inline constexpr RequiredFile kRequiredFiles[] = {",
    ]
    for item in profile["required_files"]:
        lines.append(
            f'        {{"{item["path"]}", {int(item["size"])}ULL, "{item["sha256"]}"}},'
        )
    lines.extend([
        "    };",
        "}",
        "",
    ])
    content = "\n".join(lines)
    if os.path.exists(header_path):
        with open(header_path, "r", encoding="utf-8") as existing:
            if existing.read() == content:
                return False
    with open(header_path, "w", encoding="utf-8", newline="\n") as out:
        out.write(content)
    return True


def validate_elf_structure(elf_bytes, profile):
    if len(elf_bytes) < 52 or elf_bytes[:4] != b"\x7fELF":
        raise RuntimeError("SLUS_214.48 is not a valid ELF binary")
    ei_class, ei_data = elf_bytes[4], elf_bytes[5]
    if ei_class != ELFCLASS32 or ei_data != ELFDATA2LSB:
        raise RuntimeError(f"Expected ELF32 LSB, got class={ei_class} data={ei_data}")
    e_type, e_machine, _e_version, e_entry, _e_phoff, e_shoff, _e_flags, _e_ehsize, _e_phentsize, _e_phnum, e_shentsize, e_shnum, e_shstrndx = struct.unpack_from(
        "<HHIIIIIHHHHHH", elf_bytes, 16
    )
    if e_type != ET_EXEC or e_machine != EM_MIPS:
        raise RuntimeError(f"Expected ET_EXEC/EM_MIPS, got type={e_type} machine={e_machine}")

    expected_entry = parse_hex(profile["boot_elf"]["entry"])
    if e_entry != expected_entry:
        raise RuntimeError(f"Unexpected entry point 0x{e_entry:08X} (expected 0x{expected_entry:08X})")

    if e_shoff == 0 or e_shnum == 0 or e_shentsize < 40:
        raise RuntimeError("SLUS_214.48 is missing section headers")

    sections = [
        struct.unpack_from("<10I", elf_bytes, e_shoff + i * e_shentsize)
        for i in range(e_shnum)
    ]
    shstr_sec = sections[e_shstrndx]
    if shstr_sec[1] != SHT_STRTAB:
        raise RuntimeError("Invalid .shstrtab section type")
    shstr = elf_bytes[shstr_sec[4]:shstr_sec[4] + shstr_sec[5]]

    def sec_name(name_off):
        end = shstr.find(b"\x00", name_off)
        return shstr[name_off:end if end != -1 else len(shstr)].decode("ascii", "replace")

    reloc_sections = []
    vutext_sec = None
    for sec in sections:
        name = sec_name(sec[0])
        sh_type, _sh_flags, sh_addr, _sh_off, sh_size = sec[1], sec[2], sec[3], sec[4], sec[5]
        if sh_type in (SHT_REL, SHT_RELA):
            reloc_sections.append(name)
        if name == profile["vutext_exclude"]["name"]:
            vutext_sec = (sh_addr, sh_size)

    if reloc_sections:
        raise RuntimeError(f"ADR-002 violation: unexpected relocation sections {reloc_sections}")

    expected_vutext_start = parse_hex(profile["vutext_exclude"]["start"])
    expected_vutext_size = parse_hex(profile["vutext_exclude"]["size"])
    if vutext_sec != (expected_vutext_start, expected_vutext_size):
        raise RuntimeError(
            f"Unexpected .vutext bounds {vutext_sec} (expected (0x{expected_vutext_start:08X}, 0x{expected_vutext_size:X}))"
        )

    return {
        "entry": e_entry,
        "section_count": e_shnum,
        "reloc_count": len(reloc_sections),
        "vutext_start": vutext_sec[0],
        "vutext_size": vutext_sec[1],
    }


def validate_iso(iso_path, profile, verify_full_disc=False):
    serial = profile["serial"]
    version = profile["version"]
    disc = profile["disc"]
    expected_disc_size = int(disc["size"])
    expected_disc_sha = disc["sha256"]

    if not os.path.isfile(iso_path):
        raise RuntimeError(
            f"ISO not found: {iso_path}. Required release: {serial} v{version} (expected SHA-256 {expected_disc_sha})."
        )

    actual_size = os.path.getsize(iso_path)
    if actual_size != expected_disc_size:
        sample_sha = sha256_file(iso_path) if actual_size <= 64 * 1024 * 1024 else "<skipped >64MiB>"
        raise RuntimeError(
            f"Unsupported or corrupted disc image '{iso_path}' for {serial} v{version}: "
            f"expected size {expected_disc_size} bytes (SHA-256 {expected_disc_sha}), "
            f"got {actual_size} bytes (SHA-256 {sample_sha})."
        )

    if verify_full_disc:
        actual_disc_sha = sha256_file(iso_path)
        if actual_disc_sha != expected_disc_sha:
            raise RuntimeError(
                f"Full-disc SHA-256 mismatch for {serial} v{version}: "
                f"expected {expected_disc_sha}, got {actual_disc_sha}."
            )

    try:
        iso = Iso9660(iso_path)
    except Exception as exc:
        raise RuntimeError(
            f"Invalid ISO9660 image '{iso_path}' for {serial} v{version} "
            f"(expected disc SHA-256 {expected_disc_sha}): {exc}"
        ) from exc

    info = iso.info()
    if info["logical_block_size"] != int(disc["sector_size"]) or info["volume_space_size"] != int(disc["sectors"]):
        raise RuntimeError(
            f"Unexpected ISO9660 geometry for {serial} v{version}: "
            f"sector={info['logical_block_size']} count={info['volume_space_size']}"
        )

    verified_files = []
    for item in profile["required_files"]:
        rel = item["path"]
        entry = iso.find(rel)
        if not entry or entry.is_dir:
            raise RuntimeError(f"Missing required disc file '{rel}' in {serial} v{version} ISO")
        if entry.size != int(item["size"]):
            raise RuntimeError(
                f"Size mismatch for '{rel}' in {serial} v{version}: expected {item['size']}, got {entry.size}"
            )
        data = iso.read_extent(entry.lba, entry.size)
        actual_sha = sha256_bytes(data)
        if actual_sha != item["sha256"]:
            raise RuntimeError(
                f"SHA-256 mismatch for '{rel}' in {serial} v{version}: "
                f"expected {item['sha256']}, got {actual_sha}"
            )
        verified_files.append((rel, entry.size, actual_sha))

    elf_spec = profile["boot_elf"]
    elf_entry = iso.find(elf_spec["disc_path"])
    if not elf_entry or elf_entry.is_dir:
        raise RuntimeError(f"Missing boot ELF '{elf_spec['disc_path']}' in {serial} v{version} ISO")
    if elf_entry.size != int(elf_spec["size"]):
        raise RuntimeError(
            f"Boot ELF size mismatch for '{elf_spec['disc_path']}' in {serial} v{version}: "
            f"expected {elf_spec['size']}, got {elf_entry.size}"
        )
    elf_bytes = iso.read_extent(elf_entry.lba, elf_entry.size)
    actual_elf_sha = sha256_bytes(elf_bytes)
    if actual_elf_sha != elf_spec["sha256"]:
        raise RuntimeError(
            f"Boot ELF SHA-256 mismatch for '{elf_spec['disc_path']}' in {serial} v{version}: "
            f"expected {elf_spec['sha256']}, got {actual_elf_sha}"
        )
    verified_files.append((elf_spec["disc_path"], elf_entry.size, actual_elf_sha))

    elf_info = validate_elf_structure(elf_bytes, profile)
    return elf_bytes, elf_info, verified_files


def main():
    ap = argparse.ArgumentParser(description="Validate Rule of Rose (SLUS-21448 v1.00) ISO and prepare build artifacts")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, help="Path to SLUS-21448_v1.00.json")
    ap.add_argument("--iso", help="Path to Rule of Rose (USA) ISO image")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "prepare"), help="Git-ignored preparation directory")
    ap.add_argument("--emit-header", help="Optional path to emit rozu_layout_generated.h")
    ap.add_argument("--emit-header-only", action="store_true", help="Emit layout header from profile without reading an ISO")
    ap.add_argument("--validate-only", action="store_true", help="Validate ISO and ELF without extracting SLUS_214.48")
    ap.add_argument("--verify-full-disc-sha256", action="store_true", help="Also verify full 3.2 GiB disc SHA-256")
    args = ap.parse_args()

    profile = load_profile(args.profile)

    if args.emit_header:
        wrote = emit_layout_header(profile, args.emit_header)
        print(f"header: {args.emit_header} ({'written' if wrote else 'up to date'})")
        if args.emit_header_only:
            return 0

    if not args.iso:
        ap.error("--iso is required unless --emit-header-only is specified")

    try:
        elf_bytes, elf_info, verified_files = validate_iso(
            args.iso, profile, verify_full_disc=args.verify_full_disc_sha256
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    print(f"verified disc: {profile['title']} ({profile['serial']} v{profile['version']}, {profile['vmode']})")
    print(f"verified files: {len(verified_files)}/{len(verified_files)} SHA-256 checks passed")
    print(
        f"verified ELF: entry=0x{elf_info['entry']:08X} sections={elf_info['section_count']} "
        f"relocs={elf_info['reloc_count']} .vutext=0x{elf_info['vutext_start']:08X}+0x{elf_info['vutext_size']:X}"
    )

    if not args.validate_only:
        os.makedirs(args.out, exist_ok=True)
        elf_out = os.path.join(args.out, profile["boot_elf"]["disc_path"])
        tmp_out = elf_out + ".tmp"
        with open(tmp_out, "wb") as f:
            f.write(elf_bytes)
        os.replace(tmp_out, elf_out)
        print(f"extracted boot ELF: {elf_out} ({len(elf_bytes)} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
