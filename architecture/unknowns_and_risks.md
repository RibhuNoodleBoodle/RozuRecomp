# Phase B — Unknowns, Technical Risks, and Smallest Unblocking Tests

**Date:** 2026-11-24  
**Scope:** Rule of Rose (`SLUS-21448` v1.00) Native PC Static Recompilation (`RozuRecomp`)

---

## 1. High-Priority Blockers & Risks

### R1. Unpopulated `External/PS2Recomp` Submodule & Dirty Starting Tree (IMMEDIATE — M00)
- **Fact (VERIFIED):** `External/PS2Recomp/` is currently empty, and all `sotc-vibe-pc` files are untracked on top of commit `019f6de`. `.gitignore` is missing critical exclusions (`Port/generated/`, `*.state`, `*.elf`, `*.ps2`, `Analysis/extracted/`, `Analysis/oracle/`, `Emulator/`).
- **Risk:** Accidental commit of proprietary binaries/generated code, or broken builds due to unpinned/missing engine submodule.
- **Smallest Unblocking Test (M00):** Harden `.gitignore`, initialize/clone `External/PS2Recomp` at pinned SHA `d06a4ab4a6902e0ae324f184c22581c3aa387c36`, run `git status` and build `ps2_recomp` + `ps2xAnalyzer` + `ps2x_tests`.

### R2. Local Host (Ubuntu Linux x64) vs Default Deployment Target (Windows x64)
- **Fact (VERIFIED):** Base repo (`sotc-vibe-pc`) builds on Windows x64 MSVC (`*.bat`, `sotc.rc`, Win32 APIs in `main.cpp`/`watchdog.cpp`, WGL in `GSGpuBackend`). Local host is Ubuntu 26.04.1 Linux x86_64 with GCC 15.2 / CMake 4.2.3 / Ninja 1.13.2 and **no MSVC or MinGW cross-compiler**.
- **Risk:** Either failing to run local tests on Linux, or breaking Windows x64 MSVC compatibility while porting to Linux.
- **Smallest Unblocking Test (M00):** Inspect `External/PS2Recomp/ps2xRuntime/src/lib/gs/gpu/gs_gl.h` and `CMakeLists.txt` right after cloning `External/PS2Recomp`. Configure and build `ps2_recomp`, `ps2xAnalyzer`, `ps2_runtime`, and `ps2x_tests` on Linux with GCC + Ninja; verify whether `GSCpuBackend` (`PS2X_GS_GPU=0`, headless) runs natively on Linux while documenting any WGL-only limitation for `GSGpuBackend` on Linux. Maintain dual CMake toolchain flags (`if(MSVC) ... else() ...`) so Windows x64 MSVC remains first-class.

### R3. `.vutext` Marked `SHF_EXECINSTR` + 1,449 `.gnu.linkonce.t.*` Sections in `SLUS_214.48`
- **Fact (VERIFIED):** `.vutext` (`0x00291230..0x002953B0`, 16 KB) carries `SHF_EXECINSTR` inside `PT_LOAD[0]`, interleaved between `.gnu.linkonce.t.*` sections (`0x00280E88..0x00291230` and `0x002953B0..0x00295EB8`).
- **Risk:** If `ps2xAnalyzer` or `ps2_recomp` treats `.vutext` as R5900 code, it will generate invalid instructions or decode errors; conversely, if `ps2_recomp` only scans `.text` and ignores `.gnu.linkonce.t.*`, all 1,449 inline/template C++ methods will be missing from the function table!
- **Smallest Unblocking Test (M03):** Inspect `ps2xRecomp/src/lib/elf_parser.cpp` and run `Tools/ror_prepare.py` + `ps2_recomp` on `SLUS_214.48`. Verify that all 1,449 `.gnu.linkonce.t.*` addresses ARE present in `register_functions.cpp` and ZERO addresses inside `0x00291230..0x002953B0` are emitted as EE functions.

### R4. Stripped Sony SDK Symbols & Explicit HLE Stub Boundary
- **Fact (VERIFIED):** `SLUS_214.48` has no `.symtab`. `sotc-vibe-pc` relies on `auto_stub_by_name = false` + explicit `stubs = [...]` matching symbol names for SIF/IOP RPC, CDVD, File I/O, TTY, and MPEG/IPU.
- **Risk:** If any `sceSif*`, `sceCd*`, `sceOpen`/`sceRead`, `sceMpeg*`, or `sceIpu*` function in `SLUS_214.48` is missed by `ps2xAnalyzer`, the recompiled EE code will attempt hardware-level SIF DMA or raw IPU MMIO and hang during boot! Conversely, stubbing a function misidentified by a fuzzy signature will corrupt execution.
- **Smallest Unblocking Test (M03 & M05):** Run `ps2xAnalyzer` on `SLUS_214.48`, cross-verify every matched SCE stub address by checking its SIF RPC server ID (`0x80000001`, `0x80000006`, `0x80000592..A`, `0x80000400`), syscall number, or nearby error string (`libdbc`, `libmc`, `sceMpeg`), and record a verified `rozu_sdk_stubs_audit.md` before trusting any stub.

