# Phase A — Base Repository & Engine Audit (`LightVelox/sotc-vibe-pc` + `LightVelox/PS2Recomp`)

**Audit Date:** 2026-11-24  
**Auditor:** Google Neon (High)  
**Target Destination:** Rule of Rose (PS2, NTSC-U `SLUS-21448` v1.00) Native PC Static Recompilation (`RozuRecomp`)

---

## 1. Provenance, Git State, Licenses, and Toolchain Baseline

### 1.1 Repository & Submodule Provenance (VERIFIED)

| Item | Verified Value | Status |
|---|---|---|
| Local workspace path | `/mnt/6421-8598/building/RozuRecomp` | VERIFIED |
| Local `origin` remote | `https://github.com/RibhuNoodleBoodle/RozuRecomp` | VERIFIED |
| Local branch / HEAD | `main` (`019f6deab05a8d3a11763f60e61355f53883583d`, `2026-11-24 00:54:17 +0530`, `"restarting everythang"`) | VERIFIED |
| Tracked files in HEAD | Only `.gitignore` (`git ls-tree -r --name-only HEAD`) | VERIFIED |
| Working tree state | DIRTY — entire `sotc-vibe-pc` file tree is currently untracked (`??`), plus `Game/Rule of Rose (USA).iso` (ignored) and `Google_Neon_Rule_of_Rose_Recomp_Architect.txt` (untracked) | VERIFIED |
| Upstream base repo | `https://github.com/LightVelox/sotc-vibe-pc` (`main` = `1ce4a5ea4955878bd2edabdc4e1a6b6f49a8e1ad` via `git ls-remote` on 2026-11-24) | VERIFIED |
| Submodule URL (`.gitmodules`) | `External/PS2Recomp` -> `https://github.com/LightVelox/PS2Recomp.git` (`branch = main`) | VERIFIED |
| Submodule local state | `External/PS2Recomp/` is currently an **EMPTY DIRECTORY** (not initialized/cloned) | VERIFIED |
| `LightVelox/PS2Recomp` remote HEAD | `main` = `d06a4ab4a6902e0ae324f184c22581c3aa387c36` (via `git ls-remote` on 2026-11-24) | VERIFIED |
| Upstream `ran-j/PS2Recomp` remote HEAD | `main` = `e5636981a1c9de368f6b71e819c3dc188dfedbf4` (via `git ls-remote` on 2026-11-24) | VERIFIED |
| Reference decomp repo | `https://github.com/notmanrivera/ruleofrose-decomp` (`main` = `b7871f7bab460635325d634e8c09c6f66d242c14`) | VERIFIED |

### 1.2 License Audit (VERIFIED)

| Component | License | Implication |
|---|---|---|
| `LightVelox/sotc-vibe-pc` (`LICENSE`, `README.md:176-177`) | **GPL-3.0** | Reusable under GPL-3.0 with copyright/attribution preserved. Covers code only, grants no rights to game assets. |
| `LightVelox/PS2Recomp` (`LICENSE`) | **GPL-3.0** (matching `ran-j/PS2Recomp`) | Reusable under GPL-3.0. Includes `ps2xAnalyzer/include/ps2recomp/sce_symbol_database_data.h` under GPL-3.0. |
| `notmanrivera/ruleofrose-decomp` | **NO LICENSE FILE** (verified 404 on `/LICENSE`) | **All Rights Reserved by default.** DO NOT copy source code, scripts, or symbol tables from `ruleofrose-decomp` into this repository. Use only for independent conceptual sanity-checking (e.g., expected compiler flags and rough function count). |
| Third-party libs pulled by `PS2Recomp` (`README.md:184-185`) | raylib (zlib/libpng), ELFIO (MIT), rabbitizer (MIT), fmt (MIT), toml11 (MIT), FFmpeg (LGPL when enabled) | Compatible with GPL-3.0 distribution. |

