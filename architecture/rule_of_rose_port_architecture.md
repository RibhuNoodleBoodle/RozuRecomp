# Phase C — Rule of Rose Native PC Port Architecture (`RozuRecomp`)

**Target Game:** Rule of Rose — PlayStation 2, NTSC-U, `SLUS-21448` v1.00  
**Base Engine:** `External/PS2Recomp` (pinned submodule of `LightVelox/PS2Recomp`, GPL-3.0)  
**Default Deployment Target:** Native Windows x64 (MSVC); **Dev/CI Secondary Target:** Native Linux x64 (GCC/Ninja, headless + CPU GS + portable runtime)

---

## 1. Guiding Architectural Principles

1. **Genuine Static Recompilation:** All EE R5900 game code from `SLUS_214.48` (`.text` + 1,449 `.gnu.linkonce.t.*` sections, excluding `.vutext`) is statically recompiled ahead of time to C++ by `ps2_recomp` and linked into `rozu` / `rozu.exe`. There is NO EE interpreter and NO PCSX2 dependency at runtime.
2. **Zero SOTC Leakage:** Every target name, namespace (`rozu::`), config file (`rozu.ini`), env prefix (`ROZU_*` + generic `PS2X_*`), profile (`SLUS-21448_v1.00.json`), and TOML (`rozu.toml`) belongs exclusively to Rule of Rose. All SOTC XFF/colossus/camera/widescreen/address assumptions are removed.
3. **Clean-Clone Reproducibility:** A fresh `git clone --recursive` plus the user's own verified `SLUS-21448` ISO regenerates `Port/generated/` and builds a working executable. Zero proprietary assets, disc binaries, BIOS files, or generated game C++ files are ever committed.
4. **Game-Agnostic Engine Submodule:** All generic fixes to EE/VU/GS/IOP/MPEG/IPU/recompiler live in `External/PS2Recomp` on a clearly tracked fork branch (e.g., `rozu-port` branched from `d06a4ab4a6902e0ae324f184c22581c3aa387c36`), tested with `ps2x_tests` and `ps2_iop_emulator_tests`, and explicitly pinned by commit SHA in the parent repo.
5. **Fidelity Before Optimization:** Bring-up runs with deterministic serial CPU GS (`PS2X_GS_GPU=0`), synchronous VU1 interpreter (`PS2X_MTVU=0`, `PS2X_VU1_RECOMP=0`), and authentic NTSC 60 Hz pacing before enabling GPU GS, MTVU, or VU1 AOT recompilation.

---

## 2. Target Repository Layout

