# Phase C — Milestone Plan & Readiness Map (`M00`–`M12`)

**Date:** 2026-11-24  
**Readiness Legend:**
- **READY** — Fully grounded in verified local repo, toolchain, and `SLUS_214.48` binary evidence; immediately executable by Gemini Hydrogen once prerequisite commit lands.
- **CONDITIONAL** — Architecture and acceptance gate are defined, but exact addresses, hooks, or runtime fixes depend on runtime execution logs/traces from earlier milestones (`M05`+). Hydrogen MUST inspect runtime evidence from prior steps before editing code; never guess offsets.

---

## Milestone Roadmap

| Milestone | Step File(s) | Readiness | Gate | Core Objective | Hard Prerequisite |
|---|---|---|---|---|---|
| **M00** | `Gemini_Step_001.txt` | **READY** | G0 (part 1) | Protect repository (`.gitignore` hardening), create dedicated feature branch `rozu/port-bringup`, initialize & pin `External/PS2Recomp` submodule (`d06a4ab4`), audit Linux/Windows CMake buildability, build & test `ps2_recomp`, `ps2xAnalyzer`, `ps2x_tests`, `ps2_iop_emulator_tests`. | Clean awareness of user's untracked starting files; `git status` check. |
| **M01** | `Gemini_Step_002.txt` | **READY** | G0 (part 2) | Audit & strip SOTC-only targets/hooks/scripts/docs from active build (`CMakeLists.txt`, `Port/`, `Tools/`), establish clean `RozuRecomp` skeleton (`Port/src/rozu/` generic utilities: `log`, `sha256`, `config`, `function_hooks`, `diagnostics`, `watchdog`, `debug_script`, `display`), keep `External/PS2Recomp` cleanly isolated, verify `ctest` still passes 100%. | M00 commit + passing `ctest`. |
| **M02** | `Gemini_Step_003.txt` | **READY** | G1 (part 1) | Create `Port/profile/SLUS-21448_v1.00.json` with all verified hashes, implement `Tools/ror_prepare.py` Phase 1 (ISO9660 validator + negative tests + `rozu_layout_generated.h` emitter) and `Port/src/rozu/game_disc.{h,cpp}` with unit/CLI verification against `Game/Rule of Rose (USA).iso`. | M01 commit. |
| **M03** | `Gemini_Step_004.txt` | **READY** | G1 (part 2) | Extend `Tools/ror_prepare.py` with full `SLUS_214.48` function discovery (`.text` + 1,449 `.gnu.linkonce.t.*` + 284 `.gnu.linkonce.d.*` vtables + 4,025 `jal` + `j` tail + pointer tables, **strictly excluding `.vutext` `0x00291230..0x002953B0`**), integrate `ps2xAnalyzer` GPL SCE SDK symbol scanner, verify every SCE stub address, emit `slus_21448_annotated.elf`, `rozu_functions.csv`, `Analysis/ADDRESS_MAP.generated.csv`, and `Port/recomp/rozu.toml`. | M02 commit + working `ps2xAnalyzer`. |
| **M04** | `Gemini_Step_005.txt` | **READY** | **G2** | **Hard Feasibility PoC:** Implement `Tools/generate.py`, run `ps2_recomp` on a small real subset of `SLUS_214.48` first, compile & run `rozu_poc_test` proving real statically recompiled Rule of Rose EE instructions execute natively with verified results; then run full `SLUS_214.48` `ps2_recomp` pass confirming **0 decode failures** and **0 unhandled instructions** and compile `rozu_game_code`. | M03 commit + verified `rozu.toml` & `rozu_functions.csv`. |
| **M05** | `Gemini_Step_006.txt` | **READY** (runtime triage conditional on logs) | **G3** | Wire `Port/src/main.cpp` + `rozu` executable linking full `rozu_game_code` + `ps2_runtime` + `ps2xIOP`; boot `0x00100008` in deterministic CPU-GS headless mode; resolve any missing function entries, SDK stubs, or `IOPCONF.CNF` (`MCMAN`/`MCSERV`/`RXSNDDRV`) boot blockers; verify reproducible boot traces. | M04 commit (G2 PASS). |
| **M06** | `Gemini_Step_007.txt` | **CONDITIONAL** (depends on M05 boot traces & FFmpeg availability) | **G4** (part 1) | Boot to first reliably verified video/audio/initial screen: validate `CP_LOGO.PSS` playback (`PS2X_ENABLE_FFMPEG` / `Stubs/MPEG.cpp` / `IPU.cpp`), CRTC presentation, first non-black GS frames, and `RXSNDDRV.IRX` audio output. | M05 commit (G3 PASS). |
| **M07** | `Gemini_Step_008.txt` | **CONDITIONAL** (depends on M06 menu reachability & audio trace) | **G4** (part 2) | Title screen & main menu navigation: verify `DS1O_D`/`libpad2` controller & keyboard bindings, menu cursor/selection responsiveness, `RXSNDDRV.IRX` SFX + BGM (implement generic `IopSpu2` AutoDMA PCM if trace proves `sceSdBlockTrans` usage), deterministic dual-run VRAM hash check. | M06 commit. |
| **M08** | `Gemini_Step_009.txt` | **CONDITIONAL** (depends on M07 title screen & FMV/loading logs) | **G5** | Select New Game, advance through opening FMV/cutscene (`MV01_OPE.PSS`) and loading (`LOADING.BIN`, `CHAP00.RPK`, `MAPUNIT.BIN`, `A*.ARA`), verify `i3d` 3D world/VU1/GS initialization into real game-controlled scene. | M07 commit (G4 PASS). |
| **M09** | `Gemini_Step_010.txt` | **CONDITIONAL** (depends on M08 gameplay addresses & scene stability) | **G6** | First 10+ minutes (~36,000 NTSC fields) of genuine controllable gameplay: movement, Brown interactions, doors/area transitions, item/inventory UI, camera cuts, save-state (`F5`/`F9`) round-trip check, zero fatal faults. | M08 commit (G5 PASS). |
| **M10** | `Gemini_Step_011.txt` | **CONDITIONAL** (depends on M09 stability & `MCMAN`/`MCSERV` traces) | **G7** | Memory card save/load (`/BASLUS-21448` on `Mcd001.ps2`, PCSX2 cross-check if oracle available), chapter transition (`CHAP00` -> `CHAP01`+), combat, FMV & `.STR` audio streaming automated regression suite. | M09 commit (G6 PASS). |
| **M11** | `Gemini_Step_012.txt` | **CONDITIONAL** (depends on M10 regression suite) | **G8** (part 1) | Extended multi-chapter / full-game playthrough coverage, automated chapter scenario harness (`Tools/rozu_scenario.py`), fix remaining VU/GS/SPU2/MPEG edge cases generically. | M10 commit (G7 PASS). |
| **M12** | `Gemini_Step_013.txt` | **CONDITIONAL** (depends on M11 fidelity baseline) | **G8** (part 2) | Performance profiling & optimization (`GSGpuBackend`, `MTVU`, optional `vu1_recomp` AOT for `.vutext` microprograms), user settings (`rozu.ini`), Windows x64 + Linux CI/packaging, clean-clone + ISO rebuild verification, final documentation & release hygiene audit. | M11 commit. |

---

## Critical Dependency Chain

```text
M00 (Repo safety + PS2Recomp submodule + toolchain)
 └─► M01 (Clean RozuRecomp skeleton, strip SOTC assumptions)
      └─► M02 (SLUS-21448 ISO validator + profile + game_disc)
           └─► M03 (SLUS_214.48 function discovery + .vutext exclusion + ps2xAnalyzer SDK stubs)
                └─► M04 [G2] (Small PoC + full ps2_recomp dry-run & compile)
                     └─► M05 [G3] (EE boot + IOPCONF.CNF + first cdrom0: reads)
                          └─► M06 [G4a] (CP_LOGO.PSS FMV + first verified video/audio)
                               └─► M07 [G4b] (Title/Menu + pad + RXSNDDRV audio)
                                    └─► M08 [G5] (New Game + intro cutscene + world init)
                                         └─► M09 [G6] (10+ min interactive gameplay + savestate)
                                              └─► M10 [G7] (MCMAN/MCSERV saves + chapters + combat/FMV)
                                                   └─► M11 [G8a] (Extended/full-game coverage)
                                                        └─► M12 [G8b] (Perf/VU1 AOT/packaging/clean-clone)
```
