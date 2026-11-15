# 01 — Environment, Upstream Baseline, and Media Inventory

## 1. Host Hardware, OS, and Storage Profile

All values below were captured from the live host environment on 2026-11-15 via `uname`, `lscpu`, `lspci`, `glxinfo`, `vulkaninfo`, `free`, and `df`.

| Subsystem | Verified Specification | Operational Constraint / Impact |
| :--- | :--- | :--- |
| **OS & Kernel** | Ubuntu 26.04.1 LTS (Resolute Raccoon), Linux `7.0.0-43-generic x86_64` | Modern glibc (`2.42`) and GCC 15.2.0 toolchain. |
| **CPU** | `Intel(R) Core(TM) i5-7200U CPU @ 2.50GHz` (Kaby Lake-U, Family 6 Model 142 Stepping 9) | **2 physical cores / 4 hardware threads**, base 2.50 GHz, boost 3.10 GHz, 3 MiB L3 cache. Supports `sse2`, `ssse3`, `sse4_1`, `sse4_2`, `avx`, `avx2`, `fma`, `bmi1`, `bmi2`. Generated R5900 SSE4.1/AVX2 code executes natively without `sse2neon` translation. |
| **GPU** | `Intel(R) HD Graphics 620 (KBL GT2)`, PCI ID `8086:5916` (rev 02, HP subsystem `103c:822e`) | Kernel driver `i915`. Unified memory architecture sharing dual-channel/single-channel system DDR4 bandwidth with the CPU. |
| **Graphics APIs** | Mesa `26.0.8-1ubuntu0.3`: OpenGL `4.6 (Core & Compatibility Profile)`, GLSL `4.60`, OpenGL ES `3.2`, Vulkan `1.4.335` (`Intel open-source Mesa driver`, conformance `1.4.0.0`) | `ps2xRuntime`'s `raylib` 5.5 windowing/texture presenter runs natively on OpenGL 3.3+/4.6. Per-frame full-texture CPU->GPU uploads (`UpdateTexture`) consume shared memory bandwidth and must be minimized on HD 620. |
| **System Memory & Swap** | `15 GiB` total RAM (`9.8 GiB` available at baseline), **`0 B` swap (`Swap: 0B`)** | **CRITICAL HAZARD**: With zero swap space configured, any C++ compilation or `ld` link step that exceeds ~9.5 GiB RSS will immediately trigger the Linux kernel OOM-killer (`SIGKILL`). Parallel compilation of huge generated translation units MUST be bounded (`ninja -j2`, chunked output or bounded unity batches). |
| **Root Filesystem (`/`)** | `/dev/sdb3`: `59 GiB` total, `55 GiB` used, **`1.1 GiB` free (99% full)** | **CRITICAL HAZARD**: `/tmp` and `/home/ribhu` reside on `/dev/sdb3`. Writing CMake FetchContent caches, compiler temporaries (`/tmp/cc*`), Ghidra projects, or extracted ISO files to `/` will exhaust disk space and fail builds. |
| **Workspace Filesystem (`/mnt/6421-8598`)** | `/dev/sda2`: `354 GiB` total, `109 GiB` used, **`245 GiB` free (32% used)** | **MANDATORY MITIGATION**: Every build, extraction, Ghidra headless run, and test command MUST export `TMPDIR=/mnt/6421-8598/building/RozuRecomp/out/tmp` and keep all build/output directories inside `/mnt/6421-8598/building/RozuRecomp/out/`. |

---

## 2. Installed Host Toolchain & Missing Optional Packages

