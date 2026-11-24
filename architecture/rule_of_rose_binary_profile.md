# Phase B — Rule of Rose (`SLUS-21448`) Disc & Binary Profile

**Inspection Date:** 2026-11-24  
**Source Media:** Locally supplied `Game/Rule of Rose (USA).iso` (git-ignored; inspected read-only in memory without extracting proprietary binaries into tracked directories).

---

## 1. Verified Disc Identity

| Property | Value | Provenance |
|---|---|---|
| Local file | `Game/Rule of Rose (USA).iso` (git-ignored) | Local filesystem (`stat`, `ls -lh`) |
| Title / Publisher | Rule of Rose / `ATLUS USA INC.` | ISO9660 PVD (`isoinfo -d`, `Tools/iso9660.py info`) |
| Serial / Region / Revision | **`SLUS-21448`** / USA (NTSC-U) / **`1.00`** | `SYSTEM.CNF` (`BOOT2 = cdrom0:\SLUS_214.48;1`, `VER = 1.00`, `VMODE = NTSC`) & `SYSTEM.INI` (`NUMBER = SLUS-21448`, `VERSION = 100`, `COUNTRY = AMERICA`, `LANGUAGE = ENGLISH`) |
| Sector Format & Size | 2048-byte-sector ISO9660 (DVD-5), **1,656,960 sectors**, **3,393,454,080 bytes** | `isoinfo -d`, `stat -c '%s'` |
| Volume Creation Date | `2006-07-27 23:26:19` | `Tools/iso9660.py info` |
| **MD5** | **`54e6990f5ed6e0d5b03b6ca7655b7cec`** | `md5sum` — **EXACT MATCH** to Redump entry for *Rule of Rose (USA)* |
| **SHA-256** | **`95ff5d1298b1bb19443098852c95c42886605f01fb1ffa8d823ff496598989e9`** | `sha256sum` |
| PCSX2 Game CRC | `F3FD313E` (candidate from public PCSX2 patch DB; verify locally when PCSX2 is available) | INFERRED (web search; unverified on local PCSX2) |

---

## 2. Disc Filesystem Inventory

Total ISO9660 paths: **3,313** (`DATA`: 3,250; `MOVIE`: 42; `MODULES`: 17; root files: 4).

### 2.1 Root Files & Verified SHA-256 Hashes

| LBA | Size (bytes) | Path | SHA-256 | Role |
|---:|---:|---|---|---|
| 1645590 | 323 | `/IOPCONF.CNF;1` | `699d70c00ffc5afe9ebd4df116d20df4b3a3d88aaf1dd0317bc35edae43eea38` | IOP boot module load list |
| 1645591 | 57 | `/SYSTEM.CNF;1` | `93843e865293ca2e06bd849262db9a724615bd16c9628bcaebdf6c14cf7baee1` | PS2 boot descriptor (`SLUS_214.48`, NTSC) |
| 1645592 | 176 | `/SYSTEM.INI;1` | `7f1f312a02cfb6245e9d51937138a199c75c59c33016c1b869d56071da02f41c` | Game system config (`SLUS-21448`, `ENGLISH`, `MODE = 0`) |
| 1645593 | 2,296,472 | `/SLUS_214.48;1` | `262efe713ad2432d4e8b2122a5edae9302b7f9eb900537b76beae064a4a91af3` | Monolithic EE game executable (ELF32 MIPS R5900) |

*(Additional hashes for `SLUS_214.48`: SHA-1 `f9abd6dc53070750dfcae3b44184fb9852e603fb`, MD5 `0f3875fc3cf349a4a7e52861223df46f`.)*

### 2.2 `/DATA/` Archive & Streaming Structure

