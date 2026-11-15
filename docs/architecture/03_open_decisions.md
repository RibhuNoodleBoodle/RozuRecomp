# 03 — Open Architectural Decisions & Tradeoffs

This document records the five non-trivial architectural tradeoffs evaluated for `Rule of Rose` (`SLUS_214.48`), the default decision selected for Flash's work orders (`M00–M12`), and the exact trigger conditions for switching to the fallback option.

---

## Decision 01: Generated Code Organization (`single_file_output` vs Unity Batching vs Per-Function Files)

* **Context**: `SLUS_214.48` contains `~8,963` R5900 functions across `.text` (`1.50 MiB`) and `.gnu.linkonce.t.*` (`69 KiB`). The host machine has `15 GiB` RAM (`9.8 GiB` available) and **`0 B` swap**.
* **Options Considered**:
  1. **`single_file_output = true`**: Emits one massive `.cpp` file (`~100+ MiB`). Fastest if RAM were 64 GiB, but under `g++ 15.2.0` it will consume `> 10 GiB` RSS and trigger the Linux OOM-killer (`Swap: 0B`).
  2. **Per-function `.cpp` files (`8,963` separate files)**: Low peak memory (`< 500 MiB`), but invoking `g++` 8,963 times on a 2-core/4-thread i5-7200U takes `> 45 minutes` due to header parsing overhead (`ps2_runtime.h`, `<immintrin.h>`).
  3. **Unity Batching (`single_file_output = false` + 32 to 64 Unity Batch `.cpp` files, ~140–280 functions per batch) (SELECTED)**: Parses headers only 32–64 times while capping per-process `g++` memory at `~800 MiB – 1.2 GiB` RSS (`< 2.5 GiB` total with `ninja -j2`).
* **Default Directive for Flash (M03)**: Use **Option 3 (64 Unity Batches + `ninja -j2`)** with `-O1` (or `-O2 -fno-var-tracking-assignments`) on generated guest batches.
* **Fallback Trigger**: If any single batch exceeds `3.0 GiB` RSS, split batches to `128` files (~70 functions/batch).

---

## Decision 02: Controller Input Architecture (`EE libpad2 Override` vs `LLE SIO2MAN + DBCMAN + DS1O_D.IRX`)

* **Context**: `Rule of Rose` (`BedPad`, `0x00101AEC`–`0x00102488`) uses `sceDbcInit`, `scePad2Init`, `scePad2CreateSocket`, `scePad2GetState`, `scePad2Read`, and `sceVibSetActParam`.
* **Options Considered**:
  1. **Full LLE IRX Execution (`SIO2MAN.IRX` + `SIO2D.IRX` + `DBCMAN.IRX` + `PAD2/DS1O_D.IRX`)**: Requires emulating the low-level SIO2 hardware registers (`0x1F808200`–`0x1F808280`), FIFO transfers, and DualShock 2 command/response wire protocol inside `ps2xIOP`.
  2. **IOP-Level `dbcman` + `ds1o_d` HLE Service**: Requires reverse-engineering the undocumented internal SIF RPC packet layouts between `libpad2` (EE), `DBCMAN.IRX` (IOP SID `0x80001300`), and `DS1O_D.IRX`.
  3. **EE-Level `libpad2` / `libdbc` / `libvib` Stub Override (`Pad.cpp` + `game_overrides`) (SELECTED)**: Intercepts the well-documented Sony SDK EE functions (`sceDbcInit` at `0x0026FC88`, `scePad2Init` at `0x0026DF00`, `scePad2CreateSocket` at `0x0026E168`, `scePad2DeleteSocket` at `0x0026E2B8`, `scePad2Read` at `0x0026E3C0`, `scePad2GetState` at `0x0026E4B0`, `sceVibSetActParam` at `0x002705A8`) and writes the standard 32-byte DualShock 2 button/analog/pressure packet directly into guest RDRAM from `ps2_stubs::Pad`.
* **Default Directive for Flash (M08)**: Use **Option 3 (EE-Level `libpad2` / `libdbc` / `libvib` Stub Overrides)** while still allowing `bedInitSystem` (`0x001005E0`) to load `DBCMAN.IRX` and `DS1O_D.IRX` cleanly during M05.

---

## Decision 03: Audio Architecture (`LIBSD.IRX + RXSNDDRV.IRX in IopEmulator` vs `HLE RXSNDDRV Service`)

