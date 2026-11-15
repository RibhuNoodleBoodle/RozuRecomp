================================================================================
GEMINI FLASH (HIGH REASONING) — EXECUTION PROTOCOL & WORK ORDER INDEX
Project: Rule of Rose (PS2, SLUS-21448) Static Recompilation on ran-j/PS2Recomp
Repository: /mnt/6421-8598/building/RozuRecomp
Architect: Gemini Argon (High Reasoning)
Worker: Gemini Flash (High Reasoning)
================================================================================

1. PURPOSE OF THIS DIRECTORY
----------------------------
Each file in `gemini_flash/` is a self-contained, paste-ready execution prompt
designed for a fresh Gemini Flash (High Reasoning) session with ZERO prior chat
memory. You must execute them in strict numerical order (`Step_00` -> `Step_12`).

2. CRITICAL HOST ENVIRONMENT RULES (READ BEFORE EVERY SESSION)
--------------------------------------------------------------
- Root Disk (`/`, `/dev/sdb3`) has ONLY ~1.1 GiB free (99% full).
- Workspace Disk (`/mnt/6421-8598`, `/dev/sda2`) has ~245 GiB free.
- Host RAM is 15 GiB (`~9.8 GiB` available) with **0 Bytes of Swap (`Swap: 0B`)**.
- Therefore, in EVERY shell command you run, you MUST:
  1) Export `TMPDIR=/mnt/6421-8598/building/RozuRecomp/out/tmp` (after `mkdir -p`).
  2) Place ALL build, extraction, dependency, and test outputs inside
     `/mnt/6421-8598/building/RozuRecomp/out/`.
  3) Cap parallel C++ compilation at `ninja -j2` to prevent Linux OOM kills.
  4) NEVER stage or commit `Rule of Rose (USA).iso`, `SLUS_214.48`, `*.IRX`,
     `*.IMG`, `*.RPK`, `*.PSS`, `*.STR`, or anything under `out/`.
  5) **WRITE `handoff.txt` AFTER EVERY MAJOR MILESTONE (MANDATORY)**:
     At the end of EVERY milestone (`M00` through `M12`) and after any recovery
     session, you MUST write/update `/mnt/6421-8598/building/RozuRecomp/handoff.txt`
     with:
     - The completed milestone ID (`MXX = DONE`) and its exact 40-char commit SHA
       (`git rev-parse HEAD`).
     - Exact commands executed, test counts, frame/audio/heap/RSS metrics, and
       files changed.
     - The exact next milestone prompt file to run.
     - Then commit `handoff.txt` (`docs(handoff): update ledger after MXX`) so
       both disk and Git history always have the latest `handoff.txt`.

3. SEQUENTIAL WORK ORDER TABLE
------------------------------
- `Gemini_Step_00_Inventory_And_Baseline.txt` (Milestone M00):
  Harden `.gitignore`, extract `Rule of Rose (USA).iso` into `out/disc/`, and
  verify SHA-256/CRC32 of `SLUS_214.48` and IOP modules.
- `Gemini_Step_01_Upstream_Toolchain_And_Tests.txt` (Milestone M01):
  Configure and build upstream `ps2xAnalyzer`, `ps2xRecomp`, `ps2xIOP`,
  `ps2xRuntime`, and `ps2xTest` (`-DPS2X_ENABLE_FFMPEG=OFF`) and pass 100% of
  `ctest`.
- `Gemini_Step_02_Ghidra_And_Function_Map.txt` (Milestone M02):
  Exclude `.vutext` (`[0x00291230, 0x002953B0)`) from R5900 code scanning and
  generate `config/slus_21448.toml` (`~8,963` verified function boundaries from
  `.gnu.linkonce.t.*`, `.gnu.linkonce.d._vt$*`, SDK signatures, and `.text`).
- `Gemini_Step_03_Static_Recompilation_Integration.txt` (Milestone M03):
  Run `ps2xRecomp` on `config/slus_21448.toml`, organize generated C++ into
  32-64 unity batch translation units, and compile/link `RozuRunner`.
- `Gemini_Step_04_Runtime_Boot_And_Dispatch.txt` (Milestone M04):
  Register `SLUS_214.48` (`CRC32 0x8cf7b024`) game overrides, wire `T0_COUNT`
  (`0x10000000`) and `sceGsSyncVCallback`, and boot through `.ctors` into
  `MagSystem::run` (`0x00117FC8`).
- `Gemini_Step_05_IOP_IRX_CDVD_And_RPC.txt` (Milestone M05):
  Support `bedInitSystem` (`0x001005E0`) loading `IOPCONF.CNF`, `IOPRP300.IMG`,
  and all 8 `.IRX` modules, plus case-insensitive CDVD/VFS path resolution.
- `Gemini_Step_06_GS_VU_Graphics.txt` (Milestone M06):
  Enable VIF1/GIF DMA sync, `.vutext` 44 `.DVP.overlay` VU1 microprogram
  uploads, and `512x448` / `512x384` GS rendering through boot logos and title.
- `Gemini_Step_07_Movies_And_Audio.txt` (Milestone M07):
  Enable `MOVIE/*.PSS` MPEG-2 playback (staging FFmpeg headers in `out/deps/`)
  and `LIBSD.IRX` + `RXSNDDRV.IRX` audio streaming (`DATA/SND/XWS/*.STR`).
- `Gemini_Step_08_Input_Menu_And_Saves.txt` (Milestone M08):
  Implement `libpad2` / `libdbc` / `libvib` HLE handlers (`scePad2CreateSocket`,
  `scePad2Read`, `scePad2GetState`, `sceDbcInit`) for `BedPad` (`0x00101AEC`)
  and verify `mc0` save/load (`BASLUS-21448*`).
- `Gemini_Step_09_First_Playable_Gameplay.txt` (Milestone M09):
  Start a New Game, execute `ELFR101` scripts via `CSequenceCode::update`
  (`0x001AE7C8`), and reach interactive 3D gameplay in `STAGE01`.
- `Gemini_Step_10_Sustained_Gameplay_Testing.txt` (Milestone M10):
  Run a 30-minute continuous gameplay soak test across room transitions, menus,
  Brown companion AI, combat, and save/load.
- `Gemini_Step_11_Intel_HD620_Optimization.txt` (Milestone M11):
  Gate `UploadFrame()` to 30 Hz guest buffer swaps, SIMD-optimize `GSCpuBackend`,
  and benchmark `<= 33.4 ms` median frame time on Intel HD Graphics 620.
- `Gemini_Step_12_Packaging_And_Regression.txt` (Milestone M12):
  Run the full `ctest` + `RozuRunner` regression suite, audit Git cleanliness,
  and finalize `handoff.txt`.
- `Gemini_Recovery_And_Debugging.txt`:
  Emergency recovery playbooks for OOM kills, `/` disk exhaustion, missing
  guest function targets (`[guest-branch:missing-target]`), VSync/DMA hangs,
  and IOP RPC deadlocks.
================================================================================