| Tool / Package | Status | Path / Version | Notes |
| :--- | :--- | :--- | :--- |
| **C/C++ Compiler** | Installed | `/usr/bin/gcc`, `/usr/bin/g++` `15.2.0` (`Ubuntu 15.2.0-19ubuntu2`) | `clang`/`clang++` is NOT installed. Use GCC 15.2.0 with `-std=c++20`. |
| **CMake** | Installed | `/usr/bin/cmake` `4.2.3` | Supports `CMakeLists.txt` (`cmake_minimum_required(VERSION 3.20)`). |
| **Ninja** | Installed | `/usr/bin/ninja` `1.13.2` | Preferred generator (`-G Ninja`). |
| **Python 3** | Installed | `/usr/bin/python3` `3.14.4` | Available for ELF/section/symbol analysis and validation scripts. |
| **Binutils / ELF Tools** | Installed | `/usr/bin/readelf`, `/usr/bin/objdump`, `/usr/bin/nm`, `/usr/bin/strip` (GNU Binutils `2.46`) | Host x86_64 binutils (`readelf` parses MIPS ELF headers/sections; `objdump` only lists x86/i386 targets, so R5900 disassembly uses Python or `rabbitizer`). |
| **ISO Extraction Tools** | Installed | `/usr/bin/isoinfo`, `/usr/bin/7z` (`26.00`), `/usr/bin/xorriso` (`1.5.6`) | `7z` and `isoinfo` extract ISO 9660 contents without root/mount privileges. |
| **Java Runtime** | Installed | `/usr/bin/java` `OpenJDK 25.0.5.0.3` (`2026-10-24`) | Suitable for Ghidra headless execution if Ghidra is unpacked under `/mnt/6421-8598/`. |
| **Ghidra** | **Not Installed** | `ghidraRun` / `analyzeHeadless` not present on filesystem | Optional in M02 because `SLUS_214.48` retains 1,449 `.gnu.linkonce.t.*` section headers, 284 `.gnu.linkonce.d._vt$*` vtables, 648 Sony SDK signatures, and an exact SHA-1 match (`f9abd6dc53070750dfcae3b44184fb9852e603fb`) with verified `SLUS_214.48` function boundary catalogs. |
| **FFmpeg Runtime vs Dev** | **Partial** | `/usr/bin/ffmpeg` and `/usr/lib/x86_64-linux-gnu/libavcodec.so.62.11.100` installed; **`libavcodec.pc` / `libav*-dev` headers missing** | `ps2xRuntime/CMakeLists.txt` defaults `PS2X_ENABLE_FFMPEG=ON` and calls `pkg_check_modules(FFMPEG REQUIRED IMPORTED_TARGET libavformat libavcodec libavutil libswscale libswresample)`. Until `libav*-dev` is installed or staged in `out/deps/ffmpeg`, CMake MUST be configured with `-DPS2X_ENABLE_FFMPEG=OFF` (M01–M06). |

---

## 3. Repository & Upstream `ran-j/PS2Recomp` Baseline

* **Local Repository Path**: `/mnt/6421-8598/building/RozuRecomp`
* **Configured Remote (`origin`)**: `https://github.com/RibhuNoodleBoodle/RozuRecomp`
* **Upstream Repository**: `https://github.com/ran-j/PS2Recomp.git`
* **Active Branch**: `main`
* **Verified Local `HEAD` Commit**: `e5636981a1c9de368f6b71e819c3dc188dfedbf4` (`GIF: treat FLG=3 like IMAGE everywhere a GIFtag is parsed (#384)`, committed 2026-10-23)
* **Verified Upstream `ran-j/PS2Recomp` `refs/heads/main`**: `e5636981a1c9de368f6b71e819c3dc188dfedbf4` (verified live via `git ls-remote https://github.com/ran-j/PS2Recomp.git`). Local `HEAD` is **100% up-to-date** with upstream `ran-j/PS2Recomp` `main`.
* **Upstream Release Tags**: `v0.0` (`8584c061...`), `v0.1` (`669114f3...`), `v0.2` (`7ca6a866...`), `v0.3` (`cad1ca0b...`), `v0.4` (`93e221fe...`).
* **External CMake FetchContent Dependencies** (configured in top-level/subproject `CMakeLists.txt`):
  * `fmt` (`10.2.1`)
  * `toml11` (`v4.4.0`)
  * `rabbitizer` (`1.13.0`, C++ MIPS R5900 instruction decoder)
  * `elfio` (`Release_3.12`)
  * `raylib` (`5.5`)
  * `nlohmann_json` (`v3.11.3`)
  * `imgui` (`v1.91.8`)
  * `rlImGui` (`f383eeb87d8fb4ce73efd8fb9fb4ddb4fb7ac9d8`)