Extensions across 3,250 `/DATA/` entries: `.ARA` (1,134), `.STR` (844), `.RPK` (49), `.SE` (36), `.WRD` (15), `.BIN` (6), `.GRB` (1), plus directories.
- **No ELF, IRX, OVL, PRX, XFF, or REL binaries exist anywhere inside `/DATA/`.**
- Verified magic headers of all 6 `/DATA/**/*.BIN` files:
  - `/DATA/BG/MAPUNIT.BIN` (603,231,264 B): magic `5254504b` (`"RTPK"`) — room/background geometry pack.
  - `/DATA/EFF/EFF.BIN` (812,288 B): magic `5254504b` (`"RTPK"`) — visual effects pack.
  - `/DATA/WRD/WRD.BIN` (270,131 B): magic `5254504b` (`"RTPK"`) — word/script table pack.
  - `/DATA/CMNTEX/LOADING.BIN` (66,784 B): loading screen texture data.
  - `/DATA/SND/XV/G000_TBL.BIN` (56,784 B): sound-effect table (starts with `"cursor_move\0..."`).
  - `/DATA/SND/XWS/STR_TBL.BIN` (47,328 B): streamed audio table (starts with `"M00\0..."`).
- Key disc paths referenced in `SLUS_214.48` strings: `cdrom0:\DATA\CMNTEX\LOADING.BIN`, `data/PREMIERE.RPK`, `data/ch/CHARA.RPK`, `data/ch/00..12/CHAP00..12.RPK`, `data/bg/mapunit.bin`, `data/%s/W%03d/A%03d/A%03d.ARA`, `data/%s/w%03d/door_obj.bin`, `data/%s/w%03d/jump_pos_tbl.bin`.
- **Implication:** Asset formats do NOT require extraction or conversion for native execution; the game reads them directly from the mounted ISO via `cdrom0:` (`PS2CdImage` + `sceCd*`/`fio`).

### 2.3 `/MOVIE/` FMV Inventory (CRITICAL DIFFERENCE FROM SOTC)

- **41 `.PSS` files** totaling **1,564,229,796 bytes (1,491.8 MiB)** — nearly half the disc!
- Includes boot/logo (`CP_LOGO.PSS`, 5.19 MB), title/chapter title cards (`MV01_TIT.PSS`..`MV11_TIT.PSS`), opening/ending movies (`MV01_OPE.PSS`, `MV00_AD.PSS`, `MV00_ED.PSS`, `MV00_GD.PSS`, `MV00_GED.PSS`), death movie (`DEATH_J.PSS`), and major story cutscenes.
- Verified MPEG-2 Program Stream (`00 00 01 E0` video packets, `00 00 01 B5` MPEG-2 extensions, slice start codes `0x00..0x11`) in both `CP_LOGO.PSS` and `MV01_TIT.PSS`.
- `SLUS_214.48` embeds `libmpeg 3000` and `libipu 3000` (`"_sceMpegSliceA0(): error happens"`, `"Need to re-setup libipu since sceMpegGetPicture was aborted"`, `"[MPEG ERROR]%s"`).

---

## 3. Boot ELF (`SLUS_214.48`) Structure & Code Profile

### 3.1 ELF Header & Program Headers (VERIFIED)

- **Format:** ELF32 Little-Endian, `ET_EXEC` (`Type=2`), `EM_MIPS` (`Machine=8`), `e_flags = 0x20924001` (MIPS R5900, EABI64 `.mdebug.eabi64`).
- **Entry Point:** **`0x00100008`** (`0x00100000..0x00100007` are two `NOP` words; `0x00100008` begins Sony `crt0` register-zeroing `lq/por` sequence `70000C28`...).
- **Global Pointer (`_gp`):** **`0x0030FFF0`** (from `.reginfo` `ri_gp_value`).
- **Symbol & Relocation Tables:** `has_symtab = False`, `has_rel = False` (stripped static executable, **no EE relocations**).
- **Program Headers (2 `PT_LOAD` segments):**
  - `PT_LOAD[0]`: `off=0x001000`, `vaddr=0x00100000`, `filesz=0x195EB8`, `memsz=0x195ED0`, `R-X`
  - `PT_LOAD[1]`: `off=0x196F00`, `vaddr=0x00295F00`, `filesz=0x0720FC`, `memsz=0x592F94`, `RW-` (RAM image spans `0x00100000 .. 0x00828E94`, ~7.16 MB of the 32 MB EE RDRAM).

### 3.2 Section Map (1,795 Sections Total — VERIFIED)

