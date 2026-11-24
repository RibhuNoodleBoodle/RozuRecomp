#!/usr/bin/env python3
"""Rule of Rose (SLUS-21448 v1.00) ISO9660 validator, ELF checker, and layout header emitter."""

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

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


SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHF_ALLOC = 2
SHF_EXECINSTR = 4
STB_GLOBAL = 1
STT_FUNC = 2

VERIFIED_SDK_NAMES = {
    0x0024B490: ("sceCdCallback", "sdk_libcdvd"),
    0x0024B668: ("sceCdInitEeCB", "sdk_libcdvd"),
    0x0024BA98: ("sceCdLayerSearchFile", "sdk_libcdvd"),
    0x0024BD98: ("sceCdSearchFile", "sdk_libcdvd"),
    0x0024BF10: ("sceCdNcmdDiskReady", "sdk_libcdvd"),
    0x0024BFA8: ("sceCdSync", "sdk_libcdvd"),
    0x0024C048: ("sceCdSyncS", "sdk_libcdvd"),
    0x0024C2C0: ("sceCdInit", "sdk_libcdvd"),
    0x0024C7C0: ("sceCdDiskReady", "sdk_libcdvd"),
    0x0024C9E0: ("sceCdRead", "sdk_libcdvd"),
    0x0024CC58: ("sceCdGetDiskType", "sdk_libcdvd"),
    0x0024CC80: ("sceCdGetError", "sdk_libcdvd"),
    0x0024CD18: ("sceCdStatus", "sdk_libcdvd"),
    0x0024CF78: ("sceCdMmode", "sdk_libcdvd"),
    0x0024D070: ("sceCdReadClock", "sdk_libcdvd"),
    0x0024D130: ("sceCdTrayReq", "sdk_libcdvd"),
    0x0024D220: ("sceMcInit", "sdk_libmc"),
    0x0024D448: ("sceMcEnd", "sdk_libmc"),
    0x0024D4B0: ("sceMcChangeThreadPriority", "sdk_libmc"),
    0x0024D570: ("sceMcGetSlotMax", "sdk_libmc"),
    0x0024D630: ("sceMcOpen", "sdk_libmc"),
    0x0024D758: ("sceMcMkdir", "sdk_libmc"),
    0x0024D790: ("sceMcClose", "sdk_libmc"),
    0x0024D850: ("sceMcSeek", "sdk_libmc"),
    0x0024D930: ("mceIntrReadFixAlign", "sdk_libmc"),
    0x0024D9E0: ("sceMcRead", "sdk_libmc"),
    0x0024DAF8: ("sceMcWrite", "sdk_libmc"),
    0x0024DC70: ("sceMcSync", "sdk_libmc"),
    0x0024DD38: ("mceGetInfoApdx", "sdk_libmc"),
    0x0024DD90: ("sceMcGetInfo", "sdk_libmc"),
    0x0024DF80: ("sceMcGetDir", "sdk_libmc"),
    0x0024E0D0: ("mceStorePwd", "sdk_libmc"),
    0x0024E160: ("sceMcChdir", "sdk_libmc"),
    0x0024E2A0: ("sceMcFormat", "sdk_libmc"),
    0x0024E370: ("sceMcDelete", "sdk_libmc"),
    0x0024E490: ("sceMcFlush", "sdk_libmc"),
    0x0024E550: ("sceMcSetFileInfo", "sdk_libmc"),
    0x0024E720: ("sceMcRename", "sdk_libmc"),
    0x0024E878: ("sceMcUnformat", "sdk_libmc"),
    0x0024E948: ("sceMcGetEntSpace", "sdk_libmc"),
    0x0024EB28: ("sceMpegCreate", "sdk_libmpeg"),
    0x0024F6D0: ("sceMpegInit", "sdk_libmpeg"),
    0x0024F788: ("sceMpegAddBs", "sdk_libmpeg"),
    0x0024F7C8: ("sceMpegGetPicture", "sdk_libmpeg"),
    0x0024F810: ("sceMpegGetPictureRAW8", "sdk_libmpeg"),
    0x0024F868: ("sceMpegReset", "sdk_libmpeg"),
    0x0024F8F8: ("sceMpegIsEnd", "sdk_libmpeg"),
    0x0024F908: ("sceMpegSetDecodeMode", "sdk_libmpeg"),
    0x0024F920: ("sceMpegGetDecodeMode", "sdk_libmpeg"),
    0x0024F940: ("sceMpegAddCallback", "sdk_libmpeg"),
    0x0024FAF8: ("sceMpegClearRefBuff", "sdk_libmpeg"),
    0x0024FB50: ("sceMpegGetPictureRAW8xy", "sdk_libmpeg"),
    0x0024FBA0: ("sceMpegSetDefaultPtsGap", "sdk_libmpeg"),
    0x0024FBB8: ("sceMpegResetDefaultPtsGap", "sdk_libmpeg"),
    0x0024FBE0: ("sceMpegDispWidth", "sdk_libmpeg"),
    0x0024FBF0: ("sceMpegDispHeight", "sdk_libmpeg"),
    0x0024FC00: ("sceMpegDispCenterOffX", "sdk_libmpeg"),
    0x0024FC10: ("sceMpegDispCenterOffY", "sdk_libmpeg"),
    0x0024FC20: ("sceMpegIsRefBuffEmpty", "sdk_libmpeg"),
    0x00250798: ("sceMpegFlush", "sdk_libmpeg"),
    0x002539C0: ("sceMpegDemuxPssRing", "sdk_libmpeg"),
    0x00253DA0: ("sceMpegDemuxPss", "sdk_libmpeg"),
    0x00253DC0: ("sceMpegAddStrCallback", "sdk_libmpeg"),
    0x0025DEA8: ("write", "sdk_fio"),
    0x0025DF28: ("read", "sdk_fio"),
    0x0025E9E8: ("sceTtyHandler", "sdk_tty"),
    0x0025EB80: ("sceTtyWrite", "sdk_tty"),
    0x0025ECF8: ("sceTtyRead", "sdk_tty"),
    0x0025EDC8: ("sceTtyInit", "sdk_tty"),
    0x00260110: ("scePrintf", "sdk_tty"),
    0x00260288: ("sceSifInitCmd", "sdk_sif"),
    0x00260508: ("sceSifExitCmd", "sdk_sif"),
    0x00260570: ("sceSifAddCmdHandler", "sdk_sif"),
    0x002605E8: ("sceSifRemoveCmdHandler", "sdk_sif"),
    0x00260770: ("sceSifSendCmd", "sdk_sif"),
    0x002607F0: ("sceSifCmdIntrHdlr", "sdk_sif"),
    0x00260938: ("sceSifWriteBackDCache", "sdk_sif"),
    0x002609E8: ("sceSifInitRpc", "sdk_sif"),
    0x00260C78: ("sceRpcGetFPacket", "sdk_sif"),
    0x00260CA8: ("sceRpcGetFPacket2", "sdk_sif"),
    0x00260EC8: ("sceSifGetOtherData", "sdk_sif"),
    0x00261190: ("sceSifBindRpc", "sdk_sif"),
    0x00261370: ("sceSifCallRpc", "sdk_sif"),
    0x00261570: ("sceSifCheckStatRpc", "sdk_sif"),
    0x002615B0: ("sceSifSetRpcQueue", "sdk_sif"),
    0x00261648: ("sceSifRegisterRpc", "sdk_sif"),
    0x00261718: ("sceSifRemoveRpc", "sdk_sif"),
    0x002617B0: ("sceSifRemoveRpcQueue", "sdk_sif"),
    0x00261840: ("sceSifGetNextRequest", "sdk_sif"),
    0x00261898: ("sceSifExecRequest", "sdk_sif"),
    0x00261A60: ("sceSifRpcLoop", "sdk_sif"),
    0x002622B0: ("sceFsInit", "sdk_fio"),
    0x00262548: ("sceFsReset", "sdk_fio"),
    0x002627B0: ("sceOpen", "sdk_fio"),
    0x00262A40: ("sceClose", "sdk_fio"),
    0x00262BB8: ("sceLseek", "sdk_fio"),
    0x00262DF8: ("sceRead", "sdk_fio"),
    0x00263068: ("sceWrite", "sdk_fio"),
    0x00263328: ("sceIoctl", "sdk_fio"),
    0x002656D8: ("sceSifInitIopHeap", "sdk_sif"),
    0x00265760: ("sceSifAllocIopHeap", "sdk_sif"),
    0x002657D0: ("sceSifAllocSysMemory", "sdk_sif"),
    0x002658E8: ("sceSifLoadIopHeap", "sdk_sif"),
    0x00265DB8: ("sceSifLoadFileReset", "sdk_sif"),
    0x00265FF8: ("sceSifStopModule", "sdk_sif"),
    0x002663C0: ("sceSifLoadModuleBuffer", "sdk_sif"),
    0x00266628: ("sceSifLoadModule", "sdk_sif"),
    0x00266668: ("sceSifLoadElfPart", "sdk_sif"),
    0x00266790: ("sceSifLoadElf", "sdk_sif"),
    0x002667B8: ("sceSifGetIopAddr", "sdk_sif"),
    0x002668A8: ("sceSifSetIopAddr", "sdk_sif"),
    0x00266988: ("sceSifResetIop", "sdk_sif"),
    0x00266AE0: ("sceSifIsAliveIop", "sdk_sif"),
    0x00266B08: ("sceSifSyncIop", "sdk_sif"),
    0x00266B58: ("sceSifRebootIop", "sdk_sif"),
    0x00269710: ("sceDeci2Open", "sdk_deci2"),
    0x00269758: ("sceDeci2Close", "sdk_deci2"),
    0x00269780: ("sceDeci2ReqSend", "sdk_deci2"),
    0x002697B0: ("sceDeci2Poll", "sdk_deci2"),
    0x00269830: ("sceDeci2ExRecv", "sdk_deci2"),
    0x00269868: ("sceDeci2ExSend", "sdk_deci2"),
    0x002698A0: ("sceDeci2ExReqSend", "sdk_deci2"),
    0x002698D0: ("sceDeci2ExLock", "sdk_deci2"),
    0x002698F8: ("sceDeci2ExUnLock", "sdk_deci2"),
    0x00269A38: ("sceIpuStopDMA", "sdk_libipu"),
    0x00269B20: ("sceIpuRestartDMA", "sdk_libipu"),
    0x00269C70: ("sceIpuSync", "sdk_libipu"),
    0x00269D50: ("sceIpuInit", "sdk_libipu"),
}

