# 01 — System Architecture (`Rule of Rose` Static Recompilation on `PS2Recomp`)

## 1. End-to-End Text Dependency & Data-Flow Diagram

```text
+---------------------------------------------------------------------------------------------------+
|                        OFFLINE STATIC RECOMPILATION PIPELINE (M02 - M03)                          |
+---------------------------------------------------------------------------------------------------+
  User Disc Image (/mnt/6421-8598/building/RozuRecomp/Rule of Rose (USA).iso)
         |
         +--> Extracted to ignored /mnt/6421-8598/building/RozuRecomp/out/disc/
         |      |-- SLUS_214.48 (2,296,472 B, SHA-256: 262efe71..., CRC32: 0x8cf7b024)
         |      |-- SYSTEM.CNF, SYSTEM.INI, IOPCONF.CNF
         |      |-- MODULES/ (IOPRP300.IMG, SIO2MAN, SIO2D, DBCMAN, PAD2/DS1O_D, MCMAN, MCSERV, LIBSD, RXSNDDRV)
         |      +-- DATA/ & MOVIE/ (RTPK .RPK, MAPUNIT.BIN, .ARA, .STR, XVAB .SE, .PSS)
         |
         v
  Symbol & Boundary Generator (tools/rozu_symbols/ or ps2xAnalyzer + Linkonce/Vtable Extractor)
         |-- Reads 1,449 .gnu.linkonce.t.* ELF sections (0x00280E88..0x0029122C, 0x002953B0..0x00295EB8)
         |-- Reads 284 .gnu.linkonce.d._vt$* vtables + .ctors (0x002E014C) + .eh_frame (0x002E0178)
         |-- Matches 648 Sony SDK/Newlib/libgcc2 functions (0x0024B490..0x00280E88) via sce_symbol_database
         |-- Scans .text (0x00100000..0x0024B490) for ~6,866 game/engine/mw::i3d/mw::sound functions
         |-- EXCLUDES [0x00291230, 0x002953B0) (.vutext / 44 .DVP.overlay VU1 microprograms)
         v
  TOML Recompiler Config (config/slus_21448.toml, ~8,963 verified function boundaries)
         |
         v
  ps2xRecomp (ElfParser + CodeGenerator + Rabbitizer 1.13.0)
         |-- Emits dense dispatch table: g_ps2RecompiledFunctionTable [0x00100000, 0x00295EB8)
         |-- Emits 32-64 Unity Batch C++ files in out/recomp/ (single_file_output = false)
         +-- Links with ps2xRuntime + ps2xIOP (ninja -j2, TMPDIR=out/tmp, peak RSS < 4.5 GiB)

+---------------------------------------------------------------------------------------------------+
|                        RUNTIME EXECUTION ARCHITECTURE (M04 - M12)                                 |
+---------------------------------------------------------------------------------------------------+
  +---------------------------------------------------+     +---------------------------------------+
  | Thread 1: Host Main / Presentation Thread         |     | Thread 2: GameThread (EeScheduler)    |
  | (PS2Runtime::run() in ps2_runtime.cpp)            |     | (Recompiled R5900 Guest Execution)    |
  |---------------------------------------------------|     |---------------------------------------|
  | - raylib 5.5 OpenGL 4.6 Window (Intel HD 620)     |     | - Executes _start (0x00100008)        |
  | - Polls Keyboard / Gamepad (Pad.cpp)              |     |   -> __do_global_ctors (0x00280E38)   |
  | - Calls UploadFrame() ONLY when VSync tick        |     |   -> main (0x001002D0)                |
  |   advances (avoids redundant PCIe/RAM copies)     |     |   -> bedInitSystem (0x001005E0)       |
  | - Draws 512x448 / 512x384 Texture2D to screen     |     |   -> MagSystem::run (0x00117FC8)      |
  | - Drives raylib AudioStream (48 kHz stereo PCM)   |     | - Cooperative preemptive checkpoints  |
  +-------------------------^-------------------------+     |   at branches & dispatchGuestBranch() |
                            |                               +---------+-------------------+---------+
                            | Latched 512x448 RGBA                    |                   |
                            | Presentation Frame                      | MMIO / DMA        | Syscalls / Stubs / SIF RPC
                            |                                         v                   v
  +-------------------------+-------------------------+     +---------+-------------------+---------+
  | GS / VIF1 / VU1 Graphics Pipeline                 |     | Kernel Stubs, Overrides & ps2xIOP     |
  |---------------------------------------------------|     |---------------------------------------|
  | - DMAC Ch 1 (VIF1) & Ch 2 (GIF) (ps2_memory.cpp)  |     | - Game Override (CRC32 0x8cf7b024):   |
  | - ps2_vif1_interpreter: UNPACK, DIRECT, MPG       |     |   * BedPad / libpad2 (scePad2Init,    |
  |   (uploads 44 .vutext overlays to VU1 Code RAM)   |     |     scePad2CreateSocket, scePad2Read, |
  | - VU1Interpreter (ps2_vu1_core.cpp):              |     |     scePad2GetState, sceDbcInit,      |
  |   executes MSCAL/MSCNT -> XGKICK -> Path 1 GIF    |     |     sceVibSetActParam) -> Pad.cpp     |
  | - GifArbiter -> GS Frontend -> GSCpuBackend       |     | - Timer 0 (*T0_COUNT 0x10000000) &    |
  |   (512x448 PSMCT32, FBP 0x00/0x70, ZBP 0xE0       |     |   sceGsSyncVCallback -> vsyncHandler  |
  |    PSMZ16S ZGEQUAL, 512x384 setDisplay384)        |     |   (m_v_rate = 2 -> 29.97 FPS lock)    |
  +---------------------------------------------------+     | - ps2xIOP (IopSubsystem + IopEmulator)|
                                                            |   * CDVD / VFS -> out/disc/ or ISO    |
                                                            |   * mcserv HLE -> out/mc0/BESLES...   |
                                                            |   * LIBSD.IRX + RXSNDDRV.IRX in R3000A|
                                                            |     IopEmulator -> PS2AudioBackend    |
                                                            | - MPEG / IPU (MPEG.cpp + FFmpeg)      |
                                                            +---------------------------------------+
```

