# 01 — Comprehensive Validation & Anti-Cheating Test Plan

## 1. Non-Negotiable Anti-Cheating & Honesty Rules

Every milestone validation executed by Gemini Flash MUST adhere to the following rules:
1. **No Fake Passes**: Never hardcode a test return value, stub out `main()` or `MagSystem::run()` to exit early and claim "boot succeeded", or render a static image not produced by the guest's actual GS/VIF1/VU1 pipeline.
2. **Strict Missing-Function Policy in Automated Tests**: All automated boot, menu, and gameplay tests MUST run with `MissingFunctionPolicy::Stop` (`0`) or assert `0` occurrences of `[guest-branch:missing-target]` and `Error: No exact recompiled function for guest PC` in `stderr`/`stdout`. Using `MissingFunctionPolicy::SkipCallDebug` (`3`) to pass a milestone gate is strictly forbidden.
3. **Host Resource Safety Assertions**: Before and after every build/test run, Flash must verify:
   * `df -BM /` shows **`>= 800M` available** on `/`.
   * Peak RSS (`/usr/bin/time -v`) during compilation/linking stays **`< 6,500,000 KB` (`6.5 GiB`)**.

---

## 2. Nine-Tier Verification Suite

### Tier 1: Baseline Upstream Unit Tests (`M01`)
* **Command**:
  ```bash
  export TMPDIR=/mnt/6421-8598/building/RozuRecomp/out/tmp
  ctest --test-dir /mnt/6421-8598/building/RozuRecomp/out/build/baseline --output-on-failure
  ```
* **Pass Criteria**: 100% of upstream `ps2xTest` executables (`test_elf_analyzer`, `test_code_generator_*`, `test_r5900_decoder`, `test_vu1_interpreter`, `test_vif1_interpreter`, `test_gs_*`, `test_iop_*`, `test_pad_override`, etc.) exit `0`.

### Tier 2: Static Recompilation & Symbol Coverage Audit (`M02–M03`)
* **Verification Script**: `tools/verify_recomp_coverage.py`
* **Quantitative Checks**:
  1. `config/slus_21448.toml` defines **`>= 8,900` functions** covering `.text` (`0x00100000`–`0x00280E88`) and all `1,449` `.gnu.linkonce.t.*` sections (`0x00280E88`–`0x0029122C`, `0x002953B0`–`0x00295EB8`).
  2. **Zero** functions overlap `[0x00291230, 0x002953B0)` (`.vutext`).
  3. All 4 `.ctors` targets (`0x00138BE0`, `0x001AE530`, `0x001CC290`, `0x0024B2D8`) and all valid code pointers in `.gnu.linkonce.d._vt$*` (`0x002E0A80`–`0x002E5300`) are registered entry points in `g_ps2RecompiledFunctionTable`.
  4. `grep -rn "UNHANDLED" out/recomp/` returns `0` unhandled R5900 instructions in active code sections.

### Tier 3: Deterministic Boot, `.ctors`, & `MagSystem` Loop Trace (`M04–M05`)
* **Execution Method**: Run `RozuRunner` against `out/disc/SLUS_214.48` for 15 seconds (under X11 display `:0` or `xvfb-run` if headless) with runtime logging enabled.
* **Quantitative Checks**:
  1. Log confirms `ELF file loaded successfully. Entry point: 0x100008` and `crc32 = 0x8cf7b024`.
  2. Guest executes `_start` (`0x00100008`) -> `__do_global_ctors` (`0x00280E38`) -> `main` (`0x001002D0`) -> `bedInitSystem` (`0x001005E0`) -> `MagSystem::initialize` (`0x00117AA0`) -> `MagSystem::run` (`0x00117FC8`).
  3. All 8 IOP modules listed in `IOPCONF.CNF` (`SIO2MAN.IRX`, `SIO2D.IRX`, `DBCMAN.IRX`, `PAD2/DS1O_D.IRX`, `MCMAN.IRX`, `MCSERV.IRX`, `LIBSD.IRX`, `RXSNDDRV.IRX`) load with `moduleId > 0`.
  4. `MagSystem::waitVSync` (`0x00118754`) wakes every 2 VSyncs (`m_v_rate = 2`) for **`>= 100` consecutive guest frames** with **0 missing-function errors**.

