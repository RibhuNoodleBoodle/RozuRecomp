# Phase A — Source-to-Destination Reuse & Adaptation Matrix

**Classification Key:**
- **(A) Reuse Unchanged** — Keep intact; zero or trivial game-agnostic tweaks only.
- **(B) Adapt Generically** — Refactor to remove `sotc` naming/hardcoded addresses and make game-agnostic or parameterized by Rule of Rose profile.
- **(C) Rewrite for Rule of Rose** — Discard SOTC implementation; write fresh Rule of Rose-specific version grounded in `SLUS_214.48` evidence.
- **(D) Remove / Do Not Use** — SOTC-only artifact; delete or leave excluded from the Rule of Rose build so SOTC assumptions never leak into `RozuRecomp`.

---

## 1. Engine & Submodule (`External/PS2Recomp/`)

| Component | Classification | Evidence / Rationale | Action for `RozuRecomp` |
|---|---|---|---|
| `External/PS2Recomp/ps2xRecomp` | **(A) Reuse Unchanged** (verify `.vutext`/`.gnu.linkonce.t.*` handling -> **(B)** if generic bug found) | Handles R5900 ISA, FPU alignment, VU0 macros, non-throwing syscalls, explicit `stubs = [...]`, `ghidra_output` CSV. | Clone/pin submodule at `d06a4ab4a6902e0ae324f184c22581c3aa387c36`. Test directly on `SLUS_214.48` in M03/M04; any parser fix must be generic. |
| `External/PS2Recomp/ps2xAnalyzer` | **(A) Reuse Unchanged** | Contains GPL-3.0 `sce_symbol_database_data.h` and `sce_symbol_scanner.cpp` to recover stripped Sony SDK symbols in `SLUS_214.48`. | Enable `PS2X_BUILD_ANALYZER ON` in root `CMakeLists.txt` (SOTC had it `OFF` because KERNEL.XFF had ABS symbols). |
| `External/PS2Recomp/ps2xRuntime` (EE kernel, DMA, VIF, GIF, VU0/VU1, GS CPU/GPU, SaveState, Input, VFS, CDImage) | **(A) Reuse Unchanged** / **(B) Adapt Generically** (Linux portability + FFmpeg MPEG/IPU validation) | Generic PS2 hardware runtime; proven on SOTC with 477 unit tests. | Reuse as-is. Enable `PS2X_ENABLE_FFMPEG ON` for Rule of Rose's 41 `.PSS` movies. Audit Linux OpenGL/WGL guards in `gs_gpu_backend` / `gs_gl.h` for local Linux testing. |
| `External/PS2Recomp/ps2xIOP` (R3000A CPU, kernel, SIO2, VirtualDualShock2, SPU2, `mcserv`, `iop_memcard`) | **(A) Reuse Unchanged** / **(B) Adapt Generically** (if `RXSNDDRV.IRX` or `MCMAN`/`MCSERV` exposes generic IOP gaps) | Runs the **exact byte-identical** Sony SDK 3.0 IRX modules (`IOPRP300.IMG`, `SIO2MAN`, `SIO2D`, `DBCMAN`, `DS1O_D`, `LIBSD`, `MCMAN`, `MCSERV`) plus generic `IopSpu2`. | Verify `RXSNDDRV.IRX` (`libsd` ordinals 4–26) and `MCMAN.IRX`+`MCSERV.IRX` loading on IOP in M05/M10. |
| `External/PS2Recomp/ps2xTest/tools/vu1_recomp.cpp` | **(A) Reuse Unchanged** | Generic VU1 microcode AOT recompiler + bit-exact interpreter verifier (`PS2X_VU1_VERIFY=1`). | Keep target `vu1_recomp`; start with VU1 interpreter in M05–M09, add AOT VU1 capture/recomp in M12 (or earlier if perf needs it). |

---

## 2. Root Build System, Config, and Scripts