### 1.3 Local Host vs Default Target Toolchain (VERIFIED)

- **Default deployment target:** Native Windows x64 (matching `sotc-vibe-pc` MSVC/Win32 build).
- **Actual local host inspected:**
  - OS: Ubuntu 26.04.1 LTS (`Resolute Raccoon`), Linux `7.3.5-070305-generic x86_64`.
  - Installed native Linux tools: `cmake 4.2.3`, `ninja 1.13.2`, `g++ 15.2.0`, `python3 3.14.4` (`PIL` installed; `capstone`, `elftools`, `numpy`, `pycdlib`, `tomli` missing), `readelf`, `objdump`, `7z`, `isoinfo`, `wine 10.0`.
  - Installed Linux dev headers: `libsdl2-dev 2.32.10`, `libopengl-dev 1.7.0`, `libegl1-mesa-dev`, `libgles2-mesa-dev`, `libglm-dev`, `vulkan`, `zlib`.
  - **Missing on this Linux host:** MSVC, Windows SDK, `x86_64-w64-mingw32-g++`, `clang++`, `mips64el-linux-gnuabi64-objdump`, `pcsx2`/`pcsx2-qt`, and FFmpeg dev packages (`libavcodec-dev` etc. not listed by `pkg-config`).
- **Implication:**
  - `configure.bat`, `build.bat`, `run.bat`, `setup.bat`, `package-release.bat`, `Tools/win/vsenv.cmd` are **Windows-only**.
  - `Port/CMakeLists.txt` currently uses MSVC-only compiler/linker flags (`/bigobj`, `/fp:precise`, `/arch:AVX2`, `/FORCE:MULTIPLE`, `/STACK:16777216`, `sotc.rc`), while `Port/src/main.cpp` and `Port/src/sotc/watchdog.cpp` wrap Win32 APIs in `#if defined(_WIN32)`.
  - `LightVelox/PS2Recomp` supports CMake builds on Linux (including `ps2_recomp`, `ps2xAnalyzer`, `ps2xIOP`, `ps2_runtime`, `ps2xTest`), except where GPU OpenGL context creation uses WGL (see Section 2.6; CPU GS backend `PS2X_GS_GPU=0` is portable).
  - Therefore, Gemini Hydrogen **can** build and run `ps2_recomp`, `ps2xAnalyzer`, `ps2xTest`, `ps2xIOP` tests, and a Linux-native headless/CPU-GS (and potentially OpenGL-if-portable) test executable locally on Ubuntu while keeping Windows x64 (`MSVC`) as a first-class supported target.

---

## 2. Deep Component-by-Component Audit (10 Mandatory Domains)