### Tier 4: Visual Framebuffer & GS/VU1 Validation (`M06`)
* **Frame Dump Hook**: Add a deterministic frame-capture flag (`--dump-frames-dir out/frames --dump-every-n-frames 30`) to the runner that saves the latched `512x448` / `512x384` RGBA buffer from `GS::copyLatchedHostPresentationFrame()` as PNG files + JSON metrics.
* **Quantitative Checks (No Human Eyeballing Alone)**:
  1. `GSDebugSnapshot` confirms `hostPresentationWidth == 512` and `hostPresentationHeight == 448` (or `384`), `FBP0 == 0x00`, `FBP1 == 0x70`, `ZBP == 0xE0`.
  2. Captured logo and title frames have:
     * **Zero** pure-magenta (`#FF00FF`, fallback blank texture) frames after first GS draw.
     * Non-black pixel ratio **`>= 5.0%`** and luminance standard deviation **`>= 15.0`** during Atlus/Sony logo and title screen display.
     * `m_memory.vifWriteCount() > 0`, `m_memory.gifCopyCount() > 0`, and `m_vu1.state().cycles > 0` (proving VU1 `.DVP.overlay` microcode executed).

### Tier 5: Audio & FMV Validation (`M07`)
* **Quantitative Checks**:
  1. **FMV (`.PSS`)**: When entering attract mode or starting a New Game (`MOVIE/*.PSS`), `sceMpegDemuxPssRing` and `sceMpegGetPicture` decode **`>= 60` consecutive video frames** and cleanly signal end-of-stream (`sceMpegIsEnd`) or skip on `Start` press without deadlocking.
  2. **Audio (`RXSNDDRV.IRX` + `.STR` / `XVAB`)**: `PS2AudioBackend` diagnostic counters record **`> 0` non-silent PCM samples** (`peak_abs_sample > 100` on int16 scale, `rms > 0.001`) during title music (`DATA/SND/XWS/*.STR`) and menu cursor sound effects (`DATA/SND/XV/*.SE`).

### Tier 6: Input (`libpad2`) & Memory Card (`libmc`) Functional Tests (`M08`)
* **Automated Input Script**: Use `setPadOverrideState` (`PS2_TEST_HOOK_LIST` in `ps2_call_list.h:690`) or CLI `--input-script` to inject deterministic DualShock 2 button sequences (`Start`, `D-Pad Down`, `Cross`, `Circle`, left analog stick `(lx=0x80, ly=0x00)`).
* **Quantitative Checks**:
  1. `BedPad::update` (`0x00101DF0`) calls `scePad2GetState` (receiving `6`) and `scePad2Read` (receiving `1`), and menu cursor state changes in guest RAM in response to `D-Pad Down` / `Cross`.
  2. Memory Card save/load test creates a save directory under `out/mc0/BASLUS-21448*`, writes icon + save data via `sceMcWrite`, closes via `sceMcClose`, and verifies non-zero file size on host disk and successful re-load on a fresh process start.

### Tier 7: First Playable Gameplay & `ELFR101` Script Progression (`M09`)
* **Quantitative Checks**:
  1. Selecting "New Game" loads `DATA/EVT/*.RPK` and `DATA/BG/STAGE01/*.RPK`, executes `CSequenceCode::update` (`0x001AE7C8`) on `ELFR101` bytecode without error, and transitions into interactive 3D gameplay in Stage 01.
  2. Injecting left-stick forward (`ly = 0x00`) for 120 frames changes Jennifer's world transform coordinates in guest RAM and produces changing 3D perspective frames (`frame_diff_l1 > 1.0%` between frames `t` and `t+30`).

### Tier 8: 30-Minute Sustained Soak & Leak Test (`M10`)
* **Quantitative Checks**:
  1. Continuous execution for **`>= 1,800` seconds (`30 minutes`, `>= 54,000` guest frames at 29.97 FPS)** across at least 3 room transitions, 2 menu opens/closes, and 1 save check.
  2. `0` crashes, `0` `[guest-branch:missing-target]` logs, `0` unhandled exceptions.
  3. Guest heap high-water mark (`PS2Runtime::guestHeapEnd()`) remains **`< 0x01E00000`** (`30 MiB`), and host process RSS growth between minute 5 and minute 30 is **`< 5%`**.

### Tier 9: Intel HD Graphics 620 Performance Benchmark (`M11`)
* **Quantitative Checks**:
  1. Over a 3,600-frame (`2-minute`) benchmark run in 3D gameplay on the i5-7200U + Intel HD Graphics 620:
     * Median guest frame time **`<= 33.4 ms` (`>= 29.9 FPS`)**.
     * 99th-percentile guest frame time **`<= 42.0 ms`**.
     * Host `UpdateTexture` calls per second **`<= 31.0`** (confirming 30 Hz upload gating).