| File / Path | Classification | Evidence / Rationale | Action for `RozuRecomp` |
|---|---|---|---|
| `.gitignore` | **(C) Rewrite / Harden** | Current `.gitignore` lacks `Port/generated/`, `Analysis/extracted/`, `Analysis/oracle/`, `Emulator/`, `Tools/pcsx2-oracle/`, `*.state`, `*.ps2`, `*.elf`, `game_data/`, `memcards/`, `states/`. | Harden in M00 before any build or extraction. |
| `.gitmodules` | **(B) Adapt Generically** | Points to `LightVelox/PS2Recomp.git` (`main`). | Initialize submodule properly in git index and pin exact SHA. |
| `CMakeLists.txt` | **(B) Adapt Generically** | Currently `project(SotcPC)`, `PS2X_BUILD_ANALYZER OFF`, `PS2X_ENABLE_FFMPEG OFF`. | Rename to `project(RozuRecomp)`, enable `PS2X_BUILD_ANALYZER ON`, make `PS2X_ENABLE_FFMPEG` configurable (ON when FFmpeg available), keep `PS2X_BUILD_TEST` option. |
| `Port/CMakeLists.txt` | **(B) Adapt Generically** | Hardcodes `sotc`, `sotc_game_code`, `sotc_layout_generated.h`, `assets/sotc.rc`, MSVC-only flags. | Rename targets to `rozu`, `rozu_game_code`, `rozu_vu1_code`, `rozu_layout_generated.h`; add GCC/Clang flag equivalents alongside MSVC flags so Linux headless/native dev builds work cleanly. |
| `configure.bat`, `build.bat`, `run.bat`, `setup.bat`, `package-release.bat`, `Tools/win/vsenv.cmd` | **(B) Adapt Generically** | Windows-only scripts referencing `sotc.exe`, `SCES-53326`, and MSVC `vswhere`. | Keep Windows support (`rozu.exe`, `SLUS-21448`), and add parallel POSIX/Linux scripts or CMake presets (`CMakePresets.json`) for Ubuntu local builds. |
| `LICENSE` | **(A) Reuse Unchanged** | GPL-3.0 required by PS2Recomp / sotc-vibe-pc. | Retain GPL-3.0; add clear attribution in `README.md`. |
| `README.md`, `Docs/*`, `Analysis/*` | **(D) Remove / Replace** | All SOTC-specific docs (`XFF_FORMAT.md`, `CANYON_PERFORMANCE_RESULTS.md`, `ADDRESS_MAP.csv` for SCES-53326). | Do not keep SOTC docs masquerading as Rule of Rose docs; archive or remove SOTC-only docs/analysis in M01 and maintain Rule of Rose docs under `architecture/` and `Docs/`. |

---

## 3. Native Host Layer (`Port/`)