* **Context**: `Rule of Rose` loads `MODULES/LIBSD.IRX` (`30,085` B) and custom `MODULES/RXSNDDRV.IRX` (`74,005` B) and streams 844 `.STR` ADPCM files + 36 `XVAB` `.SE` sound banks.
* **Options Considered**:
  1. **Execute `LIBSD.IRX` + `RXSNDDRV.IRX` in `ps2xIOP`'s R3000A `IopEmulator` (SELECTED PRIMARY)**: Argon verified that all 11 import libraries required by `RXSNDDRV.IRX` (`libsd`, `sysmem`, `intrman`, `loadcore`, `sifcmd`, `sifman`, `stdio`, `sysclib`, `thbase`, `thevent`, `vblank`) are already implemented in `ps2xIOP/src/emulator/iop_emulator.cpp`.
  2. **HLE `rxsnddrv` `IopService` + Direct ADPCM Decoder**: If `RXSNDDRV.IRX` waits on an unimplemented SPU2 hardware interrupt or DMA completion bit, intercept its SIF RPC SID in a dedicated `rxsnddrv.cpp` HLE service that decodes `XVAB` / `.STR` PS-ADPCM blocks directly into `PS2AudioBackend`.
* **Default Directive for Flash (M05 & M07)**: Let `IopEmulator` load and execute `LIBSD.IRX` and `RXSNDDRV.IRX` in M05/M07, trace all SIF RPC binds/calls from `mw/sound` (`0x00237D00`–`0x0024B490`), and implement an HLE `rxsnddrv` RPC fallback for any RPC function that blocks or fails to produce PCM output.

---

## Decision 04: FMV Movie Playback (`FFmpeg Staging in out/deps` vs `Built-in MPEG2/IPU Stub`)

* **Context**: `MOVIE/*.PSS` contains 41 MPEG-2 Program Stream videos (`2.18 GiB`). The host has `/usr/lib/x86_64-linux-gnu/libavcodec.so.62.11.100` installed at runtime, but the Ubuntu `-dev` headers (`libavcodec.pc`) are not installed in `/usr/lib/x86_64-linux-gnu/pkgconfig`.
* **Options Considered**:
  1. **M01–M06 with `-DPS2X_ENABLE_FFMPEG=OFF`**: Uses `MPEG.cpp`'s built-in non-FFmpeg fallback path so movie player state machines (`sceMpegGetPicture`, `sceMpegIsEnd`) never hang while core boot/GS/VU1/IOP work is completed.
  2. **M07 Local FFmpeg Header/PkgConfig Staging in `out/deps/ffmpeg` (SELECTED FOR M07)**: Extract matching Ubuntu `libav*-dev` `.deb` packages (via `apt-get download` into `out/deps/ffmpeg` — requires zero root privileges and zero `/` disk space!) and point `PKG_CONFIG_PATH` at `out/deps/ffmpeg/usr/lib/x86_64-linux-gnu/pkgconfig` to enable `-DPS2X_ENABLE_FFMPEG=ON` against the system's installed `/usr/lib/x86_64-linux-gnu/libav*.so`.
* **Default Directive for Flash**: Use `-DPS2X_ENABLE_FFMPEG=OFF` in M01–M06, then stage local FFmpeg headers in `out/deps/ffmpeg` in M07 to enable full `-DPS2X_ENABLE_FFMPEG=ON` video decoding.

---

## Decision 05: GS Rasterization Backend on Intel HD Graphics 620 (`SIMD GSCpuBackend` vs `OpenGL Hardware Backend`)

* **Context**: `ps2xRuntime` ships a mature software rasterizer (`GSCpuBackend` in `gs_cpu_backend.cpp`) that accurately handles PS2 GS `PSMCT32`, `PSMT8`/`PSMT4` CLUT textures, `PSMZ16S` (`ZGEQUAL`), alpha blending, and local-to-local transfers, uploading the resulting `512x448` / `512x384` RGBA framebuffer to an OpenGL `Texture2D`.
* **Default Directive for Flash (M06 & M11)**: Keep `GSCpuBackend` at native `512x448` / `512x384` resolution for visual accuracy, gate `UploadFrame()` on actual 30 Hz guest VSync frame updates, and SIMD-optimize hot pixel loops in M11. Only consider a custom OpenGL primitive backend if M11 profiling proves `GSCpuBackend` exceeds `16.0 ms/frame` after SIMD optimization.