### 2.1 Disc Identity, ISO9660, Extraction, File Access, and Optical-Disc Semantics
- **Files inspected:** `Tools/iso9660.py` (150 lines), `Port/src/sotc/game_disc.cpp` (128 lines), `Port/profile/SCES-53326_v1.00.json` (40 lines), `Port/src/sotc/hle/sce_cdvd.cpp` (161 lines), `Port/src/sotc/hle/sce_fileio.cpp` (334 lines).
- **Verified findings:**
  - `Tools/iso9660.py` is a clean, pure-Python, zero-dependency 2048-byte-sector ISO9660 reader (`Iso9660`: PVD parse, recursive `walk()`, case-insensitive `find()`, `extract()`). Tested directly on `Game/Rule of Rose (USA).iso`: **SUCCEEDED** (exit 0, parsed `volume_space_size: 1656960`, `publisher_id: ATLUS USA INC.`).
  - `Port/src/sotc/game_disc.cpp` uses `PS2CdImage` from `ps2_runtime` to mount the ISO, verify `SYSTEM.CNF` contains `kBootElfPath`, SHA-256 verify the boot ELF and listed module files (`Sha256::hex`), and cache the extracted boot ELF into `game_data/`. **Design is generic** except it reads `sotc_layout_generated.h` and checks XFF `kModuleFiles` (for Rule of Rose, it should verify `SLUS_214.48` + critical disc files like `IOPCONF.CNF` / `SYSTEM.INI` / `MODULES/RXSNDDRV.IRX`).
  - `Port/src/sotc/hle/sce_cdvd.cpp` wraps `ps2_stubs::sceCdRead`, `sceCdReadIOPm`, `sceCdSync`, `sceCdSyncS` with a cycle-accurate DVD seek/transfer timing model (`SOTC_DVD_RATE`, `SOTC_DVD_SEEK_MS`) plus save-state serialization (`ps2x::savestate::registerExtension`). **CRITICAL:** The guest addresses (`0x001DB688`, `0x001DB868`, `0x00117098`, `0x00117138` at lines 126-135) are **100% SOTC-specific** and MUST NOT be reused.
  - `Port/src/sotc/hle/sce_fileio.cpp` wraps 28 `fio`/`sceOpen`/`sceRead`/`sceWrite`/`sceGetstat`/`sceCdSearchFile` bindings (lines 291-320) with SOTC-specific addresses and PAL `kFieldsPerSecond = 50` (line 80). Rule of Rose is **NTSC 60 Hz**, has different addresses, and uses `cdrom0:` paths for `.RPK`, `.ARA`, `.STR`, `.PSS`, `.BIN`, `.IRX`.

