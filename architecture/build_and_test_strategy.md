# Phase C — Build, Verification, and Acceptance Gate Strategy

**Date:** 2026-11-24  
**Scope:** Reproducible builds (Windows x64 target + Linux x64 local dev/test), automated verification, PCSX2 oracle methodology, and staged acceptance gates G0–G8.

---

## 1. Dual-Platform Build Strategy (Honest Platform Boundaries)

| Capability | Windows x64 (MSVC — Default Target) | Linux x64 (Ubuntu 26.04 GCC — Current Local Host) |
|---|---|---|
| `ps2_recomp`, `ps2xAnalyzer`, `vu1_recomp` | Supported (MSVC + Ninja) | **Supported locally** (GCC 15.2 + Ninja + CMake 4.2.3) |
| `ps2x_tests` & `ps2_iop_emulator_tests` | Supported | **Supported locally** via `ctest` |
| `Tools/ror_prepare.py` & `Tools/generate.py` | Supported (Python 3.10+) | **Supported locally** (Python 3.14.4) |
| `rozu` executable + `GSCpuBackend` (headless & windowed) | Supported | **Supported locally** (once Linux `#if defined(_WIN32)` guards verified in `PS2Recomp` + `Port/CMakeLists.txt`) |
| `GSGpuBackend` (OpenGL 4.6 compute + HW raster) | Supported (WGL) | **VERIFY IN M00** — if `PS2Recomp`'s `gs_gl.cpp` is WGL-only, Linux runs `PS2X_GS_GPU=0` (`GSCpuBackend`) until optional GLX/EGL support is added, and Windows runs full `GSGpuBackend`. Never silently fake GPU support. |
| `PS2X_ENABLE_FFMPEG` (`.PSS` FMV decode) | Supported (auto-fetched `n7.1-241205` prebuilt ZIP in CMake) | Requires system `libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libswresample-dev` (currently absent on host; M00/M05 documents exact `apt` check or runs initial non-FMV/stub test first). |
| Compiler FP Semantics | `/fp:precise` (NO `/fp:fast`) | `-fno-fast-math -ffp-contract=off -fno-associative-math` (strict IEEE/EE consistency) |

### Key Build Performance & Hygiene Rules
- Compile `rozu_game_code` with PCH (`ps2_runtime_macros.h`, `ps2_runtime.h`, `ps2_recompiled_functions.h`, `ps2_recompiled_stubs.h`, `ps2_syscalls.h`, `ps2_stubs.h`) and disable PCH/opt on `register_functions.cpp` to avoid giant compile-time spikes.
- Support `ROZU_GAME_CODE_LIBRARY` CMake cache variable (ported from `SOTC_GAME_CODE_LIBRARY`) so host-layer edits rebuild in seconds without recompiling ~7,500+ generated C++ files!
- Use `build/linux/` on Linux and `build/port/` on Windows (both git-ignored).

---

## 2. PCSX2 Oracle Verification Methodology

PCSX2 is used **strictly as an independent reference oracle**, NEVER linked into or launched by `rozu`.

### Matched Checkpoint Protocol
When PCSX2 + user's legally dumped PS2 BIOS are available under git-ignored `Emulator/` (`Tools/pcsx2-oracle`):
1. **CPU / RAM State Comparison:** Dump 32 MB EE RDRAM at matched deterministic milestones (e.g., `main()` entry, post-`IOPCONF.CNF` load, title screen ready, New Game scene load) using `Tools/pine.py dump` (PCSX2) vs `ROZU_DUMP_RAM_AT=<pc>:<file>` (native) and compare key game state structures (scene ID, chapter ID, player HP/coords, inventory, frame counter).
2. **IOP / SIF RPC Trace Comparison:** Compare PCSX2 EE/IOP console log (`IOPCONF.CNF` module load order, `RXSNDDRV` `Start RX - sound RPC server`, `XVAB`/`XSEQ` opens, `MCMAN`/`MCSERV` probe) against `ROZU_TRACE=BOOT,IOP,FILE,GAME` native log.
3. **GS Frame & VRAM Comparison:** Capture PCSX2 `.gs` dumps (`Tools/gsdump.py`) and replay through `gs_replay` / compare native `PS2X_GS_RECORD` screenshots and VRAM hashes (`Tools/gsr_compare.py`, `Tools/frame_report.py`) at identical deterministic pad-script fields (`PS2X_GS_GPU=0`, `PS2X_MTVU=0`).
4. **Audio Comparison:** Capture 48 kHz stereo PCM (`PS2X_AUDIO_DUMP` / `Tools/audio_check.py`) and verify non-silent peak/RMS energy, absence of clipping/underrun storms, and presence of both `.SE` SFX and `.STR` BGM/voice tracks.
5. **Save-File Interchangeability:** Save `/BASLUS-21448` in `rozu` to `memcards/Mcd001.ps2`, boot PCSX2 with a copy of `Mcd001.ps2` and verify PCSX2 loads the exact save; perform the reverse (PCSX2 save -> `rozu` load).
6. **Timing / Pacing Separation:** Always log **emulated guest game-logic updates/sec** (NTSC 60 Hz fields & internal game tick counter) SEPARATELY from **host rendered FPS**, frame-time percentiles (p50/p95/p99), shader stalls, and dropped frames.