| Section(s) | Count | Address Range | Size | Flags | Notes |
|---|---:|---|---:|---|---|
| `.text` | 1 | `0x00100000 .. 0x00280E88` | `0x180E88` (1,576,584 B) | `AX` | Main EE R5900 code (crt0, game, `i3d` engine, sound/movie mgr, Sony SDK, newlib, libgcc) |
| `.gnu.linkonce.t.*` | **1,449** | `0x00280E88 .. 0x00295EB8` (split around `.vutext`) | `0x10E60` (69,216 B) | `AX` | **Exact GCC 2.96 mangled C++ function names** (`DogEntity`, `DogActor`, `MagLife*`, `Tsk*`, `Eff0`, `mnuBase`, `EmyManager`, `PLScenePlay`, etc.) |
| **`.vutext`** | 1 | **`0x00291230 .. 0x002953B0`** | `0x4180` (16,768 B) | `AX` | **VU1/VU0 microcode + VIF DMA packets (44 VIF `MPG` commands). NOT R5900 EE code! MUST be excluded from EE recompilation!** |
| `.reginfo` | 1 | `0x00295EB8 .. 0x00295ED0` | `0x18` | `A` | `_gp = 0x0030FFF0` |
| `.data` | 1 | `0x00295F00 .. 0x002E014C` | `0x4A24C` | `AW` | Initialized globals & tables |
| `.ctors` / `.dtors` | 2 | `0x002E014C .. 0x002E0178` | `0x18` / `0x14` | `AW` | Global C++ constructors/destructors |
| `.eh_frame` | 1 | `0x002E0178 .. 0x002E0A7C` | `0x904` | `AW` | Exception frame table |
| `.gnu.linkonce.d.*` | **284** | `0x002E0A80 .. 0x002E52D0` | `0x4850` (18,512 B) | `AW` | **Exact C++ vtables (`_vt$8DogActor`, `_vt$9MagLifePC`, etc.)** — high-confidence source of indirect-call (`jalr`) virtual method targets! |
| `.rodata` | 1 | `0x002E5300 .. 0x00307F70` | `0x22C70` | `A` | Strings, float constants, jump tables |
| `.gcc_except_table` | 1 | `0x00307F80 .. 0x00307FFC` | `0x7C` | `AW` | Minimal exception table |
| `.sbss` / `.bss` | 2 | `0x00308000 .. 0x00828E94` | `0xBC` / `0x520D94` | `AW` | Zero-initialized RAM (~5.13 MB) |
| `.DVP.ovlytab` / `.DVP.ovlystrtab` / `.DVP.overlay.*` | 46 | Non-allocated (`addr=0`) | `0x4756` | — | **44 VU microcode overlay debug/metadata sections** matching the 44 `MPG` packets in `.vutext`. |

### 3.3 R5900 Instruction & Control-Flow Profile (VERIFIED)

Scanned across all executable sections (419,696 32-bit words, note ~4,192 words are `.vutext` and will be excluded):
- **`jal` calls:** 24,832 sites -> **4,025 unique targets** (`0x00100248 .. 0x00295918`). **ZERO out-of-range `jal` targets!** Every direct call lands inside `SLUS_214.48`'s static code range.
- **`j` jumps:** 1,311 sites -> 645 unique targets.
- **`jalr` indirect calls:** **558 sites** (heavily C++ virtual calls via the 284 `.gnu.linkonce.d.*` vtables, plus callbacks).
- **`jr` non-`$ra` (switch jump tables / tail indirect jumps):** 297 sites.
- **`jr $ra` returns:** 8,860 sites.
- **COP1 (FPU):** 16,632 instructions.
- **COP2 (VU0 macro mode):** 1,614 instructions + 841 `lqc2`/`sqc2`.
- **MMI (128-bit SIMD):** 630 instructions + 1,402 `lq`/`sq`.
- **COP0:** 263 instructions; **`cache`:** 17; **`pref`:** 16; **`sync`:** 509.
- **Syscalls:** 179 sites covering **146 distinct syscall numbers** (standard Sony `libkernl 3000` positive and negative interrupt-context syscalls `0x0000..0x00FD` and `-255..-26`, plus 11 dynamic/wrapper sites).
- **Dynamic EE Code / Overlays Verdict:** **NONE DETECTED.** `LoadExecPS2:%s` string appears only as standard Sony SDK `libkernl` boilerplate (no secondary ELF files exist on the disc). All EE code resides statically in `SLUS_214.48`.

