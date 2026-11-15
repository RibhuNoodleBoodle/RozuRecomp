# 04 — Rule of Rose Engine Architecture & Asset Formats (`SLUS_214.48`)

## 1. `SLUS_214.48` Memory Map & ELF Section Layout

`SLUS_214.48` (`2,296,472` bytes, SHA-256 `262efe713ad2432d4e8b2122a5edae9302b7f9eb900537b76beae064a4a91af3`, CRC32 `0x8cf7b024`) loads into EE RDRAM (`0x00100000`–`0x00828E94`) as follows:

| Virtual Address Range | ELF Section(s) | Size (Hex / Bytes) | Permissions | Contents & Architectural Notes |
| :--- | :--- | ---: | :---: | :--- |
| `0x00100000`–`0x00280E88` | `[1] .text` | `0x180E88` (`1,576,584` B) | `AX` (`R E`) | Main R5900 code: `crt0` (`0x00100008`), `main` (`0x001002D0`), game/engine modules (`0x00100000`–`0x0024B490`), and Sony SDK / Newlib / `libgcc2` (`0x0024B490`–`0x00280E88`). |
| `0x00280E88`–`0x0029122C` | `[2..1405] .gnu.linkonce.t.*` | `0x0103A4` (`66,468` B) | `AX` (`R E`) | `1,404` GCC2 linkonce C++ methods, template instantiations, and virtual destructors. |
| `0x00291230`–`0x002953B0` | `[1406] .vutext` (+ `[1750..1793] .DVP.overlay`) | `0x004180` (`16,768` B) | `AX` (`R E`) | **VU1 Microcode** (`44` `.DVP.overlay` microprograms + `.DVP.ovlytab`). **NOT R5900 CODE! Must be excluded from `ps2xRecomp` R5900 disassembly.** |
| `0x002953B0`–`0x00295EB8` | `[1407..1451] .gnu.linkonce.t.*` | `0x000B08` (`2,824` B) | `AX` (`R E`) | `45` additional GCC2 linkonce C++ template methods (`CStageDataMan`, `i3d`, etc.). |
| `0x00295EB8`–`0x00295ED0` | `[1452] .reginfo` | `0x000018` (`24` B) | `A` (`R`) | MIPS register usage metadata (`GP` value `0x0030FF70`). |
| `0x00295F00`–`0x002E014C` | `[1453] .data` | `0x04A24C` (`303,692` B) | `WA` (`RW`) | Initialized global data, stage/file lookup tables, script opcode dispatch tables, non-linkonce vtables. |
| `0x002E014C`–`0x002E0164` | `[1454] .ctors` | `0x000018` (`24` B) | `WA` (`RW`) | Global C++ constructor table: `0xFFFFFFFF`, `0x00138BE0`, `0x001AE530`, `0x001CC290`, `0x0024B2D8`, `0x00000000`. |
| `0x002E0164`–`0x002E0178` | `[1455] .dtors` | `0x000014` (`20` B) | `WA` (`RW`) | Global C++ destructor table. |
| `0x002E0178`–`0x002E0A7C` | `[1456] .eh_frame` | `0x000904` (`2,308` B) | `A` (`RW`) | GCC2 DWARF exception frame unwind records. |
| `0x002E0A80`–`0x002E5100` | `[1457..1725] .gnu.linkonce.d._vt$*` | `0x004680` (`18,048` B) | `WA` (`RW`) | `269` named C++ virtual method tables. |
| `0x002E5100`–`0x002E5300` | `[1726] .vudata` + `[1727..1741] .gnu.linkonce.d._vt$*` | `0x000200` (`512` B) | `WA` (`RW`) | Empty `.vudata` marker + `15` additional C++ virtual method tables (`284` total linkonce vtables). |
| `0x002E5300`–`0x00307F70` | `[1742] .rodata` | `0x022C70` (`142,448` B) | `A` (`RW`) | Read-only strings (`cdrom0:\...`, debug logs, stage names), float constants, jump tables. |
| `0x00307F80`–`0x00307FFC` | `[1743] .gcc_except_table` | `0x00007C` (`124` B) | `A` (`RW`) | GCC2 exception range tables. |
| `0x00308000`–`0x003080BC` | `[1744] .sbss` | `0x0000BC` (`188` B) | `WAp` (`RW`) | Small GP-relative uninitialized globals (`GP = 0x0030FF70`). |
| `0x00308100`–`0x00828E94` | `[1745] .bss` | `0x520D94` (`5,377,428` B) | `WA` (`RW`) | Uninitialized static buffers (~5.13 MiB: static heaps, DMA packet ring buffers, audio/movie work buffers). |
| `0x00829EA0`–`0x01F00000` | *Runtime Guest Heap* | `0x16D6160` (`23,945,568` B) | `RW` | Managed by `PS2Runtime::guestMalloc` / `utl::CAllocater`. |
| `0x01F00000`–`0x02000000` | *Stack & Async Callback Area* | `0x0100000` (`1,048,576` B) | `RW` | Main EE thread stack (`SP` starts at `0x01FFFFF0`) + async callback stacks. |