### R5. MPEG-2 / IPU `.PSS` FMV Playback (41 Movies, 1.49 GiB)
- **Fact (VERIFIED):** Rule of Rose opens with `CP_LOGO.PSS` and contains 41 `.PSS` movies (`libmpeg 3000` + `libipu 3000`). `sotc-vibe-pc` built with `PS2X_ENABLE_FFMPEG OFF` and never tested full `.PSS` playback.
- **Risk:** Boot could stall at `CP_LOGO.PSS` if `sceMpeg*`/`sceIpu*` stubs return stub frames indefinitely, crash, fail to demux audio/video PTS, or fail on Linux without `libavcodec-dev` installed.
- **Smallest Unblocking Test (M05/M06):** Inspect `External/PS2Recomp/ps2xRuntime/src/lib/Kernel/Stubs/MPEG.cpp` & `IPU.cpp`. First test boot with `PS2X_ENABLE_FFMPEG=OFF` (verify whether `CP_LOGO.PSS` advances cleanly or hangs) and then enable `PS2X_ENABLE_FFMPEG=ON` and verify real frame decoding & audio sync on `CP_LOGO.PSS` and `MV01_TIT.PSS`.

### R6. `MCMAN.IRX` + `MCSERV.IRX` (`libmc 3020`) vs SOTC's `MC2_D.IRX`
- **Fact (VERIFIED):** Rule of Rose loads `MCMAN.IRX` + `MCSERV.IRX` (classic `libmc`), whereas SOTC loaded `MC2_D.IRX` (`libmc2`). `MCMAN.IRX` imports `secrman(1.03:3fn)`, `sio2man`, `cdvdman`, `ioman`, `modload`.
- **Risk:** `ps2xIOP` may have untested code paths in `secrman` or `MCMAN`/`MCSERV` RPC handling, causing boot-time memory-card probe hangs or save corruption.
- **Smallest Unblocking Test (M05 & M10):** Observe `IOPCONF.CNF` loading of `MCMAN.IRX` and `MCSERV.IRX` in M05 (must initialize without unresolved IOP imports or deadlock). In M10, create/save/reload `/BASLUS-21448` on `memcards/Mcd001.ps2` and verify readability in PCSX2.

### R7. `RXSNDDRV.IRX` Audio Streaming & Potential AutoDMA PCM Gap
- **Fact (VERIFIED/INFERRED):** `RXSNDDRV.IRX` imports `libsd` ordinals `[4..11, 13, 15, 17, 18, 20, 23, 26]` (note: ordinal 17 is `sceSdVoiceTrans`, 18 is `sceSdBlockTrans` — AutoDMA!). `Docs/ARCHITECTURE.md:196-197` explicitly documents that **AutoDMA PCM input, reverb, noise, pitch modulation, and SPU2 IRQ address handling remain fidelity gaps in `IopSpu2`**.
- **Risk:** `.SE` sound effects (ADPCM via `sceSdVoiceTrans`) will likely work out of the box, while `.STR` streamed music/voices and `.PSS` FMV audio may be silent or stall if `RXSNDDRV.IRX` relies on `sceSdBlockTrans` (AutoDMA) and SPU2 DMA transfer-complete IRQs!
- **Smallest Unblocking Test (M06/M07):** Trace `RXSNDDRV.IRX` `libsd` calls at title screen and during first cutscene/FMV. If `sceSdBlockTrans` (AutoDMA) is active and silent/stalling, implement generic AutoDMA PCM ring support in `External/PS2Recomp/ps2xIOP/src/emulator/devices/iop_spu2.cpp` with unit tests in `iop_spu2_tests.cpp`.

### R8. Indirect Calls (`jalr`: 558 sites) & Switch Jump Tables (`jr`: 297 sites)
- **Fact (VERIFIED):** `SLUS_214.48` is C++ (`ee-gcc 2.96`) with 284 vtables (`.gnu.linkonce.d.*`) and 558 `jalr` call sites plus 297 non-`$ra` `jr` sites.
- **Risk:** Missing any virtual method or callback target during function discovery causes `MissingFunctionPolicy::Stop` at runtime; misclassifying a switch jump-table entry as a separate function breaks intra-function CFG.
- **Smallest Unblocking Test (M03):** Parse all 284 `.gnu.linkonce.d.*` vtables (each entry pointing into `.text` or `.gnu.linkonce.t.*` is a guaranteed function entry!) and distinguish `.rodata` switch jump tables (all targets inside a single enclosing function) from function-pointer tables. Verify 0 missing-function stops during M05–M09 runtime sweeps.

### R9. No Local PCSX2 Oracle Installed Yet on This Machine
- **Fact (VERIFIED):** `which pcsx2 pcsx2-qt` returned nothing on this Ubuntu host; no PS2 BIOS is present (and must NOT be downloaded).
- **Risk:** Cannot immediately perform automated PINE RAM/frame diffs against PCSX2 on this machine until the user supplies PCSX2 + their own legally dumped PS2 BIOS locally.
- **Smallest Unblocking Test:** Design all M00–M06 acceptance gates to have rigorous **self-verifying native checks** (exit codes, unit tests, deterministic traces, VRAM hashes, non-black frame checks, audio waveform energy checks) PLUS **optional PCSX2 PINE/GS-dump oracle commands** that activate as soon as `Emulator/` is configured by the user.

### R10. EE Timing, FPU Rounding, and `i3d` Engine GS/VU1 Quirks
- **Fact (UNKNOWN):** We have not yet verified whether `SLUS-21448` requires specific PCSX2 `GameIndex.yaml` fixes (e.g., EE chop rounding, VU clamping, specific GS half-pixel/interlace/palette tricks, or subtitle-over-FMV blending).
- **Risk:** Subtle visual glitches, animation drift, or black screens during FMV subtitles.
- **Smallest Unblocking Test (M06–M08):** Keep `applyEeFloatingPointMode()` (RTZ+FTZ+DAZ) enabled by default (matching EE hardware), log all `i3d` GS/VIF/VU1 commands via `PS2X_GS_TRACE` / `GSCpuBackend` reference mode first (`PS2X_GS_GPU=0`, `PS2X_MTVU=0`, `PS2X_VU1_RECOMP=0`) before enabling async/GPU accelerations.
