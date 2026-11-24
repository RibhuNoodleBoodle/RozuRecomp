# Phase C — Architecture Decision Record (ADR)

**Date:** 2026-11-24  
**Author:** Google Neon (High)

---

## ADR-001: Single Verified Disc Revision First (`SLUS-21448` NTSC-U v1.00)
- **Decision:** Target exclusively **Rule of Rose (USA, NTSC-U, `SLUS-21448`, v1.00)** (`SHA-256 95ff5d1298b1bb19443098852c95c42886605f01fb1ffa8d823ff496598989e9`, Redump MD5 `54e6990f5ed6e0d5b03b6ca7655b7cec`) until G7/G8 are proven.
- **Rationale:** Locally supplied and verified byte-exact against Redump. All ELF addresses, section bounds, and SDK stub locations are specific to this binary. Supporting PAL `SLES-54218` or JP `SCPS-15106` prematurely multiplies surface area without verified media.
- **Alternative Rejected:** Multi-region abstraction before first boot.

## ADR-002: Eliminate XFF Linker; Use Direct Static ELF Preparation (`Tools/ror_prepare.py`)
- **Decision:** Discard `Tools/xff.py`, `Tools/sotc_link.py`, `Tools/verify_reloc_sites.py`, and `module_guard.cpp`'s XFF verification. Replace with `Tools/ror_prepare.py` producing an annotated static ELF (`slus_21448_annotated.elf`) and `rozu_functions.csv` directly from `SLUS_214.48`.
- **Rationale:** Verified ELF inspection proved `SLUS_214.48` is a monolithic static `ET_EXEC` (`0x00100000..0x00828E94`) with `has_rel=False` and zero EE overlays. Carrying SOTC's XFF2 dynamic linker or `runtime_relocations` machinery would be dead complexity and a source of bugs.
- **Alternative Rejected:** Wrapping `SLUS_214.48` in a fake XFF profile to reuse `sotc_link.py`.

## ADR-003: Explicitly Exclude `.vutext` (`0x00291230..0x002953B0`) from EE Recompilation
- **Decision:** Strip `SHF_EXECINSTR` from `.vutext` in `slus_21448_annotated.elf` (while keeping its bytes loaded at `0x00291230` in guest RDRAM!) and exclude `0x00291230..0x002953B0` from `rozu_functions.csv`.
- **Rationale:** Verified that `.vutext` is marked `AX` (`SHF_EXECINSTR`) in the retail ELF but contains 44 VIF `MPG` VU microcode upload packets matching `.DVP.overlay.*`, NOT R5900 EE code. Keeping the bytes at `0x00291230` ensures guest VIF1 DMA reads the authentic VU microcode verbatim while preventing `ps2_recomp` from trying to disassemble VU microcode as MIPS.
- **Alternative Rejected:** Letting `ps2_recomp` scan all `SHF_EXECINSTR` sections unfiltered.

## ADR-004: Clean-Room GPL SDK Symbol Identification via `External/PS2Recomp/ps2xAnalyzer`
- **Decision:** Identify stripped Sony SDK functions (`sceSif*`, `sceCd*`, `sceOpen/Read/Write`, `sceMpeg*`, `sceIpu*`, `sceMc*`, `scePad2*`) using `External/PS2Recomp/ps2xAnalyzer` (GPL-3.0 `sce_symbol_database_data.h`) plus deterministic RPC-ID/syscall/string verification inside `Tools/ror_prepare.py`. Do **NOT** copy code, scripts, or symbol tables from `notmanrivera/ruleofrose-decomp`.
- **Rationale:** `notmanrivera/ruleofrose-decomp` has no `LICENSE` file (All Rights Reserved). `External/PS2Recomp` is GPL-3.0 (matching our project license) and already includes the exact Sony SDK signature database needed.
- **Alternative Rejected:** Importing symbol CSVs or Python tools from `ruleofrose-decomp`.

## ADR-005: Explicit Stub Allowlist (`auto_stub_by_name = false`, `direct_tail_calls = false`)
- **Decision:** Keep `auto_stub_by_name = false` and `direct_tail_calls = false` in `Port/recomp/rozu.toml`. Stub only the verified IOP/SIF/CDVD/FIO/TTY/MPEG/IPU boundary; keep all game logic, `i3d` engine, newlib `malloc`/`rand`/math/string, and DMA/VIF/GS packet builders as genuine recompiled EE code.
- **Rationale:** Prevents silent misbinding of game functions and guarantees every inter-function call/tail-jump respects `rozu::FunctionHooks`.
- **Alternative Rejected:** Enabling `auto_stub_by_name = true`.