---

## 4. User-Supplied Game Media Verification (`Rule of Rose (USA).iso`)

### 4.1 Disc Image Identity
* **Path**: `/mnt/6421-8598/building/RozuRecomp/Rule of Rose (USA).iso`
* **File Size**: `3,393,454,080` bytes (`3.16 GiB`, `1,656,960` sectors × `2,048` bytes/sector)
* **SHA-256**: `95ff5d1298b1bb19443098852c95c42886605f01fb1ffa8d823ff496598989e9`
* **ISO 9660 Volume Header**:
  * System ID: `PLAYSTATION`
  * Publisher ID: `ATLUS USA INC.`
  * Data Preparer ID: `SONY COMPUTER ENTERTAINMENT INC.`
  * Application ID: `PLAYSTATION`
  * Creation Timestamp: `2006-07-27 19:56:19.00`
* **Git Safety Warning**: `Rule of Rose (USA).iso` currently resides in the repository root and `.gitignore` only ignores `build/`, `out/`, `.vs/`, and `.vscode/`. Flash Milestone M00 MUST add `*.iso`, `*.ISO`, `SLUS_*`, `*.IRX`, and `*.IMG` to `.gitignore` before any code commits.

### 4.2 Boot & Configuration Files on Disc

#### `SYSTEM.CNF` (57 bytes, LBA 266)
* **SHA-256**: `93843e865293ca2e06bd849262db9a724615bd16c9628bcaebdf6c14cf7baee1`
* **CRC32**: `0xbd6d0e08`
* **Contents**:
  ```ini
  BOOT2 = cdrom0:\SLUS_214.48;1
  VER = 1.00
  VMODE = NTSC
  ```

#### `SYSTEM.INI` (176 bytes, LBA 268)
* **SHA-256**: `7f1f312a02cfb6245e9d51937138a199c75c59c33016c1b869d56071da02f41c`
* **CRC32**: `0x5b054e14`
* **Contents**:
  ```ini
  NUMBER = SLUS-21448
  VERSION = 100
  VMODE = NTSC
  COUNTRY = AMERICA
  LANGUAGE = ENGLISH
  ```

#### `IOPCONF.CNF` (323 bytes, LBA 267)
* **SHA-256**: `699d70c00ffc5afe9ebd4df116d20df4b3a3d88aaf1dd0317bc35edae43eea38`
* **CRC32**: `0x98aeae49`
* **Contents**:
  ```ini
  IOPRP = cdrom0:\MODULES\IOPRP300.IMG;1
  MODULES = cdrom0:\MODULES\SIO2MAN.IRX;1
  MODULES = cdrom0:\MODULES\SIO2D.IRX;1
  MODULES = cdrom0:\MODULES\DBCMAN.IRX;1
  MODULES = cdrom0:\MODULES\PAD2\DS1O_D.IRX;1
  MODULES = cdrom0:\MODULES\MCMAN.IRX;1
  MODULES = cdrom0:\MODULES\MCSERV.IRX;1
  MODULES = cdrom0:\MODULES\LIBSD.IRX;1
  MODULES = cdrom0:\MODULES\RXSNDDRV.IRX;1
  ```

---

## 5. Primary Executable (`SLUS_214.48`) & IOP Module Inventory