| File / Path | Classification | Evidence / Rationale | Action for `RozuRecomp` |
|---|---|---|---|
| `Port/profile/SCES-53326_v1.00.json` | **(D) Remove** -> **(C) Rewrite** | SOTC PAL profile with XFF module bases and hashes. | Replace with `Port/profile/SLUS-21448_v1.00.json` containing verified Rule of Rose disc, `SLUS_214.48`, `SYSTEM.CNF`, `IOPCONF.CNF`, and IRX SHA-256 hashes (no XFF fields). |
| `Port/recomp/sotc.toml` | **(D) Remove** -> **(C) Rewrite** | Points to `sotc_linked.elf`, `sotc_runtime_relocs.csv`, SOTC stub list. | Replace with `Port/recomp/rozu.toml` pointing to `build/prepare/slus_21448_annotated.elf` + `rozu_functions.csv` (no `runtime_relocations`), with Rule of Rose-verified SDK `stubs = [...]`. |
| `Port/src/main.cpp` | **(B) Adapt Generically** | Clean composition root; includes SOTC hooks and Win32-only helpers. | Rewrite under `Port/src/main.cpp` for `rozu` namespace, `"Rule of Rose"` title, Linux+Windows `executableDirectory()` (`/proc/self/exe` + `GetModuleFileNameW`), removing SOTC hooks (`module_guard` XFF checks, `idle_thread`, `display_mode`, `mouse_camera`, `motion_blur`, `libgcc`). |
| `Port/src/sotc/function_hooks.{h,cpp}` | **(B) Adapt Generically** | 100% generic fast-path hook/observer table. | Move to `Port/src/rozu/function_hooks.{h,cpp}` (`namespace rozu`). |
| `Port/src/sotc/sha256.{h,cpp}` | **(A) Reuse Unchanged** (namespace rename) | Portable standalone SHA-256 implementation. | Move to `Port/src/rozu/sha256.{h,cpp}`. |
| `Port/src/sotc/log.{h,cpp}` | **(B) Adapt Generically** | Portable category logger (`SOTC_TRACE` env var). | Move to `Port/src/rozu/log.{h,cpp}` (`ROZU_TRACE`). |
| `Port/src/sotc/config.{h,cpp}` | **(B) Adapt Generically** | Clean INI parser/migrator with `SOTC_*` keys and SOTC camera/video defaults. | Move to `Port/src/rozu/config.{h,cpp}` (`rozu.ini`, `ROZU_*` + `PS2X_*` keys, NTSC default, gamepad-first defaults, no right-stick forced inversion or mouse camera). |
| `Port/src/sotc/game_disc.{h,cpp}` | **(B) Adapt Generically** | Verifies ISO9660 `SYSTEM.CNF`, boot ELF SHA-256, and disc module SHA-256s via `PS2CdImage`. | Move to `Port/src/rozu/game_disc.{h,cpp}` using `rozu_layout_generated.h` (`SLUS-21448`, `SLUS_214.48`, `IOPCONF.CNF`, `MODULES/*.IRX`). |
| `Port/src/sotc/module_guard.{h,cpp}` | **(B) Split & Adapt** / **(D) Drop XFF guard** | XFF `verifyModule()` and SOTC thread-trace addresses (`0x001066E0` etc.) are SOTC-only; `applyEeFloatingPointMode()`, `RAM dump`, `mem trace`, `call trace` are generic. | Drop XFF `verifyModule()`. Move generic EE FPU setup + env-driven call/mem/RAM-dump diagnostics to `Port/src/rozu/diagnostics.{h,cpp}`. |
| `Port/src/sotc/watchdog.{h,cpp}` | **(B) Adapt Generically** | Generic watchdog/timeline/poke; remove SOTC hardcoded `0x1C3070u` hook (line 619); keep Win32 stackwalk guarded by `#if defined(_WIN32)`. | Move to `Port/src/rozu/watchdog.{h,cpp}`; parameterize present-hook address via env var `ROZU_TIMELINE_HOOK`. |
| `Port/src/sotc/debug_script.{h,cpp}` | **(B) Adapt Generically** | Generic frame-triggered call/peek/poke/save/load script engine; only `kDefaultHook = 0x001C35B0u` is SOTC-specific. | Move to `Port/src/rozu/debug_script.{h,cpp}`; require explicit `ROZU_DEBUG_HOOK` until a verified Rule of Rose per-frame hook address is measured. |
| `Port/src/sotc/hle/sce_cdvd.{h,cpp}` | **(C) Rewrite for Rule of Rose** | Timing model pattern is great, but hardcoded addresses (`0x001DB688` etc.) are SOTC-only. | Bind via `rozu.toml` stubs first (using `ps2_stubs::sceCd*`); only add timed HLE wrappers by verified `SLUS_214.48` symbol address if Rule of Rose exhibits race conditions under instant disc reads. |
| `Port/src/sotc/hle/sce_fileio.{h,cpp}` | **(C) Rewrite for Rule of Rose** | Hardcoded SOTC addresses + PAL 50 Hz field timing. | Start with `ps2_runtime` built-in `fio`/`sceOpen`/`sceRead`/`sceWrite` stubs + TTY stdout hook; add timed wrappers only if measured timing requires them (at 60 Hz NTSC). |
| `Port/src/sotc/hle/libgcc.{h,cpp}` | **(D) Remove** | Hardcoded SOTC `__floatdisf` (`0x00121D00u`) performance optimization. | Remove; let recompiled `SLUS_214.48` libgcc run natively first. |
| `Port/src/sotc/idle_thread.{h,cpp}` | **(D) Remove** | Hardcoded SOTC `iosRecvMsg` (`0x001ABED0u`, `$ra=0x001A808Cu`). | Remove; revisit only in M12 if profiling proves an EE busy-wait idle loop in Rule of Rose. |
| `Port/src/sotc/display_mode.{h,cpp}` | **(D) Remove** (keep 20-line `configureHostDisplay()`) | Hardcoded SOTC PAL/NTSC menu skip and 15 SOTC widescreen addresses. | Extract portable `configureHostDisplay()` into `rozu/display.cpp`; discard all SOTC widescreen/menu hooks. |
| `Port/src/sotc/mouse_camera.{h,cpp}` & `mouse_camera_math.h` | **(D) Remove** | Hardcoded SOTC free-camera struct offsets. Rule of Rose uses fixed/cinematic camera angles. | Remove completely. |
| `Port/src/sotc/motion_blur.{h,cpp}` | **(D) Remove** | Hardcoded SOTC `screenBlur` (`0x0117FDF8u`). | Remove completely. |
| `Port/src/sotc/window_icon.{h,cpp}`, `Port/assets/sotc.rc` | **(D) Remove** | SOTC icon/resource file. | Remove SOTC resource; add neutral `rozu` icon only in M12 packaging. |
| `Port/tools/vu1_bench.cpp` | **(B) Adapt Generically** | Generic VU1 trace replay/verifier; minor Win32 timing helpers. | Retain for optional M12 VU1 AOT benchmarking. |