_CPP_RESERVED = {
    "alignas", "alignof", "and", "and_eq", "asm", "auto", "bitand", "bitor",
    "bool", "break", "case", "catch", "char", "class", "compl", "const",
    "constexpr", "continue", "default", "delete", "do", "double", "else",
    "enum", "explicit", "export", "extern", "false", "float", "for", "friend",
    "goto", "if", "inline", "int", "long", "mutable", "namespace", "new",
    "noexcept", "not", "not_eq", "nullptr", "operator", "or", "or_eq",
    "private", "protected", "public", "register", "return", "short", "signed",
    "sizeof", "static", "struct", "switch", "template", "this", "throw",
    "true", "try", "typedef", "typeid", "typename", "union", "unsigned",
    "using", "virtual", "void", "volatile", "while", "xor", "xor_eq",
}


def parse_elf32(elf_bytes):
    e_entry, e_phoff, e_shoff = struct.unpack_from("<III", elf_bytes, 24)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", elf_bytes, 46)
    shstr_sh = struct.unpack_from("<10I", elf_bytes, e_shoff + e_shstrndx * e_shentsize)
    shstr_off, shstr_size = shstr_sh[4], shstr_sh[5]
    shstr = elf_bytes[shstr_off : shstr_off + shstr_size]
    sections = []
    for i in range(e_shnum):
        sh = list(struct.unpack_from("<10I", elf_bytes, e_shoff + i * e_shentsize))
        name_off = sh[0]
        end = shstr.find(b"\0", name_off)
        name = shstr[name_off:end].decode("ascii", "replace")
        sections.append(
            {
                "index": i,
                "name": name,
                "sh": sh,
                "type": sh[1],
                "flags": sh[2],
                "addr": sh[3],
                "offset": sh[4],
                "size": sh[5],
                "link": sh[6],
                "info": sh[7],
                "align": sh[8],
                "entsize": sh[9],
            }
        )
    return {
        "entry": e_entry,
        "phoff": e_phoff,
        "shoff": e_shoff,
        "shentsize": e_shentsize,
        "shnum": e_shnum,
        "shstrndx": e_shstrndx,
        "sections": sections,
    }