### 3.4 Embedded SCE SDK & Middleware Stamps (VERIFIED)

- Sony EE SDK 3.0x: `libkernl 3000` (inferred from syscalls + IOPRP300), `libcdvd 3000`, `libmc 3020`, `libmpeg 3000`, `libdma 3000`, `libvu0 3000`, `libipu 3000`, `libdbc 3020`, `libpad2 3020`, `libvib 3000`, `libscf 3000`.
- Graphics / Engine Middleware: **`i3d_package_version 050121-stable-050826`** (`I3D_BIN`, `I3D_I3C`, `I3D_I3M`, `I3rRoot__CheckIdString`).
- Audio Engine: **`rxsnd` / `rxsndut` / `RXSNDDRV.IRX`** (`XVAB` sound banks, `XSEQ` MIDI/HEAD sequences, SPU heap allocator, double-buffer streaming thread, RPC server).
- Memory Card Save Paths: `/BASLUS-21448`, `/BASLUS-21448/BASLUS-21448`, `/BASLUS-21448/icon.sys`, `slime1.ico`..`slime3.ico`.

---

## 4. IOP Modules (`IOPCONF.CNF` & `/MODULES/`) — EXTRAORDINARY COMPATIBILITY FINDING

`IOPCONF.CNF` loads **9 files** in exact order:
1. `modules/ioprp300.img`
2. `modules/sio2man.irx`
3. `modules/sio2d.irx`
4. `modules/dbcman.irx`
5. `modules/pad2/ds1o_d.irx`
6. `modules/mcman.irx`
7. `modules/mcserv.irx`
8. `modules/libsd.irx`
9. `modules/rxsnddrv.irx`

### 4.1 Byte-for-Byte Match with `sotc-vibe-pc` (VERIFIED BY FULL SHA-256)

| Rule of Rose File | Size (B) | Verified SHA-256 | Match vs `sotc-vibe-pc` (`Docs/GAME_BUILD.md:71-80`) |
|---|---:|---|---|
| `/MODULES/IOPRP300.IMG` | 275,345 | `02d314464c17c715d7e809297b0aba184173a98616b1fafeac27fe33fc480c82` | **IDENTICAL** |
| `/MODULES/SIO2MAN.IRX` | 6,641 | `565ec77e75f174cfddf72c41ccc446c1c07a3d5fb0a2ccfefad337cb8a7d0728` | **IDENTICAL** |
| `/MODULES/SIO2D.IRX` | 11,289 | `b07339d0b6ef6021ebb2bd8dba1138f3159b2cdfbf1b29df799694107107d330` | **IDENTICAL** |
| `/MODULES/DBCMAN.IRX` | 15,653 | `60bfea7d0877df3af370676666e5f1043b6e71723fab94cdff790c19e75e12e7` | **IDENTICAL** |
| `/MODULES/PAD2/DS1O_D.IRX` | 10,469 | `ba65aefc36ef49fc2c31b979aef628cf304561c421b817d3734aee066082937c` | **IDENTICAL** |
| `/MODULES/MCMAN.IRX` | 96,181 | `b4df4061f8fdc9c7cf06a329b96227ad6ca69d008df475c1fc4d3e8d06fe3fa4` | **IDENTICAL** (present on SOTC disc; SOTC used `MC2_D` at runtime) |
| `/MODULES/MCSERV.IRX` | 7,385 | `5006b0dd650fa416d03a559bc8e3bae8a7ae95be81f3e4f3fd9bd524fa27e000` | **IDENTICAL** (`ps2xIOP/src/modules/mcserv.cpp` exists in `PS2Recomp`) |
| `/MODULES/LIBSD.IRX` | 30,085 | `94915a3d9673e8a370e144ae493552d5e1f3956bb9ae5bd91e2da5f36c83ce7d` | **IDENTICAL** |
| `/MODULES/RXSNDDRV.IRX` | 74,005 | `64d6f26c796fc2599b4fffee94744288d2603cf376041a9f8b25dc538aea67fc` | **RULE OF ROSE SPECIFIC** (`Sound driver version 1.00`, v1.01) |