---

## 4. Python Tooling & Test Harnesses (`Tools/`)

| Tool(s) | Classification | Evidence / Rationale | Action for `RozuRecomp` |
|---|---|---|---|
| `Tools/iso9660.py` | **(A) Reuse Unchanged** | Verified working on `Game/Rule of Rose (USA).iso`. | Reuse unchanged. |
| `Tools/pine.py`, `Tools/irx_imports.py`, `Tools/gs_vram.py`, `Tools/gsdump.py`, `Tools/gsr_compare.py`, `Tools/gstrace_summary.py`, `Tools/state_ram_extract.py`, `Tools/find_walk_delta.py`, `Tools/pystrings.py`, `Tools/vu0_corpus.py`, `Tools/audio_check.py`, `Tools/frame_report.py` | **(A) Reuse Unchanged** (or trivial CLI path updates) | Game-agnostic PS2/PCSX2/GS/IRX/audio/state diagnostic scripts. | Retain as shared PS2 diagnostic utilities. |
| `Tools/disasm.py` | **(B) Adapt Generically** | Disassembles linked ELF using address map; currently defaults to SOTC paths. | Point default paths to `build/prepare/slus_21448_annotated.elf` and `Analysis/ADDRESS_MAP.generated.csv`. |
| `Tools/generate.py` & `Tools/generate.bat` | **(C) Rewrite for Rule of Rose** | Orchestrates `sotc_link.py`, `sotc.toml`, `verify_reloc_sites.py`, `vu1_recomp` on Windows. | Replace with cross-platform `Tools/generate.py` calling `Tools/ror_prepare.py` + `ps2xAnalyzer` + `ps2_recomp` (no XFF linker, no reloc verifier, optional VU1 recomp). |
| `Tools/sotc_link.py`, `Tools/xff.py`, `Tools/verify_reloc_sites.py` | **(D) Remove** -> **(C) Replace with `Tools/ror_prepare.py`** | XFF2 dynamic module linker + runtime relocation verifier; Rule of Rose has no XFF modules or dynamic code relocations. | Replace with `Tools/ror_prepare.py`: ISO validator, `SLUS_214.48` extractor (to git-ignored `build/prepare/`), `.gnu.linkonce.t.*` + vtable + `jal` + `ps2xAnalyzer` function discovery, `.vutext` exclusion, annotated ELF/CSV/header emitter. |
| `Tools/scenario.py`, `Tools/golden_run.py`, `Tools/boot_milestones.py`, `Tools/boot_phases.py`, `Tools/measure_boot.py`, `Tools/compare_ram.py`, `Tools/state_check.py`, `Tools/performance_*.py`, `Tools/private_state_launch.ps1`, `Tools/package_release.cmake`, `Tools/release/*` | **(D) Remove SOTC scripts** -> **(C) Rewrite progressively (M05–M12)** | Hardcoded SOTC colossi warps, RAM addresses (`0x1DC9EC`, `0x1DC7AC`), `sotc.exe`, and `SCES-53326`. | Remove SOTC-specific harnesses in M01 so nothing can accidentally claim pass on stale SOTC checks; create Rule of Rose boot/menu/gameplay/save harnesses in M05–M12 once real addresses are verified. |