def sanitize_ident(raw):
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "fn"
    if cleaned[0].isdigit() or cleaned in _CPP_RESERVED:
        cleaned = f"fn_{cleaned}"
    return cleaned


def find_analyzer_binary(explicit_path):
    if explicit_path:
        if os.path.isfile(explicit_path):
            return explicit_path
        raise RuntimeError(f"Explicit --analyzer not found: {explicit_path}")
    candidates = [
        os.path.join(ROOT, "build", "linux", "External", "PS2Recomp", "ps2xAnalyzer", "ps2_analyzer"),
        os.path.join(ROOT, "build", "Release", "External", "PS2Recomp", "ps2xAnalyzer", "ps2_analyzer.exe"),
        shutil.which("ps2_analyzer") or "",
    ]
    for cand in candidates:
        if cand and os.path.isfile(cand):
            return cand
    raise RuntimeError("Could not locate ps2_analyzer binary; pass --analyzer <path>")


def parse_analyzer_toml(toml_path):
    with open(toml_path, "rb") as f:
        raw_bytes = f.read()
    symbols = {}
    jump_targets = set()
    if tomllib is not None:
        doc = tomllib.loads(raw_bytes.decode("utf-8", "replace"))
        gen = doc.get("general", {})
        for key in ("stubs", "entry_points"):
            for item in gen.get(key, []):
                if isinstance(item, str) and "@" in item:
                    name, addr_s = item.rsplit("@", 1)
                    addr = int(addr_s, 16)
                    symbols.setdefault(addr, (name, f"analyzer_{key}"))
        jts = doc.get("jump_tables", [])
        if isinstance(jts, list):
            for jt in jts:
                for ent in jt.get("entries", []):
                    tgt = ent.get("target")
                    if isinstance(tgt, str):
                        jump_targets.add(int(tgt, 16))
        return symbols, jump_targets

    text = raw_bytes.decode("utf-8", "replace")
    for m in re.finditer(r'"([A-Za-z0-9_.$]+)@(0x[0-9a-fA-F]+)"', text):
        symbols.setdefault(int(m.group(2), 16), (m.group(1), "analyzer"))
    for m in re.finditer(r'target\s*=\s*"(0x[0-9a-fA-F]+)"', text):
        jump_targets.add(int(m.group(1), 16))
    return symbols, jump_targets