*(Unused/auxiliary IRX modules also on disc: `IOPRP270.IMG`, `PADMAN.IRX`, `DS1O_S1.IRX`, `DS2O_S1.IRX`, `SNDBGEXT.IRX`, `USBD.IRX`.)*

### 4.2 `RXSNDDRV.IRX` Import Audit (VERIFIED)

- `libsd` v1.05: **15 ordinals `[4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 18, 20, 23, 26]`** — strictly a subset of the `libsd` ordinals `4..26` already proven by `SG2IOPM1.IRX` in `sotc-vibe-pc`!
- Kernel imports: `sysmem(4..8)`, `intrman(17,18)`, `loadcore(5)`, `sifcmd(14,17,19,22,23)`, `sifman(7,8)`, `stdio(4)`, `sysclib(14)`, `thbase(4,6,20)`, `thevent(4,6,7,10)`, `vblank(5)`.
- Uses SPU2 DMA + double-buffered streaming + `XVAB`/`XSEQ` RPC server. Watch for potential **AutoDMA PCM** usage during `.STR` music/voice streaming (a known `IopSpu2` fidelity gap in `Docs/ARCHITECTURE.md:196-197` — must be tested directly in M05–M07!).

---

## 5. External Reference Audit (`notmanrivera/ruleofrose-decomp`)

| Fact | Status | License / Provenance Constraint |
|---|---|---|
| Targets exact same `SLUS_214.48` (NTSC-U) | VERIFIED (README) | No `LICENSE` file in repo -> **DO NOT copy code/tables.** |
| Confirms static monolithic ELF (no EE overlays), compiled with `ee-gcc 2.96 -Os -G0 -fno-exceptions -fno-strict-aliasing` | VERIFIED (README) + matches our ELF audit | Independent conceptual cross-check only. |
| Reports 7,230–8,963 total functions, 1,449 `.gnu.linkonce` exact names, 284 vtables, ~648 SDK/libc/libgcc functions identified using **PS2Recomp's own GPL signature database** | VERIFIED (README matches our exact 1,449 `.gnu.linkonce.t.*` & 284 `.gnu.linkonce.d.*` counts!) | Confirms our `External/PS2Recomp/ps2xAnalyzer` GPL signature DB is sufficient to recover SCE SDK names cleanly without using `ruleofrose-decomp`! |

---

## 6. Provenance Table