---

## 2. Engine Subsystem Breakdown (`SLUS_214.48`)

### 2.1 `bed/` — Low-Level Hardware Abstraction (`0x00100390`–`0x00105300`)
* **`bedInitSystem` (`0x001005E0`)**:
  * Initializes SIF RPC (`sceSifInitRpc(0)`), CD/DVD (`sceCdInit(SCE_CDINIT)`), and media mode (`sceCdMmode(SCE_CDVDMediaModeDVD)`).
  * Reads `cdrom0:\IOPCONF.CNF;1`, reboots the IOP with `cdrom0:\MODULES\IOPRP300.IMG;1` via `sceSifRebootIop` + `sceSifSyncIop`, re-initializes `sceSifInitRpc(0)`, `sceSifLoadFileReset()`, `sceFsReset()`, `sceCdInit(0)`, `sceCdMmode(2)`, and sequentially loads the 8 `.IRX` modules via `sceSifLoadModule`:
    1. `cdrom0:\MODULES\SIO2MAN.IRX;1`
    2. `cdrom0:\MODULES\SIO2D.IRX;1`
    3. `cdrom0:\MODULES\DBCMAN.IRX;1`
    4. `cdrom0:\MODULES\PAD2\DS1O_D.IRX;1`
    5. `cdrom0:\MODULES\MCMAN.IRX;1`
    6. `cdrom0:\MODULES\MCSERV.IRX;1`
    7. `cdrom0:\MODULES\LIBSD.IRX;1`
    8. `cdrom0:\MODULES\RXSNDDRV.IRX;1`
* **`BedPad` (`0x00101AEC`–`0x00102488`)**:
  * Wraps Sony's **`libdbc` + `libpad2` + `libvib`** stack (NOT legacy `libpad`).
  * `BedPad::initialize()` (`0x00101BC8`) calls `sceDbcInit()`, `scePad2Init(0)`, allocates a 256-byte aligned DMA buffer, and opens port 0 / slot 0 via `scePad2CreateSocket(&socketParam, dmaBuf)`.
  * `BedPad::update()` (`0x00101DF0`) polls `scePad2GetState(socket)`, reads the 32-byte DualShock 2 packet via `scePad2Read(socket, rawData)`, parses buttons (`rawData[2..3]`, active-low), right/left analog sticks (`rawData[4..7]`), and pressure bytes (`rawData[8..19]`), and drives actuator vibration via `sceVibSetActParam`.

### 2.2 `utl/` & `dog/` — Memory Allocators, Math, Camera, and Utilities (`0x00105300`–`0x00117654`)
* **`utl::CAllocater`**: Custom arena/heap allocator backed by guest memory (`malloc`/`EndOfHeap`).
* **`dog/`**: Camera controllers (`CDogCamera`), spline interpolation, collision primitives, and Brown (the dog companion) pathfinding/tracking helpers.

### 2.3 `mag/` — `MagSystem` Core Engine & Frame Loop (`0x00117654`–`0x001194B4`)
* **Display Setup (`MagSystem::initialize`, `0x00117AA0`)**:
  * Resets GS (`sceGsResetGraph(0, SCE_GS_INTERLACE, SCE_GS_NTSC, SCE_GS_FIELD)`).
  * Configures double-buffered `sceGsDBuffDc` at **`512x448`** (`SCE_GS_PSMCT32`, `FBP0 = 0x00`, `FBP1 = 0x70`, `FBW = 8`, `ZBP = 0xE0`, `ZPSM = SCE_GS_PSMZ16S`, `ZTEST = SCE_GS_ZGEQUAL`). Also supports `setDisplay384` (`512x384`) for letterboxed cutscene/menu modes.
  * Creates VSync semaphore `m_v_sema` (`CreateSema`) and registers `vsyncHandler` (`0x00117654`) via `sceGsSyncVCallback(vsyncHandler)`.
* **30 FPS Frame Pacing (`vsyncHandler` & `MagSystem::waitVSync`, `0x00118754`)**:
  * `m_v_rate` is initialized to **`2`**. Every VSync interrupt increments a counter; when `counter >= m_v_rate`, `vsyncHandler` calls `iSignalSema(m_v_sema)`. This locks the game to **29.97 FPS (30 Hz)**.
  * `MagSystem::update()` (`0x001182DC`) reads hardware timer `*T0_COUNT` (`*(volatile uint32_t*)0x10000000`) to measure CPU/DMA frame time, ticks the task tree, sends the VIF1 DMA chain (`sceDmaSend(m_dma, ...)` on channel 1), and calls `waitVSync()`.
  * `MagSystem::waitVSync()` (`0x00118754`) spins on `while (sceDmaSync(m_dma, 1, 0))` until VIF1 DMA completes, waits on `WaitSema(m_v_sema)`, calls `sceGsSyncPath(0, 0)`, and swaps buffers via `sceGsSwapDBuffDc(&m_db, m_frame)`.