def run_analyzer(elf_path, out_dir, analyzer_bin):
    analyzer_dir = os.path.join(out_dir, "analyzer")
    os.makedirs(analyzer_dir, exist_ok=True)
    toml_path = os.path.join(analyzer_dir, "analyzed.toml")
    proc = subprocess.run(
        [analyzer_bin, elf_path, toml_path],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not os.path.isfile(toml_path):
        raise RuntimeError(
            f"ps2_analyzer failed (rc={proc.returncode}): {proc.stderr or proc.stdout}"
        )
    return toml_path


def _is_rel_branch(word):
    op = word >> 26
    if op in (4, 5, 6, 7, 20, 21, 22, 23):
        return True
    if op == 1 and ((word >> 16) & 0x1F) in (0, 1, 2, 3, 16, 17, 18, 19):
        return True
    if op in (16, 17, 18) and ((word >> 21) & 0x1F) == 8:
        return True
    return False


def _has_delay_slot(word):
    op = word >> 26
    if op in (2, 3):  # j, jal
        return True
    if op == 0 and (word & 0x3F) in (8, 9):  # jr, jalr
        return True
    return _is_rel_branch(word)


def collect_elf_targets(elf_bytes, parsed_elf, profile):
    vutext_start = parse_hex(profile["vutext_exclude"]["start"])
    vutext_end = parse_hex(profile["vutext_exclude"]["end"])
    sections = parsed_elf["sections"]
    exec_secs = [
        s
        for s in sections
        if (s["flags"] & SHF_EXECINSTR)
        and s["addr"] != 0
        and s["size"] > 0
        and s["name"] != ".vutext"
        and not s["name"].startswith(".DVP.overlay.")
    ]
    exec_secs.sort(key=lambda s: s["addr"])
    exec_ranges = [(s["addr"], s["addr"] + s["size"]) for s in exec_secs]

    def in_exec(va):
        for a, b in exec_ranges:
            if a <= va < b:
                return True
        return False

    jals = set()
    for s in exec_secs:
        a, o, sz = s["addr"], s["offset"], s["size"]
        for pos in range(0, sz - 3, 4):
            w = struct.unpack_from("<I", elf_bytes, o + pos)[0]
            if (w >> 26) == 3:
                tgt = ((a + pos) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
                if in_exec(tgt):
                    jals.add(tgt)

    vtable_ptrs = set()
    ctors_dtors = set()
    data_rodata_ptrs = set()
    for s in sections:
        if s["name"].startswith(".gnu.linkonce.d.") and s["size"] >= 8:
            for pos in range(4, s["size"] - 3, 8):
                ptr = struct.unpack_from("<I", elf_bytes, s["offset"] + pos)[0]
                if ptr != 0 and (ptr & 3) == 0 and in_exec(ptr):
                    vtable_ptrs.add(ptr)
        elif s["name"] in (".ctors", ".dtors"):
            for pos in range(0, s["size"] - 3, 4):
                ptr = struct.unpack_from("<I", elf_bytes, s["offset"] + pos)[0]
                if ptr not in (0, 0xFFFFFFFF) and (ptr & 3) == 0 and in_exec(ptr):
                    ctors_dtors.add(ptr)
        elif s["name"] in (".data", ".sdata", ".rodata"):
            for pos in range(0, s["size"] - 3, 4):
                ptr = struct.unpack_from("<I", elf_bytes, s["offset"] + pos)[0]
                if ptr != 0 and (ptr & 3) == 0 and in_exec(ptr):
                    data_rodata_ptrs.add(ptr)

    linkonce_t = [s for s in exec_secs if s["name"].startswith(".gnu.linkonce.t.")]
    return {
        "vutext_start": vutext_start,
        "vutext_end": vutext_end,
        "exec_secs": exec_secs,
        "linkonce_t": linkonce_t,
        "jals": jals,
        "vtable_ptrs": vtable_ptrs,
        "ctors_dtors": ctors_dtors,
        "data_rodata_ptrs": data_rodata_ptrs,
    }


def discover_functions(elf_bytes, parsed_elf, profile, analyzer_symbols, jump_targets):
    info = collect_elf_targets(elf_bytes, parsed_elf, profile)
    exec_secs = info["exec_secs"]
    linkonce_t = info["linkonce_t"]
    jals = info["jals"]
    vtable_ptrs = info["vtable_ptrs"]
    ctors_dtors = info["ctors_dtors"]
    data_rodata_ptrs = info["data_rodata_ptrs"]
    e_entry = parsed_elf["entry"]

    text_secs = [s for s in exec_secs if s["name"] == ".text"]
    if len(text_secs) != 1:
        raise RuntimeError(f"Expected 1 .text section, found {len(text_secs)}")
    text_sec = text_secs[0]
    ta, to, ts = text_sec["addr"], text_sec["offset"], text_sec["size"]
    n_words = ts // 4
    words = struct.unpack_from(f"<{n_words}I", elf_bytes, to)

    # Branch spans + delay slots prevent splitting inside control-flow bodies.
    cov = [0] * (n_words + 1)
    for i, w in enumerate(words):
        if _has_delay_slot(w) and i + 1 < n_words:
            cov[i + 1] += 1
            cov[i + 2] -= 1
        if _is_rel_branch(w):
            imm = w & 0xFFFF
            if imm >= 0x8000:
                imm -= 0x10000
            tgt_i = i + 1 + imm
            if 0 <= tgt_i < n_words:
                lo = min(i, tgt_i) + 1
                hi = max(i, tgt_i)
                if lo <= hi:
                    cov[lo] += 1
                    cov[hi + 1] -= 1
    for i in range(1, n_words):
        cov[i] += cov[i - 1]

    def can_split_text(va):
        if not (ta <= va < ta + ts) or (va & 3) != 0:
            return False
        idx = (va - ta) // 4
        return cov[idx] == 0

    text_starts = {}  # va -> provenance

    def add_text(va, prov, overwrite=False, force=False):
        if not (ta <= va < ta + ts) or (va & 3) != 0:
            return
        if not force and not can_split_text(va):
            return
        if overwrite or va not in text_starts:
            text_starts[va] = prov

    if ta < e_entry < ta + ts:
        add_text(ta, "crt0_align", force=True)
    add_text(e_entry, "crt0_entry", overwrite=True, force=True)

    for va in sorted(VERIFIED_SDK_NAMES):
        if ta <= va < ta + ts:
            add_text(va, VERIFIED_SDK_NAMES[va][1], overwrite=True, force=True)

    for va in sorted(jals):
        add_text(va, "jal_target", force=True)

    for va in sorted(vtable_ptrs):
        add_text(va, "vtable_slot", force=True)

    for va in sorted(ctors_dtors):
        add_text(va, "ctor_dtor", force=True)

    # Analyzer candidates inside .text, excluding switch targets and branch spans.
    sdk_region_end = 0x0026E000
    sdk_region_start = 0x0024B000
    for va, (sym_name, prov) in sorted(analyzer_symbols.items()):
        if va not in jump_targets:
            add_text(va, prov)

    # Post-return / post-tail-jump boundaries when uncovered by internal branches.
    all_confirmed_targets = jals | vtable_ptrs | ctors_dtors | set(analyzer_symbols.keys())
    for i, w in enumerate(words):
        is_ret = w == 0x03E00008
        is_j = (w >> 26) == 2
        op = w >> 26
        is_back_uncond_b = op == 4 and ((w >> 16) & 0x3FF) == 0 and (w & 0xFFFF) >= 0x8000
        if not (is_ret or is_j or is_back_uncond_b):
            continue
        nxt = i + 2
        while nxt < n_words and words[nxt] == 0:
            nxt += 1
        if nxt < n_words and cov[nxt] == 0:
            va = ta + nxt * 4
            if va in jump_targets:
                continue
            if is_ret:
                add_text(va, "post_jr_ra")
            else:
                near_sp = any(
                    (words[k] & 0xFFFF0000) == 0x27BD0000 and (words[k] & 0xFFFF) >= 0x8000
                    for k in range(nxt, min(nxt + 5, n_words))
                )
                if is_j:
                    j_tgt = ((ta + i * 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
                    if near_sp or j_tgt in all_confirmed_targets:
                        add_text(va, "post_tail_j")
                elif near_sp:
                    add_text(va, "post_back_b")

    # Remaining non-switch .data/.sdata/.rodata code pointers uncovered by branches.
    for va in sorted(data_rodata_ptrs):
        if va in jump_targets or not can_split_text(va):
            continue
        idx = (va - ta) // 4
        w0 = words[idx]
        looks_prologue = (w0 & 0xFFFF0000) == 0x27BD0000 and (w0 & 0xFFFF) >= 0x8000
        prev_ret = any(
            idx - back >= 0 and words[idx - back] == 0x03E00008 and back >= 2
            for back in range(2, 6)
        )
        if looks_prologue or prev_ret:
            add_text(va, "rodata_data_ptr")

    sorted_text = sorted(text_starts.keys())
    if not sorted_text or sorted_text[0] != ta:
        raise RuntimeError(".text partition must begin at section start")

    functions = []
    used_names = {name for name, _ in VERIFIED_SDK_NAMES.values()}
    used_names.add("_start")
    used_names.add("crt0_align_00100000")

    def choose_text_name(va, prov):
        if va == e_entry:
            return "_start"
        if va == ta and ta < e_entry:
            return "crt0_align_00100000"
        if va in VERIFIED_SDK_NAMES:
            return VERIFIED_SDK_NAMES[va][0]
        if va in analyzer_symbols and sdk_region_start <= va < sdk_region_end:
            base = sanitize_ident(analyzer_symbols[va][0])
            if base not in used_names:
                used_names.add(base)
                return base
            unique = f"{base}_{va:08x}"
            used_names.add(unique)
            return unique
        name = f"sub_{va:08x}"
        used_names.add(name)
        return name

    for idx, start in enumerate(sorted_text):
        end = sorted_text[idx + 1] if idx + 1 < len(sorted_text) else ta + ts
        prov = text_starts[start]
        name = choose_text_name(start, prov)
        functions.append(
            {
                "name": name,
                "start": start,
                "end": end,
                "size": end - start,
                "section": ".text",
                "shndx": text_sec["index"],
                "provenance": prov,
            }
        )

    for s in linkonce_t:
        start = s["addr"]
        end = start + s["size"]
        suffix = s["name"][len(".gnu.linkonce.t.") :]
        base = sanitize_ident(f"fn_{start:08x}_{suffix[:48]}")
        while base in used_names:
            base = f"{base}_{start:08x}"
        used_names.add(base)
        functions.append(
            {
                "name": base,
                "start": start,
                "end": end,
                "size": end - start,
                "section": s["name"],
                "shndx": s["index"],
                "provenance": "linkonce_t",
            }
        )

    functions.sort(key=lambda fn: fn["start"])
    return functions, info


def build_annotated_elf(elf_bytes, parsed_elf, functions):
    out = bytearray(elf_bytes)
    sections = parsed_elf["sections"]
    shstr_sec = sections[parsed_elf["shstrndx"]]
    old_shstr = bytes(elf_bytes[shstr_sec["offset"] : shstr_sec["offset"] + shstr_sec["size"]])

    # Build .strtab with leading NUL.
    strtab = bytearray(b"\x00")
    symtab = bytearray(struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0))  # STN_UNDEF
    for fn in functions:
        name_off = len(strtab)
        strtab.extend(fn["name"].encode("ascii"))
        strtab.append(0)
        st_info = (STB_GLOBAL << 4) | STT_FUNC
        symtab.extend(
            struct.pack(
                "<IIIBBH",
                name_off,
                fn["start"],
                fn["size"],
                st_info,
                0,
                fn["shndx"],
            )
        )

    # Extend .shstrtab with .strtab and .symtab section names.
    new_shstr = bytearray(old_shstr)
    if not new_shstr.endswith(b"\x00"):
        new_shstr.append(0)
    strtab_name_off = len(new_shstr)
    new_shstr.extend(b".strtab\x00")
    symtab_name_off = len(new_shstr)
    new_shstr.extend(b".symtab\x00")

    while len(out) % 4 != 0:
        out.append(0)
    strtab_idx = len(sections)
    symtab_idx = len(sections) + 1

    strtab_off = len(out)
    out.extend(strtab)
    while len(out) % 4 != 0:
        out.append(0)

    symtab_off = len(out)
    out.extend(symtab)
    while len(out) % 4 != 0:
        out.append(0)

    new_shstr_off = len(out)
    out.extend(new_shstr)
    while len(out) % 4 != 0:
        out.append(0)

    shdrs = []
    for s in sections:
        sh = list(s["sh"])
        if s["name"] == ".vutext":
            sh[2] = sh[2] & ~SHF_EXECINSTR
        elif s["index"] == parsed_elf["shstrndx"]:
            sh[4] = new_shstr_off
            sh[5] = len(new_shstr)
        shdrs.append(sh)

    shdrs.append([strtab_name_off, SHT_STRTAB, 0, 0, strtab_off, len(strtab), 0, 0, 1, 0])
    shdrs.append([symtab_name_off, SHT_SYMTAB, 0, 0, symtab_off, len(symtab), strtab_idx, 1, 4, 16])

    new_e_shoff = len(out)
    for sh in shdrs:
        out.extend(struct.pack("<10I", *sh))

    struct.pack_into("<I", out, 32, new_e_shoff)
    struct.pack_into("<H", out, 48, len(shdrs))
    return bytes(out)


def write_phase2_outputs(out_dir, profile, elf_bytes, parsed_elf, functions, discovery_info, address_map_path, analyzer_toml):
    os.makedirs(out_dir, exist_ok=True)
    header_path = os.path.join(out_dir, "rozu_layout_generated.h")
    emit_layout_header(profile, header_path)

    annotated_bytes = build_annotated_elf(elf_bytes, parsed_elf, functions)
    annotated_path = os.path.join(out_dir, "slus_21448_annotated.elf")
    with open(annotated_path + ".tmp", "wb") as f:
        f.write(annotated_bytes)
    os.replace(annotated_path + ".tmp", annotated_path)

    csv_path = os.path.join(out_dir, "rozu_functions.csv")
    with open(csv_path + ".tmp", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["name", "start", "end", "size"])
        for fn in functions:
            w.writerow([fn["name"], f"0x{fn['start']:08X}", f"0x{fn['end']:08X}", f"0x{fn['size']:X}"])
    os.replace(csv_path + ".tmp", csv_path)

    if address_map_path:
        os.makedirs(os.path.dirname(os.path.abspath(address_map_path)), exist_ok=True)
        with open(address_map_path + ".tmp", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["address", "end", "size", "name", "section", "provenance"])
            for fn in functions:
                w.writerow(
                    [
                        f"0x{fn['start']:08X}",
                        f"0x{fn['end']:08X}",
                        f"0x{fn['size']:X}",
                        fn["name"],
                        fn["section"],
                        fn["provenance"],
                    ]
                )
        os.replace(address_map_path + ".tmp", address_map_path)

    prov_counts = {}
    for fn in functions:
        prov_counts[fn["provenance"]] = prov_counts.get(fn["provenance"], 0) + 1

    report_path = os.path.join(out_dir, "prepare_report.txt")
    lines = [
        f"RozuRecomp prepare report: {profile['title']} ({profile['serial']} v{profile['version']})",
        f"boot_elf: {os.path.join(out_dir, profile['boot_elf']['disc_path'])} ({len(elf_bytes)} bytes)",
        f"annotated_elf: {annotated_path} ({len(annotated_bytes)} bytes)",
        f"analyzer_toml: {analyzer_toml}",
        f"rozu_functions_csv: {csv_path} ({len(functions)} functions)",
        f"vutext_excluded: 0x{discovery_info['vutext_start']:08X}..0x{discovery_info['vutext_end']:08X} (SHF_EXECINSTR cleared)",
        f"jal_targets: {len(discovery_info['jals'])}",
        f"vtable_slot_targets: {len(discovery_info['vtable_ptrs'])}",
        f"linkonce_t_sections: {len(discovery_info['linkonce_t'])}",
        "provenance_breakdown:",
    ]
    for k in sorted(prov_counts):
        lines.append(f"  {k}: {prov_counts[k]}")
    with open(report_path + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(report_path + ".tmp", report_path)


def verify_prepare_output(out_dir, profile):
    raw_elf_path = os.path.join(out_dir, profile["boot_elf"]["disc_path"])
    ann_elf_path = os.path.join(out_dir, "slus_21448_annotated.elf")
    csv_path = os.path.join(out_dir, "rozu_functions.csv")
    hdr_path = os.path.join(out_dir, "rozu_layout_generated.h")
    rpt_path = os.path.join(out_dir, "prepare_report.txt")

    for req in (raw_elf_path, ann_elf_path, csv_path, hdr_path, rpt_path):
        if not os.path.isfile(req):
            raise RuntimeError(f"Missing prepared artifact: {req}")

    with open(raw_elf_path, "rb") as f:
        raw_bytes = f.read()
    with open(ann_elf_path, "rb") as f:
        ann_bytes = f.read()

    validate_elf_structure(raw_bytes, profile)
    raw_parsed = parse_elf32(raw_bytes)
    ann_parsed = parse_elf32(ann_bytes)
    info = collect_elf_targets(raw_bytes, raw_parsed, profile)

    vutext_secs = [s for s in ann_parsed["sections"] if s["name"] == ".vutext"]
    if len(vutext_secs) != 1:
        raise RuntimeError(f"Annotated ELF expected 1 .vutext section, got {len(vutext_secs)}")
    vutext_flags = vutext_secs[0]["flags"]
    if (vutext_flags & SHF_EXECINSTR) != 0 or (vutext_flags & SHF_ALLOC) == 0:
        raise RuntimeError(f".vutext flags in annotated ELF invalid: 0x{vutext_flags:X}")

    symtab_secs = [s for s in ann_parsed["sections"] if s["name"] == ".symtab" and s["type"] == SHT_SYMTAB]
    if len(symtab_secs) != 1 or symtab_secs[0]["size"] <= 16:
        raise RuntimeError("Annotated ELF missing populated .symtab")

    rows = []
    seen_names = set()
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["name"]
            start = int(row["start"], 0)
            end = int(row["end"], 0)
            size = int(row["size"], 0)
            if not name or name in seen_names:
                raise RuntimeError(f"Duplicate or empty CSV function name: {name!r}")
            seen_names.add(name)
            if start >= end or (end - start) != size or (start & 3) or (end & 3):
                raise RuntimeError(f"Invalid CSV bounds for {name}: 0x{start:08X}..0x{end:08X} size=0x{size:X}")
            if not (end <= info["vutext_start"] or start >= info["vutext_end"]):
                raise RuntimeError(f"Function {name} @ 0x{start:08X} intersects .vutext!")
            rows.append((start, end, name))

    rows.sort()
    for i in range(len(rows) - 1):
        if rows[i][1] > rows[i + 1][0]:
            raise RuntimeError(
                f"Overlapping functions: {rows[i][2]} (end 0x{rows[i][1]:08X}) > {rows[i+1][2]} (start 0x{rows[i+1][0]:08X})"
            )

    starts = {r[0] for r in rows}
    if raw_parsed["entry"] not in starts:
        raise RuntimeError(f"Entry point 0x{raw_parsed['entry']:08X} missing from rozu_functions.csv")

    missing_jals = [a for a in sorted(info["jals"]) if a not in starts]
    if missing_jals:
        raise RuntimeError(f"{len(missing_jals)} jal targets missing from rozu_functions.csv (first: 0x{missing_jals[0]:08X})")

    missing_vts = [a for a in sorted(info["vtable_ptrs"]) if a not in starts]
    if missing_vts:
        raise RuntimeError(f"{len(missing_vts)} vtable slot targets missing (first: 0x{missing_vts[0]:08X})")

    missing_lo = [s["addr"] for s in info["linkonce_t"] if s["addr"] not in starts]
    if missing_lo:
        raise RuntimeError(f"{len(missing_lo)} .gnu.linkonce.t.* starts missing (first: 0x{missing_lo[0]:08X})")

    text_sec = [s for s in raw_parsed["sections"] if s["name"] == ".text"][0]
    text_rows = [r for r in rows if text_sec["addr"] <= r[0] < text_sec["addr"] + text_sec["size"]]
    if not text_rows or text_rows[0][0] != text_sec["addr"] or text_rows[-1][1] != text_sec["addr"] + text_sec["size"]:
        raise RuntimeError(".text function partition does not cover full section")
    for i in range(len(text_rows) - 1):
        if text_rows[i][1] != text_rows[i + 1][0]:
            raise RuntimeError(f"Gap in .text between 0x{text_rows[i][1]:08X} and 0x{text_rows[i+1][0]:08X}")

    sym_count = symtab_secs[0]["size"] // 16 - 1
    if sym_count != len(rows):
        raise RuntimeError(f".symtab count ({sym_count}) != rozu_functions.csv count ({len(rows)})")

    print(
        f"verified output: {len(rows)} functions, {len(info['jals'])} jal targets, "
        f"{len(info['vtable_ptrs'])} vtable slots, {len(info['linkonce_t'])} linkonce_t, "
        f".vutext flags=0x{vutext_flags:X} (non-exec), 0 overlaps, 0 gaps"
    )


def main():
    ap = argparse.ArgumentParser(description="Validate Rule of Rose (SLUS-21448 v1.00) ISO and prepare build artifacts")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, help="Path to SLUS-21448_v1.00.json")
    ap.add_argument("--iso", help="Path to Rule of Rose (USA) ISO image")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "prepare"), help="Git-ignored preparation directory")
    ap.add_argument("--emit-header", help="Optional path to emit rozu_layout_generated.h")
    ap.add_argument("--emit-header-only", action="store_true", help="Emit layout header from profile without reading an ISO")
    ap.add_argument("--validate-only", action="store_true", help="Validate ISO and ELF without extracting SLUS_214.48")
    ap.add_argument("--verify-full-disc-sha256", action="store_true", help="Also verify full 3.2 GiB disc SHA-256")
    ap.add_argument("--analyzer", help="Path to ps2_analyzer executable")
    ap.add_argument("--analyzer-toml", help="Use an existing analyzed.toml instead of invoking ps2_analyzer")
    ap.add_argument("--address-map", help="Path to write symbol-only ADDRESS_MAP.generated.csv")
    ap.add_argument("--verify-output", metavar="DIR", help="Verify an existing prepared output directory and exit")
    args = ap.parse_args()

    profile = load_profile(args.profile)

    if args.verify_output:
        try:
            verify_prepare_output(args.verify_output, profile)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3
        return 0

    if args.emit_header:
        wrote = emit_layout_header(profile, args.emit_header)
        print(f"header: {args.emit_header} ({'written' if wrote else 'up to date'})")
        if args.emit_header_only:
            return 0

    if not args.iso:
        ap.error("--iso is required unless --emit-header-only or --verify-output is specified")

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

        analyzer_toml = args.analyzer_toml
        if not analyzer_toml:
            analyzer_bin = find_analyzer_binary(args.analyzer)
            analyzer_toml = run_analyzer(elf_out, args.out, analyzer_bin)
        analyzer_symbols, jump_targets = parse_analyzer_toml(analyzer_toml)
        parsed_elf = parse_elf32(elf_bytes)
        functions, disc_info = discover_functions(elf_bytes, parsed_elf, profile, analyzer_symbols, jump_targets)
        addr_map = args.address_map or os.path.join(ROOT, "Analysis", "ADDRESS_MAP.generated.csv")
        write_phase2_outputs(
            args.out, profile, elf_bytes, parsed_elf, functions, disc_info, addr_map, analyzer_toml
        )
        print(
            f"prepared artifacts: {len(functions)} functions in {os.path.join(args.out, 'rozu_functions.csv')}, "
            f"annotated ELF written, address map={addr_map}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