### 5.1 Primary EE Executable (`SLUS_214.48`)
* **ISO Path**: `/SLUS_214.48;1` (LBA 269)
* **Size**: `2,296,472` bytes
* **SHA-256**: `262efe713ad2432d4e8b2122a5edae9302b7f9eb900537b76beae064a4a91af3`
* **SHA-1**: `f9abd6dc53070750dfcae3b44184fb9852e603fb`
* **CRC32**: `0x8cf7b024`
* **ELF Type**: `ELF32`, Little-Endian, `ET_EXEC`, `EM_MIPS` (MIPS R3000/R5900), Flags `0x20924001` (`noreorder, 5900, eabi64, mips3`)
* **Entry Point**: `0x00100008`
* **Program Headers (2 `PT_LOAD` segments)**:
  * `LOAD[0]`: Offset `0x00001000`, VirtAddr `0x00100000`, PhysAddr `0x00100000`, FileSiz `0x00195eb8` (`1,662,648` B), MemSiz `0x00195ed0` (`1,662,672` B), Flags `R E`, Align `0x1000`
  * `LOAD[1]`: Offset `0x00196f00`, VirtAddr `0x00295f00`, PhysAddr `0x00295f00`, FileSiz `0x000720fc` (`467,196` B), MemSiz `0x00592f94` (`5,844,884` B), Flags `RW`, Align `0x1000`
* **Highest Loaded Guest Address (`.bss` end)**: `0x00828e94` (~8.16 MiB into the 32 MiB EE RDRAM; `PS2Runtime::loadELF` sets `m_guestHeapBase = 0x00829ea0`, leaving ~22.8 MiB of guest heap below `0x01f00000`).

### 5.2 Complete Executable & IOP Binary Checksum Table

| Disc Path | Size (Bytes) | CRC32 | SHA-256 | Role |
| :--- | ---: | :--- | :--- | :--- |
| `/SLUS_214.48;1` | `2,296,472` | `0x8cf7b024` | `262efe713ad2432d4e8b2122a5edae9302b7f9eb900537b76beae064a4a91af3` | Main EE R5900 game executable |
| `/MODULES/IOPRP300.IMG;1` | `275,344` | `0x59d29521` | `8dbdc3edffbaa8ffba1fdbbe5dc9aa2ca5fa2df9a409a86fd7dfcb9d0e89eb8c` | Sony SDK 3.0.0 IOP ROM replacement image |
| `/MODULES/SIO2MAN.IRX;1` | `6,641` | `0xf6dc2b6c` | `1a27136fb8d524e6292a7fb22603ae34dd7f207670cf0a4c714bc1c8db2fa153` | Serial I/O 2 Manager (`sio2man` v2.4) |
| `/MODULES/SIO2D.IRX;1` | `11,289` | `0x6c42deaa` | `848f1fa4296ab4e94fdcc9c2bd08fa7da526bd78cb907f022b9ca0c05bf3cf37` | SIO2 Driver for `libpad2`/`dbcman` (`sio2d` v2.3) |
| `/MODULES/DBCMAN.IRX;1` | `15,653` | `0x56a360d4` | `84220969db15d0377d70ca80183a0d1920e07d5762e6ffaa21a4ab112a6b6e0d` | Device Bus Controller Manager (`dbcman` v1.2, SID `0x80001300`) |
| `/MODULES/PAD2/DS1O_D.IRX;1` | `10,469` | `0x1603284f` | `8ef59ca21737cb11d9db53200bb1fd29e04de4d4d3fbcb193c984c04da8c9581` | DualShock (`libpad2`) DBC driver |
| `/MODULES/PAD2/DS2O_D.IRX;1` | `11,593` | `0x89d6044a` | `c852d3c09fa45701cb4be4056e57b5b49b179cc09b29a1eb3067a5489477c8ef` | DualShock 2 (`libpad2`) DBC driver |
| `/MODULES/PAD2/DS2U_D.IRX;1` | `12,181` | `0xf799482e` | `18c5dc6c5e0708b8a427f06064b0d9c8044e65aa322ef9433ffeb582da7fb5e4` | DualShock 2 USB/ext (`libpad2`) DBC driver |
| `/MODULES/MCMAN.IRX;1` | `96,181` | `0x19d0cd1e` | `d1cdbf5e4be93cf383bd44ca64a37951c482475a6f3bd28ff8fb3b897121139c` | Memory Card Manager (`mcman` v2.7) |
| `/MODULES/MCSERV.IRX;1` | `7,385` | `0x952b20c8` | `6ba43393e3f9ff6e0db2f3ba2fa27bc49f35ca3bfbd7e4ab7a42c5c8e3dc2061` | Memory Card RPC Server (`mcserv` v2.1, SID `0x80000400`) |
| `/MODULES/LIBSD.IRX;1` | `30,085` | `0xc0722959` | `d00060ef180ef2381c749d20389f9ef75d9a544348df4bc9ff97954f6c09d6e4` | Sound Driver Low-Level SPU2 Library (`libsd` v1.5, SID `0x80000701`) |
| `/MODULES/RXSNDDRV.IRX;1` | `74,005` | `0xb22c4a64` | `c7eb6f8be36b700e893f81020cf9da41ab002e235c3d3f4ba450dd0c61ab11f3` | Custom Sony/Punchline Sound Driver (`rxsnddrv`) |
| `/MODULES/CDVDSTM.IRX;1` | `34,073` | `0xf0ab4f2c` | `1d8c6a6cb9bf3822dc38922f184f2b82a452cc2112a6c5560e49e08d6c75bf84` | CD/DVD Streaming Module |