```text
RozuRecomp/
├── CMakeLists.txt                       # Root CMake project(RozuRecomp): PS2Recomp + Port
├── CMakePresets.json                    # Cross-platform presets (win-msvc-relwithdebinfo, linux-gcc-relwithdebinfo)
├── .gitignore                           # Hardened legal/generated/build/oracle exclusions
├── .gitmodules                          # Pinned External/PS2Recomp submodule
├── handoff.txt                          # Mandatory persistent continuity ledger
├── architecture/                        # Neon research, audit, architecture, decisions, milestones
├── gemini_hydrogen/                     # Executable step-by-step Hydrogen prompts + STEP_INDEX.txt
├── Game/
│   └── PLACE-YOUR-ISO-HERE.txt          # User places Rule of Rose (USA).iso here (git-ignored)
├── External/
│   └── PS2Recomp/                       # Submodule: ps2xRecomp, ps2xAnalyzer, ps2xIOP, ps2xRuntime, ps2xTest
├── Port/
│   ├── CMakeLists.txt                   # Targets: rozu_game_code, rozu_vu1_code (opt), rozu, rozu_smoke_test
│   ├── profile/
│   │   └── SLUS-21448_v1.00.json        # Verified disc/ELF/CNF/IRX SHA-256 profile
│   ├── recomp/
│   │   └── rozu.toml                    # PS2Recomp config (auto_stub_by_name=false, explicit verified stubs)
│   ├── generated/                       # GIT-IGNORED: ps2_recomp C++ output + rozu_layout_generated.h
│   └── src/
│       ├── main.cpp                     # Composition root (CLI, config, disc verify, runtime init, hooks)
│       └── rozu/
│           ├── config.{h,cpp}           # rozu.ini loader (ROZU_* + PS2X_* keys, gamepad-first NTSC defaults)
│           ├── log.{h,cpp}              # Category logger (ROZU_TRACE)
│           ├── sha256.{h,cpp}           # Standalone SHA-256 verifier
│           ├── game_disc.{h,cpp}        # ISO9660 mount + SLUS-21448/SLUS_214.48/IOPCONF/IRX hash check
│           ├── function_hooks.{h,cpp}   # Lock-free fast-path observe/replace/HLE registry
│           ├── diagnostics.{h,cpp}      # EE FPU mode (RTZ+FTZ+DAZ), call/mem/RAM-dump observers
│           ├── display.{h,cpp}          # Host VSync / FPS limit / headless mode config
│           ├── watchdog.{h,cpp}         # Hang detector, timeline logger, pokes (Win32 stackwalk guarded)
│           ├── debug_script.{h,cpp}     # Field-triggered call/peek/poke/save/load automation
│           └── hle/
│               ├── tty_bridge.{h,cpp}   # Guest stdout/stderr (fd 1/2) -> [GAME] log
│               └── disc_timing.{h,cpp}  # Optional cycle-accurate DVD timing wrappers (only if needed)
├── Tools/
│   ├── iso9660.py                       # Pure-Python ISO9660 reader (reused unchanged)
│   ├── ror_prepare.py                   # Rule of Rose ISO validator, ELF analyzer glue, function map, header gen
│   ├── generate.py                      # Cross-platform codegen orchestrator (prepare -> ps2_recomp -> sync)
│   ├── disasm.py                        # Disassemble annotated ELF by symbol/address
│   ├── irx_imports.py                   # IRX import inspector (reused unchanged)
│   ├── pine.py                          # PCSX2 PINE IPC oracle client (reused unchanged)
│   ├── gs_vram.py, gsdump.py, gsr_compare.py, gstrace_summary.py  # GS diagnostics (reused)
│   ├── state_ram_extract.py, audio_check.py, frame_report.py, vu0_corpus.py
│   └── win/vsenv.cmd                    # Windows MSVC environment helper
└── Analysis/                            # Generated ADDRESS_MAP.generated.csv (only symbol metadata, NO game bytes)
```

---

## 3. Pipeline & Runtime Architecture

### 3.1 Static Recompilation Build Pipeline (No XFF Linker Needed)

```text
User's Verified SLUS-21448 ISO
        │
        ▼
Tools/ror_prepare.py  (verifies ISO size + SYSTEM.CNF + SLUS_214.48 & IRX SHA-256s)
        │  1. Extracts SLUS_214.48 to git-ignored build/prepare/SLUS_214.48
        │  2. Runs External/PS2Recomp's ps2xAnalyzer (GPL SCE SDK signature scanner)
        │  3. Discovers ALL EE function starts in .text + 1,449 .gnu.linkonce.t.*:
        │       - ELF entry (0x00100008)
        │       - All 1,449 .gnu.linkonce.t.* exact mangled names & sizes
        │       - All 284 .gnu.linkonce.d.* C++ vtable function pointers
        │       - All 4,025 direct jal targets & cross-function j tail targets
        │       - Verified SCE SDK symbols from ps2xAnalyzer
        │       - .data / .rodata function-pointer tables & lui/addiu targets (excluding switch tables)
        │       - STRICT EXCLUSION of .vutext (0x00291230..0x002953B0)
        │  4. Emits:
        │       - build/prepare/slus_21448_annotated.elf  (SLUS_214.48 + synthetic .symtab/.strtab, .vutext non-exec)
        │       - build/prepare/rozu_functions.csv        (function boundaries & names)
        │       - build/prepare/rozu_address_map.csv      (provenance & confidence per function)
        │       - Port/generated/rozu_layout_generated.h  (verified hashes, entry, code bounds)
        ▼
ps2_recomp + Port/recomp/rozu.toml
        │  - auto_stub_by_name = false, direct_tail_calls = false
        │  - explicit verified stubs = [SIF/RPC, CDVD, FIO, TTY, MPEG/IPU]
        │  - emits Port/generated/*.cpp, ps2_recompiled_functions.h, register_functions.cpp
        ▼
CMake + Ninja (Windows MSVC or Linux GCC)
        │  - builds rozu_game_code (PCH + /fp:precise or -fno-fast-math -ffp-contract=off)
        │  - links ps2_runtime + ps2xIOP + raylib + FFmpeg (when enabled)
        ▼
build/<preset>/bin/rozu(.exe)  ──runtime──►  mounts Game/Rule of Rose (USA).iso via PS2CdImage
```