### 2.4 `emy/`, `game/`, `task/`, `sequence/` — Gameplay, AI, and `ELFR101` Script Engine (`0x001194B4`–`0x00218500`)
* **`task/` (`CTask`, `CTaskMan`)**: Hierarchical task scheduler driving boot logos -> title screen -> movie player -> stage loader -> gameplay rooms -> pause/inventory menus.
* **`sequence/` (`CSequenceCode`, `0x001AE570`–`0x001B0CF0`)**:
  * Interprets custom bytecode files prefixed with the 8-byte ASCII magic **`ELFR101\0`** (extracted from `DATA/EVT/*.RPK` and `DATA/BG/STAGE*/*.RPK`).
  * Despite the `ELFR101` magic string, these files are **NOT** MIPS ELF binaries; they are a proprietary bytecode VM with a 48-byte header (`magic = "ELFR101\0"`, version, code offset, string table offset, entrypoint count) executed entirely by `CSequenceCode::update()` (`0x001AE7C8`).
* **`emy/`**: Enemy AI state machines (`CEnemyAi`, Imps, Bosses) and hit/grab collision logic.

### 2.5 `mw/i3d` — 3D Rendering & VU1 Pipeline (`0x00218500`–`0x00237D00`)
* Builds VIF1 DMA chains (`UNPACK` + `MPG` + `MSCAL`/`MSCNT` + `DIRECT`) for character skinning (`DATA/CHAR/*.RPK`), stage geometry (`DATA/BG/STAGE*`), dynamic lighting, stencil/projected shadows, and post-processing.
* Uploads and switches among the **44 VU1 microcode overlays** stored in `.vutext` (`0x00291230`–`0x002953B0`, indexed by `.DVP.ovlytab` `[1748]` and `.DVP.ovlystrtab` `[1749]`).

### 2.6 `mw/sound` — Audio Engine (`0x00237D00`–`0x0024B490`)
* Communicates over SIF RPC with `MODULES/RXSNDDRV.IRX` and `MODULES/LIBSD.IRX` (`sceSdRemoteInit`, `sceSdRemote`) to play 36 `XVAB` sound-effect banks (`DATA/SND/XV/*.SE`) in SPU2 RAM and stream 844 `.STR` files (`DATA/SND/XWS/*.STR`) from CD/DVD.

---

## 3. Proprietary Asset Container Formats on Disc

| Format / Extension | Header Magic & Layout | Location on Disc | Count | Runtime Consumer |
| :--- | :--- | :--- | ---: | :--- |
| **`.RPK` (`RTPK` Archive)** | Magic `RTPK` (`0x4B505452`), followed by archive size, entry count, 16-byte aligned offset table, file size table, and null-terminated filename table. | `DATA/CHAR/`, `DATA/CUT/`, `DATA/BG/`, `DATA/EVT/`, `DATA/MENU/`, `DATA/LIMIT/`, `DATA/EFFECT/` | `1,451` | `CRpkDataMan` (`0x0011A000`+): unpacks sub-assets (textures, `i3d` models, animations, `ELFR101` scripts) in guest RAM. |
| **`MAPUNIT.BIN` & `.ARA`** | `AREA` (`0x41455241`) header defining room cells, collision meshes, trigger volumes, and camera zones. | `DATA/BG/STAGE01..12/` | `281` | Stage manager & `CDogCamera` / collision subsystem. |
| **`.STR` (Audio Stream)** | **Headerless raw PS-ADPCM** (16-byte SPU2 ADPCM blocks at `48,000 Hz`). `S0xxxxx.STR` = mono; `S1xxxxx.STR` = stereo (`0x10`-byte L/R block interleave). | `DATA/SND/XWS/` | `844` | Streamed from disc by `mw/sound` + `RXSNDDRV.IRX` into SPU2 streaming buffers. |
| **`.SE` (`XVAB` Sound Bank)** | Magic `XVAB` (`0x42415658`), header wrapping Sony VAB/VAG SPU2 ADPCM sample programs and tone attributes. | `DATA/SND/XV/` | `36` | Uploaded to SPU2 voice RAM via `mw/sound` + `RXSNDDRV.IRX`. |
| **`.PSS` (PlayStation Stream FMV)** | MPEG-2 Program Stream (`0x000001BA` pack headers) multiplexing MPEG-2 video (`0xE0`) and Sony `SS2`/`ADS` ADPCM audio (`0xBD`). | `MOVIE/` | `41` | Demuxed via `sceMpegDemuxPssRing` (`MPEG.cpp`) and decoded via IPU / `FFMPEG`. |