---

## 2. Subsystem Ownership & Interface Contracts

### 2.1 `ps2xAnalyzer` & Symbol/Boundary Generator (`ps2xAnalyzer/`, `tools/`)
* **Responsibility**: Produce a 100% deterministic, overlap-free function boundary and stub binding configuration (`config/slus_21448.toml`) for `SLUS_214.48`.
* **Interface Contract**:
  * Must emit every R5900 function in `.text` (`0x00100000`–`0x00280E88`) and `.gnu.linkonce.t.*` (`0x00280E88`–`0x0029122C`, `0x002953B0`–`0x00295EB8`).
  * Must **never** emit any function entry point inside `.vutext` (`[0x00291230, 0x002953B0)`).
  * Must map the 648 Sony SDK/libc functions (`0x0024B490`–`0x00280E88`) to their canonical `PS2_SYSCALL_LIST` or `PS2_STUB_LIST` names where runtime interception is desired.

### 2.2 `ps2xRecomp` (`ps2xRecomp/src/lib/`)
* **Responsibility**: Parse `SLUS_214.48`, decode R5900/MMI/FPU/COP0/VU0-macro instructions via `rabbitizer`, and emit C++ source files + `register_functions.cpp`.
* **Required Architectural Adjustment (`elf_parser.cpp`)**:
  * In `ElfParser::isExecutableSection()` (`ps2xRecomp/src/lib/elf_parser.cpp:694`), explicitly reject sections named `.vutext` or carrying DVP overlay types even when `SHF_EXECINSTR` is set.
  * Support loading `.gnu.linkonce.t.*` section headers as exact function boundaries when `.symtab` is absent, or ingest them from the generated TOML function list.
  * Emit functions into **32–64 unity batch `.cpp` files** (or configure CMake `UNITY_BUILD` with `UNITY_BUILD_BATCH_SIZE 160`) so `g++ 15.2.0` compiles the entire game within `< 4.5 GiB` peak RSS on the 0-swap host.