*(While PCSX2 is not installed on the current Linux host, gates G0–G4 use deterministic native oracle invariants: exact ELF/disc hashes, unit tests, 0 decode/missing-branch faults, deterministic dual-run VRAM hash equality, non-black frame histograms, non-silent audio checks, and verified guest log milestones.)*

---

## 3. Staged Acceptance Gates (G0–G8)

Every gate requires recorded artifacts (logs, exit codes, hashes, screenshots/JSON reports) saved under git-ignored `build/test_artifacts/<gate>/` and summarized in `handoff.txt`.

| Gate | Milestone | Baseline & Exact Test Command | Hard Timeout | Pass Criteria (Measurable) | Fail / Triage Trigger |
|---|---|---|---|---|---|
| **G0** | M00–M01 | Hardened `.gitignore`, initialized `External/PS2Recomp` submodule (`d06a4ab4`), cleaned SOTC-only files. Build `ps2_recomp`, `ps2xAnalyzer`, `ps2x_tests`, `ps2_iop_emulator_tests` and run `ctest --output-on-failure`. | 15 min build; 120 s tests | `git status` shows 0 untracked proprietary files; submodule pinned; `ctest` exits `0` with 100% tests passing; 0 SOTC game targets remain in CMake. | Submodule missing/dirty, `.gitignore` gap, any `ctest` failure, or broken Linux/Windows CMake logic. |
| **G1** | M02–M03 | `python3 Tools/ror_prepare.py --profile Port/profile/SLUS-21448_v1.00.json --iso "Game/Rule of Rose (USA).iso" --out build/prepare` + wrong-ISO negative test. | 120 s | Exit `0` on valid ISO; non-zero rejection on tampered/wrong file; `rozu_functions.csv` covers all 1,449 `.gnu.linkonce.t.*`, all 4,025 `jal` targets, all 284 vtable code entries, and **0** addresses inside `.vutext` (`0x00291230..0x002953B0`); SDK stub audit verifies every stubbed `sce*` address. | Any `.vutext` word treated as EE code; missing `.gnu.linkonce.t.*` or vtable entry; unverified stub address. |
| **G2** | M04 | Minimal PoC harness: recompile a small real subset of `SLUS_214.48` functions (and then full ELF dry-run with `ps2_recomp`), compile & execute a real recompiled `SLUS_214.48` routine in `rozu_poc_test`. | 10 min | `ps2_recomp` exits `0` with **0 decode failures** and **0 unhandled instructions** across all discovered `SLUS_214.48` functions; `rozu_poc_test` exits `0` proving real recompiled MIPS instructions execute natively and return expected guest register/memory results. | Any `ps2_recomp` crash/decode error, C++ compile failure on generated code, or wrong guest result. |
| **G3** | M05 | Full `rozu` build + headless deterministic boot test: `ROZU_HEADLESS=1 PS2X_GS_GPU=0 PS2X_MTVU=0 ROZU_TRACE=BOOT,IOP,FILE,GAME ./rozu --iso "Game/Rule of Rose (USA).iso"` (stopped via watchdog/field limit). | 180 s | Disc/ELF/IRX hashes pass; `0x00100008` `crt0` -> `main()` runs; `IOPCONF.CNF` loads all 9 IOP modules (`RXSNDDRV` prints `Start RX - sound RPC server`); first `cdrom0:` reads succeed; 0 missing guest branch targets; 0 crashes; deterministic log/VSync advancement reproducible across 2 runs. | Crash, hang > 30 s with 0 VSync/PC progress, unresolved IOP import, or missing guest branch target. |
| **G4** | M06–M07 | Deterministic scripted boot through `CP_LOGO.PSS` -> Title Screen -> Main Menu navigation (`New Game` / `Load Game` / `Option`) with `PS2X_GS_RECORD` + frame captures + audio capture (`Tools/audio_check.py`). | 300 s | Non-black rendered logo/title/menu frames verified via `Tools/frame_report.py`; deterministic dual-run VRAM hash match; controller/pad input moves menu cursor and changes guest menu state; audio capture has non-zero RMS/peak without fatal SPU2 errors; `CP_LOGO.PSS` decodes or cleanly transitions without hang. | Black screen, stuck FMV, unresponsive pad, silent/crashing audio, or non-deterministic VRAM mismatch. |
| **G5** | M08 | Scripted `New Game` selection -> opening cutscene (`MV01_OPE.PSS` / real-time bus/street intro) -> first playable scene load (`DATA/CH/00/CHAP00.RPK`, `MAPUNIT.BIN`, `A*.ARA`). | 600 s | Genuine game-controlled scene transition into playable world (NOT a menu screenshot); guest scene/player pointers initialized; rendered 3D scene frames non-black and changing under movement; 0 missing branch targets. | Hang on loading screen (`LOADING.BIN`), `.PSS` deadlock, VU1/GS corruption, or crash during `i3d` world init. |
| **G6** | M09 | 10+ minutes (~36,000 NTSC fields) of actual interactive / scripted controllable gameplay (walking, running, examining objects, interacting with Brown, opening doors, entering combat/items). | 1200 s | Zero fatal faults/crashes/hangs over >= 36,000 fields; guest logic counter advances continuously; player coordinates respond to stick input; audio & rendering stay coherent; save-state round-trip (`F5`/`F9`) matches VRAM/RAM. | Any crash, freeze > 300 fields, broken collision/camera/controls, or save-state corruption. |
| **G7** | M10 | Save/load (`MCMAN`/`MCSERV` -> `/BASLUS-21448` on `Mcd001.ps2`), chapter transition (`CHAP00` -> `CHAP01`+), FMV playback, combat & streaming regression suite. | 1200 s | Fresh launch detects and loads `/BASLUS-21448` save into exact chapter/room; PCSX2 cross-load check passes when oracle available; chapter transition + `.PSS` FMV + `.STR` streaming pass with 0 faults. | Save format corruption, `MCMAN`/`MCSERV` stall, streaming desync, or chapter load crash. |
| **G8** | M11–M12 | Extended multi-chapter / full-game coverage, GPU GS + MTVU + optional VU1 AOT performance benchmarking, settings UI/INI verification, clean-clone rebuild from scratch + own ISO, Windows release packaging. | Per suite | Clean clone + ISO builds and passes G0–G7; measured hardware specs + p50/p95/p99 frametimes + guest vs host FPS logged; packaged ZIP contains zero proprietary game assets. | Any regression in G0–G7, undocumented perf claim, or leaked copyrighted file in package/git. |

---

## 4. Failure Triage Loop (Mandatory for Hydrogen)

When any gate fails:
1. Capture full stdout/stderr, exit code, and generated artifacts (`build/test_artifacts/<gate>/`).
2. Minimize to the **earliest** divergence point (e.g., first unmapped branch PC, first failing IRX import, first diverging GS command, or first stalled VSync field).
3. Classify root cause: (a) Rule of Rose function discovery/stub config (`Tools/ror_prepare.py` or `rozu.toml`), (b) host layer (`Port/src/rozu/`), or (c) generic engine bug (`External/PS2Recomp`).
4. Fix generically if (c), add a focused unit test, re-run earlier gates (regression check), update `handoff.txt`, and commit only when coherent and verified.