### 2.2 PS2Recomp Fork, Generator Inputs, R5900 Codegen, Indirect Calls, Relocations
- **Files inspected:** `CMakeLists.txt` (27 lines), `Port/recomp/sotc.toml` (40 lines), `Docs/ARCHITECTURE.md` (209 lines), `Docs/PROGRESS.md` (lines 1-437), `Tools/verify_reloc_sites.py`, `LightVelox/PS2Recomp` upstream file tree & `CMakeLists.txt`.
- **Verified findings:**
  - `LightVelox/PS2Recomp` is a heavily enhanced fork of `ran-j/PS2Recomp` (diverged from `75d729ce` on 2026-09-19) adding:
    - Exact EE FPU rounding/alignment (`FPU_ADD_SUB`, round-to-nearest `DIV.S`/`SQRT.S`/`RSQRT.S`), `LQ`/`SQ` 16-byte alignment masking, VU0 macro fixes (`VCLIP`, `VRNEXT`/`VRINIT`/`VRXOR` PS2 LFSR, shared VU0 `R`, VU0 data-memory ops `VLQI`/`VSQI`/`VLQD`/`VSQD`/`VILWR`/`VISWR`).
    - Non-throwing blocking syscalls (`handleSyscall` + `DeferredTransferScope`), lazy EE timers, `EeScheduler::unwinding()` fix for recursive calls, `EeScheduler::skipIdleCycles()`, `waitUntilCycleResume`, `waitVSyncResume`.
    - `general.runtime_relocations` TOML option (used for SOTC's 26,981 runtime-patched XFF import sites; **NOT needed** for Rule of Rose because `SLUS_214.48` is a static `ET_EXEC` ELF with `has_rel=False`!).
    - `auto_stub_by_name = false` with explicit `stubs = [...]` list in TOML.
    - `ps2xAnalyzer` (`sce_symbol_scanner.cpp` + `sce_symbol_database_data.h`) for identifying stripped Sony SDK functions in retail ELFs!
    - `vu1_recomp` (`ps2xTest/tools/vu1_recomp.cpp`) for AOT compiling captured VU1 microprograms into SIMD C++ with bit-exact verification (`PS2X_VU1_VERIFY=1`).
  - **Known Recompiler Caveat (VERIFIED in `Docs/ARCHITECTURE.md:109-111`):** `j` tail-jumps between recompiled functions are emitted as direct C++ calls and bypass `g_ps2RecompiledFunctionTable` when `direct_tail_calls` is on (note `sotc.toml:12` sets `direct_tail_calls = false`). Keeping `direct_tail_calls = false` ensures tail-call targets go through the function table so hooks work cleanly.
  - **Rule of Rose specific check needed in M03:** Verify how `ps2xRecomp`'s `ElfParser` handles `SLUS_214.48`'s 1,449 `.gnu.linkonce.t.*` sections and excludes `.vutext` (`0x00291230..0x002953B0`, which has `SHF_EXECINSTR` set!).

### 2.3 SOTC Boot Process, Synthetic ELF, and XFF Module Linker
- **Files inspected:** `Tools/sotc_link.py` (664 lines), `Tools/xff.py` (220 lines), `Port/src/sotc/module_guard.cpp` (274 lines), `Docs/GAME_BUILD.md` (169 lines).
- **Verified findings:**
  - SOTC's `SCES_533.26` (229 KB) is only a dynamic loader for `KERNEL.XFF`, `MANAGER.XFF`, and `GAMECORE.XFF`. Therefore `Tools/xff.py`, `Tools/sotc_link.py`'s XFF linking/relocation, `Tools/verify_reloc_sites.py`, and `module_guard.cpp`'s `verifyModule()` / `kRuntimeRelocationSites` are **100% SOTC-specific** and MUST be discarded/replaced.
  - **Reusable patterns inside those files:**
    - `Discovery` + `ElfWriter` in `Tools/sotc_link.py` (lines 37-169, 338-404) show a clean pure-Python blueprint for discovering functions (`jal`, `j`, pointer tables, `lui/addiu`) and emitting an annotated ELF / `functions.csv` / `address_map.csv` / `layout_generated.h`.
    - `applyEeFloatingPointMode()`, `installRamDumpFromEnvironment()`, `installMemoryTracesFromEnvironment()`, `installCallTracesFromEnvironment()` in `module_guard.cpp` (lines 49-63, 81-273) are generic diagnostic utilities (except hardcoded `CreateThread`/`StartThread`/`ChangeThreadPriority` addresses at lines 171-186, which are SOTC-specific!).

### 2.4 EE Kernel, Syscalls, Interrupts, DMA, VIF, GIF, GS, VU0/VU1, Scheduler
- **Files inspected:** `Docs/ARCHITECTURE.md`, `Docs/PROGRESS.md`, `Port/src/main.cpp`, `Port/src/sotc/idle_thread.cpp`.
- **Verified findings:**
  - All core EE hardware/kernel emulation lives generically inside `External/PS2Recomp/ps2xRuntime`: EE syscalls, `EeScheduler`, RDRAM/scratchpad/MMIO, DMA chains (cap raised to `2^20` tags), VIF1 (`DIRECT`, `MPG`, `UNPACK` with SIMD option), GIF PATH1/PATH2/PATH3, GS INTC 0 (`FINISH`/`SIGNAL`/`VSINT`), VU0 macro & micro, VU1 interpreter + AOT `vu1_recomp` + `MTVU` async worker threads, save-state serialization (`ps2_save_state`).
  - `Port/src/sotc/idle_thread.cpp` hooks SOTC's `iosRecvMsg` (`0x001ABED0`, `$ra == 0x001A808C`) to call `EeScheduler::skipIdleCycles()`. The runtime primitive `skipIdleCycles()` is generic; the hook address is SOTC-specific and must NOT be enabled for Rule of Rose unless/until an actual Rule of Rose idle-spin site is identified.

### 2.5 IOP Runtime, IRX Modules, CDVD, Pad, Memory Cards, SPU2, MPEG/IPU, SIF
- **Files inspected:** `Docs/ARCHITECTURE.md:183-204`, `Docs/PROGRESS.md:52-102`, `Tools/irx_imports.py`, `LightVelox/PS2Recomp` repo tree.
- **Verified findings:**
  - `ps2xIOP` runs real PS2 R3000A IRX modules unmodified! It already runs **the exact byte-for-byte identical Sony SDK 3.0 binaries** found on the Rule of Rose disc: `IOPRP300.IMG`, `SIO2MAN.IRX`, `SIO2D.IRX`, `DBCMAN.IRX`, `DS1O_D.IRX`, `LIBSD.IRX`.
  - `ps2xIOP` also contains `ps2xIOP/src/modules/mcserv.cpp` and `ps2xIOP/src/emulator/devices/iop_memcard.cpp` (crucial because Rule of Rose uses `MCMAN.IRX` + `MCSERV.IRX` / `libmc 3020`, whereas SOTC used `MC2_D.IRX` / `libmc2 3020`).
  - `IopSpu2` decodes PS-ADPCM at 48 kHz with 4-tap Gaussian interpolation, ADSR, mixer gates, and core routing; reverb, noise, pitch modulation, and AutoDMA PCM input remain documented fidelity gaps (`Docs/ARCHITECTURE.md:196-197`).
  - **CRITICAL GAP TO ADDRESS FOR RULE OF ROSE:** `sotc-vibe-pc` disabled FFmpeg (`CMakeLists.txt:17`: `PS2X_ENABLE_FFMPEG OFF`) and stubbed `sceMpeg*`/`sceIpu*` (`Port/recomp/sotc.toml:33-38`) because SOTC uses real-time cutscenes. Rule of Rose has **41 `.PSS` MPEG-2 FMVs (1,491.8 MiB)** including `CP_LOGO.PSS` and story movies, and links `libmpeg 3000` + `libipu 3000`. `LightVelox/PS2Recomp` already contains `Stubs/MPEG.cpp`, `Stubs/IPU.cpp`, and `PS2X_ENABLE_FFMPEG` CMake wiring — we must inspect and test it early!

### 2.6 Graphics Path (GS Emulation, OpenGL, Compute/CPU Fallback, Presentation)
- **Files inspected:** `Docs/ARCHITECTURE.md:138-181`, `Docs/PROGRESS.md:8-30, 123-175, 305-336, 389-430`, `Port/src/sotc/display_mode.cpp`, `Port/src/sotc/motion_blur.cpp`.
- **Verified findings:**
  - `ps2xRuntime` provides three GS backends behind a common interface:
    1. `GSCpuBackend` + `GSThreadedBackend` (software reference & band-parallel fast CPU rasterizer — fully portable, deterministic, bit-exact oracle target).
    2. `GSGpuBackend` compute-shader rasterizer (OpenGL 4.6 SSBO 16x16 tiles, COW texture pages).
    3. `GSGpuBackend` hardware-rasterized path (`PS2X_GS_HW_RASTER`, `GL_ARB_fragment_shader_interlock`, disk shader cache `hw_*.glbin`).
  - CRTC presentation follows `PMODE`/`DISPFB`/`DISPLAY`/`SMODE2` directly with zero game-specific heuristics (`Docs/PROGRESS.md:127-136`).
  - `Port/src/sotc/display_mode.cpp` and `Port/src/sotc/motion_blur.cpp` are **almost entirely hardcoded SOTC addresses** (widescreen projection/sprite/font hooks, PAL/NTSC menu skip, `screenBlur`). Only `configureHostDisplay()` (`FLAG_VSYNC_HINT`, `SetTargetFPS`) is generic.

### 2.7 Input Mapping, Camera Controls, Rumble, and Saves
- **Files inspected:** `Port/src/sotc/config.cpp`, `Port/src/sotc/mouse_camera.cpp`, `Docs/PROGRESS.md:68-103`.
- **Verified findings:**
  - Pad input runs generically through `ps2_host_input` -> `IopHost::readPad` -> `SIO2` -> `VirtualDualShock2` -> `SIO2MAN`/`SIO2D`/`DBCMAN`/`DS1O_D` -> `libpad2` (`scePad2Read`). Rule of Rose uses the **exact same** `SIO2MAN`/`SIO2D`/`DBCMAN`/`DS1O_D` + `libpad2 3020` + `libdbc 3020` + `libvib 3000` stack!
  - `Port/src/sotc/mouse_camera.cpp` is **100% SOTC-specific** (hardcoded Wander camera struct offsets `kCameraCommon = 0x1370` etc.) and MUST be removed — Rule of Rose uses fixed/scripted horror camera angles, not a free-orbit mouse camera!
  - `Port/src/sotc/config.cpp` is a clean INI loader (`PS2X_*` keys), needing only prefix renaming (`SOTC_*` -> `ROZU_*`) and Rule of Rose-appropriate defaults (no forced right-stick inversion, no mouse camera, NTSC 60 Hz default).
  - Save states (`F5`/`F9`, `ps2x::savestate`) are generic in `ps2_runtime`. Memory cards (`memcards/Mcd001.ps2`) need verification with `MCMAN.IRX` + `MCSERV.IRX`.

### 2.8 `Port/` Config, Generated Files, Build Scripts, Runtime Hooks, Hardcoded Assumptions
- **Files inspected:** `CMakeLists.txt`, `Port/CMakeLists.txt`, `Port/recomp/sotc.toml`, `Port/src/main.cpp`, `Port/src/sotc/function_hooks.cpp`, `Port/src/sotc/log.cpp`, `Port/src/sotc/sha256.cpp`, `Port/src/sotc/watchdog.cpp`, `Port/src/sotc/debug_script.cpp`, `Port/assets/sotc.rc`, `*.bat`.
- **Verified findings:**
  - `Port/src/sotc/function_hooks.cpp` (212 lines): **100% generic** lock-free fast-path hook/observer table (`observeEntry`, `replace`, `logBindings`). Only namespace/log macro names are `sotc`.
  - `Port/src/sotc/sha256.cpp` (139 lines) & `Port/src/sotc/log.cpp` (88 lines): **100% generic**, zero Win32 dependencies.
  - `Port/src/sotc/debug_script.cpp` (315 lines): Generic except `kDefaultHook = 0x001C35B0u` (line 25) and env var names `SOTC_DEBUG_SCRIPT`/`SOTC_DEBUG_HOOK`.
  - `Port/src/sotc/watchdog.cpp` (667 lines): Generic timeline/poke/watchdog framework, with Win32-only stack walking/hardware watchpoints (`#if defined(_WIN32)`) and one SOTC hardcoded hook at line 619 (`0x1C3070u` `timeline_present`).
  - `Port/src/main.cpp` (287 lines): Clean composition root; contains SOTC-specific calls (`installModuleGuards`, `installIdleThreadSkip`, `installDisplayMode`, `installMouseCamera`, `installMotionBlurOption`, `installLibgcc`), window title `"Shadow of the Colossus"`, and Win32-only `executableDirectory()` / crash reporter / `SetPriorityClass` / `_putenv_s` / icon resource.

### 2.9 Test Harnesses, PCSX2 Oracle, Logs/Traces, Frame Comparison, Diagnostics
- **Files inspected:** `Tools/pine.py`, `Tools/gsdump.py`, `Tools/gs_vram.py`, `Tools/gsr_compare.py`, `Tools/gstrace_summary.py`, `Tools/state_ram_extract.py`, `Tools/irx_imports.py`, `Tools/audio_check.py`, `Tools/golden_run.py`, `Tools/scenario.py`, `Tools/measure_boot.py`, `Tools/boot_milestones.py`, `Tools/compare_ram.py`, `Tools/state_check.py`, `Tools/vu0_corpus.py`, `Docs/TESTING.md`.
- **Verified findings:**
  - Generic, immediately reusable oracle/diagnostic tools: `Tools/iso9660.py`, `Tools/pine.py` (PCSX2 PINE IPC client), `Tools/irx_imports.py`, `Tools/gs_vram.py`, `Tools/gsdump.py`, `Tools/gsr_compare.py`, `Tools/gstrace_summary.py`, `Tools/state_ram_extract.py`, `Tools/find_walk_delta.py`, `Tools/pystrings.py`, `Tools/vu0_corpus.py`.
  - SOTC-specific harnesses requiring rewrite for Rule of Rose checkpoints: `Tools/scenario.py` (colossi warps), `Tools/golden_run.py` (hardcoded `1dc7ac,1dc9d8` watch addresses), `Tools/boot_milestones.py`, `Tools/boot_phases.py`, `Tools/measure_boot.py`, `Tools/compare_ram.py` (imports `xff`), `Tools/state_check.py`, `Tools/performance_*.py`.

### 2.10 Git Layout, Submodules, Dependencies, and `.gitignore` Gaps
- **CRITICAL `.gitignore` AUDIT FINDING (VERIFIED):**
  - The tracked `.gitignore` (52 lines) is leftover from a prior prototype and is **MISSING** critical exclusions used by the `sotc-vibe-pc` layout:
    - Missing: `Port/generated/`, `build/`, `Analysis/extracted/`, `Analysis/oracle/`, `Emulator/`, `Tools/pcsx2-oracle/`, `*.state`, `*.ps2`, `memcards/`, `states/`, `game_data/`, `*.elf`, `*.ELF`, `*.vutext`, `*.pdb`, `*.dmp`, `*.gs`, `*.gsr`, `*.png` (test captures), `*.wav` (audio dumps), `rozu.ini`, `sotc.ini`.
  - **Mandatory M00 Fix:** Hydrogen MUST harden `.gitignore` BEFORE cloning/building/extracting or generating any code!

---

## 3. Concrete Dependency Matrix

| Dependency | Required Version / Pin | Host / Target | Source / Management |
|---|---|---|---|
| `LightVelox/PS2Recomp` | Pin to verified commit `d06a4ab4a6902e0ae324f184c22581c3aa387c36` (or dedicated `rozu-port` fork branch) | Both | Git submodule at `External/PS2Recomp` |
| CMake | `>= 3.21` (local: `4.2.3`) | Both | System package / VS CMake tools |
| Ninja | `>= 1.11` (local: `1.13.2`) | Both | System package / VS tools |
| C++20 Compiler | Windows: MSVC 19.38+ (VS 2022/2026); Linux: GCC 12+ (local: `g++ 15.2.0`) | Target / Dev | VS Build Tools / apt |
| Python | `>= 3.10` (local: `3.14.4`) | Both | System Python (stdlib only for core scripts; optional `Pillow` for contact sheets) |
| raylib, ELFIO, rabbitizer, fmt, toml11 | Managed by `External/PS2Recomp` CMake (`FetchContent`/bundled) | Both | In-repo CMake FetchContent |
| FFmpeg (`avcodec`, `avformat`, `avutil`, `swscale`, `swresample`) | Windows: `n7.1-241205` auto-fetched by `PS2Recomp` when `PS2X_ENABLE_FFMPEG=ON`; Linux: `libavcodec-dev` etc. via `pkg-config` | Both (needed for `.PSS` FMV) | CMake `ExternalProject` (Win) / apt (Linux) |
| OpenGL 4.6 driver | Required for `GSGpuBackend`; NOT required for `GSCpuBackend` headless tests | Runtime GPU | Host GPU driver |
| PCSX2 (Oracle only) | `>= 2.2` with PINE IPC + EE/IOP console logging | Verification only | External user install (`Emulator/`, git-ignored) |
| Rule of Rose Disc ISO | User-supplied NTSC-U `SLUS-21448` v1.00 (`SHA-256 95ff5d1298b1bb19443098852c95c42886605f01fb1ffa8d823ff496598989e9`) | Local runtime & codegen | `Game/` (git-ignored) |