### 2.3 `ps2xRuntime` — EE Scheduler, Memory, and Timer Subsystem (`ps2xRuntime/src/lib/`)
* **Responsibility**: Manage the 32 MiB EE RDRAM (`0x00000000`–`0x01FFFFFF`), 16 KiB Scratchpad (`0x70000000`), hardware MMIO registers (`0x10000000`–`0x1000F590`), cooperative EE thread scheduling (`EeScheduler`), VSync callbacks, and dense function table dispatch (`g_ps2RecompiledFunctionTable`).
* **`Rule of Rose` Specific Contracts**:
  * **Hardware Timer `T0_COUNT` (`0x10000000`)**: `MagSystem::update()` (`0x001182DC`) and `MagSystem::waitVSync()` (`0x00118754`) read `*(volatile uint32_t*)0x10000000` (`T0_COUNT`) and `0x10000010` (`T0_MODE`). `PS2Memory::read32(0x10000000)` MUST return a monotonically advancing 16-bit/32-bit bus-clock/HBlank counter synchronized with EE execution cycles so delta calculations never divide by zero or spin forever.
  * **VSync Callback (`sceGsSyncVCallback`, `0x00253E58`)**: `MagSystem::initialize()` registers `vsyncHandler` (`0x00117654`) via `sceGsSyncVCallback`. On every 59.94 Hz VSync tick in `EeScheduler`, the registered callback MUST be invoked in interrupt-handler context so `iSignalSema(m_v_sema)` wakes the main thread every `m_v_rate = 2` VSyncs (`29.97 FPS`).
  * **DMAC Completion (`sceDmaSend` / `sceDmaSync`)**: `MagSystem::waitVSync()` loops on `while (sceDmaSync(m_dma, 1, 0))` (`0x00252930`). `sceDmaSend` on channel 1 (`VIF1`) and channel 2 (`GIF`) must process the DMA chain through `ps2_vif1_interpreter` / `GifArbiter` and clear `CHCR.STR` so `sceDmaSync` returns `0` (idle) immediately.

### 2.4 Controller Override Subsystem (`libpad2` + `libdbc` + `libvib`)
* **Problem**: `Rule of Rose` (`BedPad`, `0x00101AEC`–`0x00102488`) uses Sony's newer `libdbc` + `libpad2` + `libvib` libraries (`DBCMAN.IRX` + `PAD2/DS1O_D.IRX`) instead of `libpad` (`PADMAN.IRX`).
* **Architectural Solution**:
  * Extend `ps2xRuntime/include/ps2_call_list.h` (`PS2_STUB_LIST`) and `ps2xRuntime/src/lib/Kernel/Stubs/Pad.cpp` with native HLE implementations for:
    * `sceDbcInit` (`0x0026FC88`) -> returns `1`
    * `sceDbcEnd` (`0x0026FD78`) -> returns `1`
    * `scePad2Init` (`0x0026DF00`) -> initializes `Pad.cpp` state, returns `1`
    * `scePad2End` (`0x0026E040`) -> returns `1`
    * `scePad2CreateSocket` (`0x0026E168`) -> allocates/opens virtual pad socket `1` for port 0 / slot 0, initializes DualShock 2 analog mode, returns socket ID (`>= 1`)
    * `scePad2DeleteSocket` (`0x0026E2B8`) -> returns `1`
    * `scePad2GetState` (`0x0026E4B0`) -> returns `6` (`SCE_PAD2_STATE_STABLE`)
    * `scePad2Read` (`0x0026E3C0`) -> populates the 32-byte guest buffer at `$a1` with DualShock 2 status (`data[0] = 0x00`, `data[1] = 0x79` or `0x73`, `data[2..3]` active-low buttons from raylib keyboard/gamepad/override hook, `data[4..7]` analog sticks `rx, ry, lx, ly`, `data[8..19]` pressure bytes) and returns `1`
    * `scePad2GetButtonInfo` / `scePad2SetButtonInfo` -> returns `1`
    * `sceVibGetProfile` (`0x002703A8`), `sceVibSetActParam` (`0x002705A8`) -> returns `1`
  * Bind these exact addresses in a `Rule of Rose` descriptor (`CRC32 = 0x8cf7b024`, `entry = 0x00100008`, `elfName = "SLUS_214.48"`) via `ps2_game_overrides::registerDescriptor`.

### 2.5 IOP Subsystem (`ps2xIOP`) — CDVD, Memory Card, and `RXSNDDRV.IRX` Audio
* **CDVD & VFS (`iop_cdvd.cpp`, `ps2_vfs.cpp`, `CD.cpp`)**:
  * Resolves `cdrom0:\PATH\FILE.EXT;1` against `IoPaths::cdRoot` (`/mnt/6421-8598/building/RozuRecomp/out/disc`) or directly from `Rule of Rose (USA).iso`.
  * Strips `;1` version suffixes and performs case-insensitive path matching on Linux ext4 so mixed-case lookups (e.g., `cdrom0:\pad2\ds1o_d.irx` in `IOPCONF.CNF` vs `/MODULES/PAD2/DS1O_D.IRX` on ISO) succeed.