## ADR-006: Pin `External/PS2Recomp` Submodule to `LightVelox/PS2Recomp` (`d06a4ab4`)
- **Decision:** Initialize `External/PS2Recomp` from `LightVelox/PS2Recomp` at verified commit `d06a4ab4a6902e0ae324f184c22581c3aa387c36` instead of raw upstream `ran-j/PS2Recomp`. Track any future generic fixes on a clean `rozu-port` branch inside the submodule with unit tests.
- **Rationale:** `LightVelox/PS2Recomp` already includes hundreds of hours of critical EE FPU, VU0 macro, VU1 AOT, `ps2xIOP` (`IOPRP300`, `SIO2MAN`, `DBCMAN`, `DS1O_D`, `LIBSD`, `IopSpu2`, `mcserv`), GS coverage/COLCLAMP, and save-state fixes proven by 477+ tests — and Rule of Rose uses 8 byte-identical IRX modules from the exact same SDK 3.0 stack.
- **Alternative Rejected:** Starting from upstream `ran-j/PS2Recomp` and re-discovering already-fixed EE/IOP/GS bugs.

## ADR-007: Dual-Target CMake (Windows x64 Primary Deployment + Linux x64 Local Dev/Test)
- **Decision:** Maintain Windows x64 (MSVC) as the primary deployment target (matching `sotc-vibe-pc`), while making `CMakeLists.txt`, `Port/CMakeLists.txt`, `Port/src/main.cpp`, and `Tools/generate.py` compile and pass headless/CPU-GS tests natively on the current Ubuntu Linux x64 host (`g++ 15.2` + Ninja). Explicitly document WGL-only GPU backend limitations on Linux if present in `PS2Recomp`.
- **Rationale:** Local workspace runs Ubuntu 26.04.1 without MSVC or MinGW. Enabling genuine local Linux compilation & execution lets Hydrogen run real build + runtime tests at every step without faking Windows verification.
- **Alternative Rejected:** Writing untested Windows-only `.bat`/MSVC code that Hydrogen cannot compile or execute locally.

## ADR-008: Treat `.PSS` FMV Playback (`PS2X_ENABLE_FFMPEG`) as First-Class Requirement
- **Decision:** Unlike `sotc-vibe-pc` (which forced `PS2X_ENABLE_FFMPEG OFF`), make `PS2X_ENABLE_FFMPEG` ON by default when FFmpeg libraries are available (Windows prebuilt auto-fetch or Linux `libavcodec-dev`), with an explicit diagnostic fallback option (`-DROZU_ENABLE_FFMPEG=OFF`) only for early pre-FMV Linux bring-up if host dev packages are absent.
- **Rationale:** Rule of Rose has 41 `.PSS` movies (1.49 GiB) starting with `CP_LOGO.PSS` at boot and carrying essential story cutscenes.
- **Alternative Rejected:** Permanently stubbing `sceMpeg*` to dummy black frames.

## ADR-009: Preserve Authentic NTSC 60 Hz Timing, Fixed Camera, and Gamepad-First Controls
- **Decision:** Remove SOTC's mouse camera (`mouse_camera.cpp`), widescreen/PAL hacks (`display_mode.cpp`), motion blur toggle (`motion_blur.cpp`), and forced right-stick inversion. Default to authentic 4:3 NTSC 60 Hz presentation, `GSCpuBackend` deterministic mode for bring-up, and DualShock 2 gamepad + clean keyboard defaults.
- **Rationale:** Rule of Rose is a fixed-camera NTSC survival horror title; SOTC camera/widescreen hacks would break UI/inventory/camera framing (known PCSX2 widescreen breakage on Rule of Rose maps/cards).
- **Alternative Rejected:** Porting SOTC's widescreen or mouse-camera hooks before native baseline is proven.

## ADR-010: Preserve User Starting Worktree & Use Dedicated Feature Branch
- **Decision:** Hydrogen creates a dedicated feature branch (e.g., `rozu/port-bringup`) from `HEAD` (`019f6de`), hardens `.gitignore` first, and commits clean, atomic milestone steps without destructive `git reset --hard` or `git clean -fd` against user files (`Google_Neon_Rule_of_Rose_Recomp_Architect.txt`, `Game/Rule of Rose (USA).iso`).
- **Rationale:** Respects user workspace safety and mandatory Git Commit Policy.