### 3.2 Explicit Module Boundaries

| Subsystem | Owner | Interface / Boundary |
|---|---|---|
| **ISO Mount & Verification** | `Port/src/rozu/game_disc.cpp` + `PS2CdImage` | Verifies size, `SYSTEM.CNF`, `SLUS_214.48`, `IOPCONF.CNF`, `SYSTEM.INI`, and `/MODULES/*.IRX` SHA-256s on every launch before executing guest code. Caches verified `SLUS_214.48` into git-ignored `game_data/`. |
| **EE Execution & Dispatch** | `Port/generated/*.cpp` + `PS2Runtime` (`g_ps2RecompiledFunctionTable`) | All `jal`, `jalr`, and inter-function `j` (`direct_tail_calls = false`) route through runtime function table. `rozu::FunctionHooks` observes/replaces slots cleanly with startup audit log. |
| **EE Kernel, Timers, Interrupts, DMA, VIF, GIF** | `External/PS2Recomp/ps2xRuntime` | Syscalls via non-throwing `handleSyscall`, lazy EE timers, INTC 0 (GS FINISH/VSINT), DMA chains up to `2^20` tags, NTSC 60 Hz VSync. |
| **VU0 / VU1** | `ps2xRuntime` VU0 macros + VU1 interpreter (Phase 1) / optional `vu1_recomp` AOT (Phase 2) | `.vutext` (`0x00291230..0x002953B0`, 44 `MPG` packets) uploads naturally through guest VIF1 DMA chains to VU1 micro-memory. Start with deterministic interpreter; capture & AOT-compile only after gameplay stability is verified. |
| **GS Graphics** | `ps2xRuntime` `GSCpuBackend` (reference/bring-up) & `GSGpuBackend` (OpenGL 4.6) | Exact CRTC presentation (`PMODE`/`DISPFB`/`DISPLAY`/`SMODE2`). Bring-up defaults to `GSCpuBackend` for bit-exact validation; `GSGpuBackend` enabled on Windows OpenGL 4.6 (and Linux if GL context layer is ported). |
| **IOP & IRX Execution** | `External/PS2Recomp/ps2xIOP` | Runs `IOPRP300.IMG`, `SIO2MAN`, `SIO2D`, `DBCMAN`, `DS1O_D`, `MCMAN`, `MCSERV`, `LIBSD`, and `RXSNDDRV.IRX` directly on emulated R3000A. |
| **Disc File I/O & Streaming** | `PS2CdImage` + `ps2_stubs` (`sceCd*`, `fio*`) + optional `rozu/hle/disc_timing.cpp` | Serves `cdrom0:` raw sector reads (`MAPUNIT.BIN`, `*.RPK`, `*.ARA`, `*.STR`, `*.PSS`) directly from mounted ISO with zero pre-extraction. |
| **Gamepad & Rumble** | `ps2_host_input` -> `IopHost::readPad` -> `SIO2` -> `VirtualDualShock2` -> `DS1O_D` -> `libpad2`/`libvib` | Controller-first mapping via raylib gamepad 0 + sensible keyboard defaults (no SOTC mouse camera, no forced right-stick inversion). |
| **Memory Card** | `MCMAN.IRX` + `MCSERV.IRX` -> `SIO2` -> `iop_memcard` (`memcards/Mcd001.ps2`) | PCSX2-compatible 8 MB raw card image storing `/BASLUS-21448/*`. |
| **Audio (SPU2)** | `RXSNDDRV.IRX` -> `LIBSD.IRX` -> `IopSpu2` -> 48 kHz host stream | ADPCM voice decoding already works; if `RXSNDDRV.IRX` uses AutoDMA (`sceSdBlockTrans`) for `.STR`/`.PSS` audio, implement generic AutoDMA ring in `ps2xIOP/iop_spu2.cpp`. |
| **FMV Movies (41 `.PSS`)** | `ps2xRuntime` `Stubs/MPEG.cpp` + `Stubs/IPU.cpp` (`PS2X_ENABLE_FFMPEG=ON`) | Real FFmpeg-backed MPEG-2 decode + audio demux for `CP_LOGO.PSS`, `MV*_TIT.PSS`, `MV*_OPE.PSS`, and all story movies. |
| **Diagnostics & Oracle** | `rozu/diagnostics.cpp`, `rozu/watchdog.cpp`, `rozu/debug_script.cpp`, `Tools/pine.py`, `Tools/gsr_compare.py` | Env-driven traces (`ROZU_TRACE`), RAM dumps (`ROZU_DUMP_RAM_AT`), GS recordings (`PS2X_GS_RECORD`), deterministic pad scripts, and PCSX2 PINE comparisons. |