* **Memory Card (`mcserv.cpp`, `MC.cpp`)**:
  * Routes `sceMc*` (`SID 0x80000400`) to `IoPaths::mcRoot` (`/mnt/6421-8598/building/RozuRecomp/out/mc0`), persisting `BASLUS-21448*` save directories, icons, and save files on disk.
* **Audio (`LIBSD.IRX` + `RXSNDDRV.IRX` + `PS2AudioBackend`)**:
  * `IopEmulator` (`ps2xIOP/src/emulator/iop_emulator.cpp`) loads physical `LIBSD.IRX` (`30,085` B) and `RXSNDDRV.IRX` (`74,005` B) from `cdrom0:\MODULES\`.
  * Because `IopSubsystem::loadModule()` prioritizes physical IRX loading for `cdrom0:` paths (`iop_subsystem.cpp:123-132`), `LIBSD.IRX` exports `libsd` (`v1.5`) in `loadcore` and `RXSNDDRV.IRX` links against `libsd` + standard IOP kernel libraries (`sysmem`, `intrman`, `loadcore`, `sifcmd`, `sifman`, `stdio`, `sysclib`, `thbase`, `thevent`, `vblank`).
  * SPU2 voice/ADPCM register writes and DMA transfers feed `PS2AudioBackend` (`48 kHz` stereo output via raylib `AudioStream`). If `RXSNDDRV.IRX` awaits an SPU2 DMA or timer interrupt not yet ticked by `IopEmulator`, add the missing IRQ trigger in `iop_emulator.cpp` AND provide an HLE RPC service fallback for `RXSNDDRV`'s SIF RPC SID so audio initialization can never deadlock the main thread.

---

## 3. Rendering Pipeline & 30 FPS Frame Budget on Intel HD Graphics 620 (`i5-7200U`)

### 3.1 Frame Pacing & Threading Model (2 Cores / 4 Threads)
* `Rule of Rose` runs at a native **29.97 FPS** (`m_v_rate = 2` VSyncs = **`33.37 ms` per game frame**).
* On the 2-core / 4-thread Intel Core i5-7200U (`2.50–3.10 GHz`):
  * **Thread 1 (Main / Raylib Render Thread)**: Runs at 60 Hz (`16.67 ms`), polling window/input events and presenting `frameTex`.
  * **Thread 2 (`GameThread` / `EeScheduler`)**: Runs recompiled R5900 code, `VU1Interpreter`, `GSCpuBackend`, and `IopEmulator`.
* **Per-Frame CPU Time Budget (`33.37 ms` total per game frame)**:
  * Recompiled R5900 game + `ELFR101` script + `mw/i3d` packet build: `<= 6.0 ms`
  * `ps2_vif1_interpreter` + `VU1Interpreter` (`.vutext` overlays + `XGKICK`): `<= 8.0 ms`
  * `GSCpuBackend` software rasterization (`512x448` `PSMCT32` + `PSMZ16S`): `<= 10.0 ms`
  * `IopEmulator` (`RXSNDDRV.IRX` + CDVD + audio mixing): `<= 3.0 ms`
  * Host OpenGL 4.6 texture upload & presentation (`Intel HD 620`): `<= 2.5 ms`
  * **Total Target Frame Time**: **`<= 29.5 ms`** (maintaining full-speed 29.97 FPS with `>= 3.8 ms` headroom).

### 3.2 Intel HD Graphics 620 Specific Optimizations (M11)
1. **Eliminate Redundant Framebuffer Clears & Texture Uploads**:
   * In `UploadFrame()` (`ps2xRuntime/src/lib/ps2_runtime.cpp:376-478`), `copyLatchedHostPresentationFrame()` and `UpdateTexture()` are currently guarded by `currentTick != s_lastPresentationTick`, which ticks at 60 Hz even though `Rule of Rose` only swaps display buffers (`sceGsSwapDBuffDc`) at **30 Hz**.
   * Latching and calling `UpdateTexture()` only when `GS::processGIFPacket` / `sceGsPutDispEnv` has actually updated the presented frame halves CPU-to-GPU memory traffic on unified DDR4 RAM.
2. **SIMD Rasterizer & Compiler Flags**:
   * Compile `ps2xRuntime` (especially `gs_cpu_backend.cpp` and `ps2_vu1_core.cpp`) with `-O2 -msse4.1 -mavx2 -mfma` (all natively supported by the Kaby Lake i5-7200U).