| Fact | Evidence / Path or Command | Confidence | Impact | Next Verification |
|---|---|---|---|---|
| Disc is exact Redump `SLUS-21448` v1.00 NTSC-U | `md5sum`, `sha256sum`, `isoinfo -d`, `SYSTEM.CNF`, `SYSTEM.INI` | **VERIFIED** | Locks exact target build and hash checks | Implement `Port/profile/SLUS-21448_v1.00.json` in M02 |
| `SLUS_214.48` is monolithic static `ET_EXEC` (`0x100000..0x828E94`), entry `0x00100008`, `_gp=0x0030FFF0`, zero EE relocations | In-memory Python ELF parser on `/SLUS_214.48;1` | **VERIFIED** | Eliminates entire XFF linker & 26,981 runtime relocation machinery | Confirm `ps2_recomp` parses & emits clean C++ in M03/M04 |
| `.vutext` (`0x00291230..0x002953B0`) has `SHF_EXECINSTR` but contains 44 VU microcode `MPG` packets | Section headers + `.DVP.ovlystrtab` + VIF `0x4A` scan | **VERIFIED** | Prevents catastrophic EE disassembly of VU microcode | Explicitly exclude `.vutext` in `Tools/ror_prepare.py` (M03) |
| 1,449 `.gnu.linkonce.t.*` + 284 `.gnu.linkonce.d.*` vtables + 4,025 unique `jal` targets | In-memory Python ELF scan | **VERIFIED** | Enables complete function discovery + indirect-call coverage | Run `Tools/ror_prepare.py` + `ps2xAnalyzer` in M03; verify 0 missing targets at runtime |
| 8 of 9 IOP modules are byte-identical to SOTC; `RXSNDDRV.IRX` imports only `libsd` 4–26 + standard IOP kernel | Full SHA-256 + IRX import parser | **VERIFIED** | Huge de-risking of IOP/pad/audio bring-up | Boot `IOPCONF.CNF` modules on `ps2xIOP` in M05 |
| 41 `.PSS` MPEG-2 FMV files (1.49 GiB) + `libmpeg`/`libipu` strings | `isoinfo -l`, MPEG start-code scan, ELF strings | **VERIFIED** | FMV playback is mandatory (starts with `CP_LOGO.PSS` at boot!) | Audit & test `PS2X_ENABLE_FFMPEG=ON` + `Stubs/MPEG.cpp` + `Stubs/IPU.cpp` in M05/M06 |
| `MCMAN.IRX` + `MCSERV.IRX` (`libmc 3020`) used for `/BASLUS-21448` saves | `IOPCONF.CNF`, ELF strings (`libmc: too old release...`) | **VERIFIED** | Differs from SOTC's `MC2_D.IRX` (`libmc2`) | Test `MCMAN`/`MCSERV` on `ps2xIOP` + `iop_memcard` in M05/M10 |
| `RXSNDDRV.IRX` AutoDMA PCM streaming usage | Strings mention double-buffer thread & `.STR` tables | **INFERRED** | `IopSpu2` AutoDMA PCM is a known fidelity gap (`Docs/ARCHITECTURE.md:196`) | Trace `libsd` calls (`sceSdVoiceTrans` vs `sceSdBlockTrans`) during M06/M07 |
| PCSX2 GameIndex quirks / FPU round mode for `SLUS-21448` | Web search (PCSX2 CRC `F3FD313E`, no local PCSX2 installed) | **UNKNOWN / INFERRED** | May need EE chop/round-to-zero or VU clamp mode | Verify against official PCSX2 `GameIndex.yaml` + local PCSX2 oracle when available |

---

## 7. Hard Feasibility Gate Evaluation

**Verdict: FEASIBLE TO PROCEED TO M00–M04 PROOF-OF-CONCEPT — NO FATAL ARCHITECTURAL BLOCKER FOUND.**

Why this passes the Hard Feasibility Gate:
1. **Static EE Control Flow is Clean:** Unlike SOTC (which required reverse-engineering a proprietary XFF2 dynamic linker and runtime code patching), Rule of Rose's `SLUS_214.48` is a single static `ET_EXEC` ELF with zero dynamic EE overlays, zero runtime code relocations, 0 out-of-range `jal` targets, 1,449 named `.gnu.linkonce.t.*` sections, and 284 named vtables.
2. **SDK Symbol Discovery Has a Clean GPL Path:** `External/PS2Recomp/ps2xAnalyzer` already ships a GPL-3.0 Sony SDK signature database that covers Sony SDK 3.0x (`libkernl`, `libcdvd`, `libmc`, `libmpeg`, `libipu`, `libpad2`, `libdbc`, `libvib`, `libdma`, `libvu0`).
3. **IOP Stack is Already Proven:** 8 of 9 `IOPCONF.CNF` modules are byte-identical to SOTC's proven `ps2xIOP` stack, and the 9th (`RXSNDDRV.IRX`) imports only already-supported `libsd` and IOP kernel ordinals.
4. **Falsifiable Minimum Viable Proof (M04 -> M05):**
   - **M03/M04 Proof:** Generate `rozu_functions.csv` + `slus_21448_annotated.elf`, run `ps2_recomp` on `SLUS_214.48` (first a tiny isolated subset test of real `SLUS_214.48` functions, then full ELF recompilation with 0 decode failures), compile and execute a real recompiled `SLUS_214.48` routine in a host unit test.
   - **M05 Proof:** Boot the real `SLUS_214.48` entry point `0x00100008` inside `rozu` runtime, advance past `crt0` + `main()` + `IOPCONF.CNF` loading + first `cdrom0:` reads, and produce deterministic execution logs without hitting unmapped indirect branches.