---

## 4. Explicit Error-Handling Architecture

| Failure Mode | Detection Mechanism | Mandatory Runtime / Tool Behavior |
|---|---|---|
| **Wrong disc / region / bad dump** | `ror_prepare.py` & `rozu::verifyDiscAndPrepare()` verify ISO size (`3,393,454,080` B), `SYSTEM.CNF` (`SLUS_214.48`), and SHA-256 of `SLUS_214.48` + `IOPCONF.CNF` + IRXs. | Abort immediately with exit code `3` and print exact expected vs actual SHA-256 and required build (`SLUS-21448 v1.00`). Never execute unverified code. |
| **Missing prerequisites** (empty submodule, missing `ps2_recomp`, missing FFmpeg when requested, missing ISO) | CMake configure checks + `Tools/generate.py` preflight checks. | Fail fast with actionable command telling the user exactly what is missing. |
| **Failed / partial regeneration** | `Tools/generate.py` writes into `build/generated_staging/` and only syncs into `Port/generated/` on exit code `0` with non-empty `register_functions.cpp` and 0 decode errors. | Never leave half-written files in `Port/generated/`. |
| **Unknown guest branch target (`jalr`/`jr`/tail `j`)** | `runtime.setMissingFunctionPolicy(PS2Runtime::MissingFunctionPolicy::Stop)` (default ON). | Halt immediately, log exact guest `pc`, caller `$ra`, registers, and nearest discovered symbol so `ror_prepare.py` can be updated cleanly. |
| **Unresolved IOP IRX import** | `ps2xIOP` module loader checks all import library versions/ordinals at `sceSifLoadModule`. | Log exact module name, library name, version, and missing ordinal; fail loudly rather than silently jumping to 0. |
| **Unexpected ELF relocations** | `ror_prepare.py` asserts `e_type == ET_EXEC` and zero `SHT_REL`/`SHT_RELA` sections in `SLUS_214.48`. | Abort preparation if a modified/unsupported ELF with unexpected relocations is supplied. |
| **Runtime divergence / hang / black screen** | `rozu::watchdog` checks VSync & guest frame counter advancement; `Tools/rozu_boot_check.py` enforces hard timeouts and non-black frame/VRAM hash thresholds. | Dump thread states + stack trace + last log lines and return non-zero exit code. |

---

## 5. Submodule Governance & Patch Provenance (`External/PS2Recomp`)

1. **Pinning:** `External/PS2Recomp` is registered in `.gitmodules` and pinned in the parent repository's git tree to an explicit commit SHA (initial pin: `d06a4ab4a6902e0ae324f184c22581c3aa387c36` from `LightVelox/PS2Recomp` `main`).
2. **Modifications Policy:**
   - Do **not** make casual ad-hoc edits inside `External/PS2Recomp`.
   - When a generic engine fix is required (e.g., Linux build guard, `IopSpu2` AutoDMA PCM, `MPEG`/`IPU` bug, `ElfParser` `.vutext`/`.gnu.linkonce` handling), commit it inside `External/PS2Recomp` on a named branch `rozu-port` with a unit test in `ps2xTest` or `ps2xIOP/tests`, record the submodule commit SHA and rationale in `handoff.txt` and `architecture/decisions.md`, and update the parent repo's submodule pointer in a clean parent commit.
   - Never put Rule of Rose addresses, disc IDs, or game-specific hacks inside `External/PS2Recomp`.
3. **Cross-Compatibility Check:** Because engine changes stay game-agnostic and pass `ps2x_tests` + `ps2_iop_emulator_tests`, they remain upstreamable to `LightVelox/PS2Recomp` / `ran-j/PS2Recomp` and compatible with `sotc-vibe-pc`.