### 5.3 Full ISO Directory & Asset Summary (`2,650` Files Across `21` Directories)

| Directory | File Count | Total Bytes | Primary File Extensions & Purpose |
| :--- | ---: | ---: | :--- |
| `/` (root) | `4` | `2,297,028` | `SLUS_214.48`, `SYSTEM.CNF`, `SYSTEM.INI`, `IOPCONF.CNF` |
| `/MODULES` & `/MODULES/PAD2` | `12` | `584,899` | `IOPRP300.IMG`, `*.IRX` IOP modules |
| `/MOVIE` | `41` | `2,338,164,776` | `*.PSS` (`2.18 GiB`, MPEG-2 Program Stream video + ADS/SS2 ADPCM audio) |
| `/DATA/SND/XWS` | `844` | `586,287,104` | `*.STR` (`559.1 MiB`, raw headerless 48 kHz PS-ADPCM mono `S0*.STR` & stereo `S1*.STR` streams) |
| `/DATA/SND/XV` | `36` | `9,613,056` | `*.SE` (`9.17 MiB`, `XVAB` headered SPU2 ADPCM sound-effect banks) |
| `/DATA/CHAR` | `299` | `94,160,640` | `*.RPK` (`RTPK` archives containing character meshes, skeletons, textures) |
| `/DATA/CUT` | `264` | `122,953,984` | `*.RPK` (`RTPK` cutscene animation/camera/asset packages) |
| `/DATA/BG/ STAGE01..12` | `562` | `191,833,216` | `MAPUNIT.BIN`, `*.ARA` (`AREA`), `*.RPK` (`RTPK` stage geometry/textures/collision) |
| `/DATA/EVT` | `223` | `23,310,336` | `*.RPK` (`RTPK` event packages encapsulating `ELFR101` scripts and event assets) |
| `/DATA/MENU` | `262` | `16,590,848` | `*.RPK` (`RTPK` 2D UI, fonts, inventory, save/load menu graphics) |
| `/DATA/LIMIT` | `88` | `4,268,032` | `*.RPK` (`RTPK` limited/room-specific asset packages) |
| `/DATA/EFFECT` | `15` | `358,400` | `*.RPK` (`RTPK` particle/visual effect packages) |
| **Total** | **`2,650`** | **`3,390,422,323`** | **No secondary `.ELF`, `.OVL`, or `.REL` EE code overlays exist anywhere on disc.** |
