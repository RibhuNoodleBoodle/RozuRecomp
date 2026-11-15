# RozuRecomp — Rule of Rose (`SLUS-21448`) Static Recompilation

> [!NOTE]
> **Status (`2026-11-15`):** In progress — **Milestones M00–M03 complete**, **Milestone M04 (`WIP`)** actively booting `SLUS_214.48` with all 8 IOP `.IRX` modules loaded and GS/DMAC init active.
> Target release: **Rule of Rose (USA, `SLUS-21448`, `VER = 1.00`, CRC32 `0x8cf7b024`)**, built on [`ran-j/PS2Recomp`](https://github.com/ran-j/PS2Recomp) (`e5636981a1c9de368f6b71e819c3dc188dfedbf4`).

---

## Project Progress

### Milestone Overview

| ID | Milestone | Status | Commit SHA | Notes |
| --- | --- | --- | --- | --- |
| M00 | Inventory & Baseline | **DONE** | `ee43bbaf45eebdc49a9de33e4f0bde39b3b9f119` | Hardened `.gitignore`, extracted retail ISO (`2,145` files) to `out/disc/`, verified `SLUS_214.48` (`2,296,472` bytes, SHA-256 `262efe713ad2432d4e8b2122a5edae9302b7f9eb900537b76beae064a4a91af3`, CRC32 `0x8cf7b024`). |
| M01 | Upstream Toolchain & Tests | **DONE** | `9a7990313cad693e3ba3e424012626ad8928fd22` | Built `ps2xAnalyzer`, `ps2xRecomp`, `ps2xIOP`, `ps2xRuntime`, and `ps2xTest` in `out/build/baseline` (`-DPS2X_ENABLE_FFMPEG=OFF`, `-msse4.1` for GCC 15 `x86_64`); `45/45` `ctest` + `446/446` `ps2x_tests` (`491/491`) passing. |
| M02 | Function Map & `.vutext` Exclusion | **DONE** | `6ad9152f95c05da221197f70aed4914da5be13e2` | Excluded `.vutext` (`[0x00291230, 0x002953B0)`) / `.vudata` / `.DVP.*` in `ElfParser`, synthesized `.gnu.linkonce.t.*` boundaries, and generated `config/slus_21448.{csv,toml}` via `tools/generate_slus21448_toml.py`: `8,983` functions (`7,534` `.text` + `1,449` `.gnu.linkonce.t.*`, `228` stubs, `439` entries, `171` jump tables); `491/491` tests passing. |
| M03 | Static Recompilation Integration | **DONE** | `737466feda6602d45f4377e875f4bc9ca16f20f5` | Recompiled `8,983` functions (`0` unhandled, `0` errors) into `out/recomp/`, integrated `64`-batch unity compilation (`PS2X_RECOMP_OUTPUT_DIR`) into `ps2xRuntime/CMakeLists.txt`, and linked `38M` `ps2EntryRunner` (`889.6s`, `1.59 GiB` peak RSS); `491/491` tests passing. |
| M04 | Runtime Boot & Dispatch | **WIP** | *Uncommitted working tree* | Booting `SLUS_214.48` cleanly from `0x100008` through SIF RPC, all 8 IOP `.IRX` modules, GS register init, and DMAC sends (`vsyncTicks=120`, `missingFunction=0`); currently resolving Thread 1 vs sound Thread 4 scheduling/priority starvation and function-split generator rules. |
| M05 | IOP IRX, CDVD & RPC | **TODO** | - | `bedInitSystem` (`0x001005E0`) full disc / case-insensitive CDVD VFS & `.RPK` loading. |
| M06 | GS & VU Graphics | **TODO** | - | VIF1/GIF DMA sync, 44 `.vutext` `.DVP.overlay` VU1 uploads, `512x448` / `512x384` boot logos & title screen. |
| M07 | Movies & Audio | **TODO** | - | `MOVIE/*.PSS` MPEG-2 playback (staging FFmpeg headers in `out/deps/`) and `LIBSD.IRX` / `RXSNDDRV.IRX` `.STR` streaming. |
| M08 | Input, Menu & Saves | **TODO** | - | `libpad2` / `libdbc` / `libvib` handlers for `BedPad` (`0x00101AEC`) and `mc0` (`BASLUS-21448*`) save/load. |
| M09 | First Playable Gameplay | **TODO** | - | New Game boot into `STAGE01` interactive 3D gameplay via `ELFR101` / `CSequenceCode::update` (`0x001AE7C8`). |
| M10 | Sustained Gameplay Testing | **TODO** | - | Continuous 30-minute soak test across room transitions, menus, companion AI, combat, and save/load. |
| M11 | Intel HD 620 Optimization | **TODO** | - | 30 Hz `UploadFrame()` gating + SIMD `GSCpuBackend` targeting `<= 33.4 ms` median frame time. |
| M12 | Packaging & Regression | **TODO** | - | Full `ctest` + regression suite verification, Git cleanliness audit, and final `handoff.txt`. |

### Current M04 Runtime Findings & Working Tree Changes

- **Game Override & Runner Controls**: Registered `Rule of Rose (NTSC-U)` (`SLUS_214.48`, CRC32 `0x8cf7b024`, `MissingFunctionPolicy::Stop`) in [`ps2xRuntime/src/lib/game_overrides.cpp`](ps2xRuntime/src/lib/game_overrides.cpp) and added `--max-frames` / `--max-seconds` flags in [`ps2xRuntime/src/main.cpp`](ps2xRuntime/src/main.cpp).
- **Kernel, Syscall & Interrupt Fixes**:
  - Updated `InitThread`, alarm syscalls (`0xFD` / `-0xFE`), and exception vector syscalls across [`Thread.cpp`](ps2xRuntime/src/lib/Kernel/Syscalls/Thread.cpp), [`Dispatcher.cpp`](ps2xRuntime/src/lib/Kernel/Syscalls/Dispatcher.cpp), and [`System.cpp`](ps2xRuntime/src/lib/Kernel/Syscalls/System.cpp).
  - Isolated [`asyncCallbackStack`](ps2xRuntime/src/lib/ps2_runtime.cpp) so timer/alarm callbacks do not corrupt the main thread stack.
  - Fixed interrupt/alarm/GS-callback preemption guards (`hasActiveInterruptInvocation`) in [`EeScheduler.cpp`](ps2xRuntime/src/lib/Kernel/EeScheduler.cpp), allowing sound scheduler alarms (`0x24a678`) to complete cleanly and Thread 4 (`0x2492b0`) to resume.
- **Latest Verified Boot State (`out/m04_boot.log`)**:
  - Loads and starts all 8 IOP `.IRX` modules (`SIO2MAN.IRX`, `SIO2D.IRX`, `DBCMAN.IRX`, `DS1O_D.IRX`, `MCMAN.IRX`, `MCSERV.IRX`, `LIBSD.IRX`, `RXSNDDRV.IRX`), including `RX` sound RPC server startup.
  - Executes initial `[gs:reg]` setup and DMAC transfers (`[sceDmaSend]` on `0x10009000` and `0x10008000`).
  - Runs 120 guest VSync ticks (`hostFrames=351`, `activeThreads=4`, `missingFunction=0`, exit code `0`).
- **Active M04 Blocker**:
  - Thread 1 (`prio=1`) busy-spins in `rozu_00244410` (`pc=0x244770`, `ra=0x24472c`) waiting on a sound command completion counter while sound worker Thread 4 (`entry=0x2492b0`, `pc=0x24c168`, `prio=5`, `status=1` Ready) is starved by Thread 1's lower numeric priority (`1 < 5`). Investigating why Thread 1 is at `prio=1` when `main` (`0x20463c`) sets priority `5` via `ChangeThreadPriority`.
  - Systemic function-split fallthroughs/delayed-prologue splits identified in `tools/generate_slus21448_toml.py` remain to be regenerated cleanly into `config/slus_21448.csv` before committing M04.

> For full hardware constraints, SHA/CRC details, and session continuity, see [`handoff.txt`](handoff.txt) and [`gemini_flash/README.txt`](gemini_flash/README.txt).

---

## Upstream PS2Recomp: PlayStation 2 Static Recompiler (Experimental)

[![Discord](https://img.shields.io/badge/Discord-Join%20Server-5865F2?logo=discord&logoColor=white)](https://discord.gg/JQ8mawxUEf)

Also check our [WIKI](https://github.com/ran-j/PS2Recomp/wiki)


This project statically recompiles PS2 ELF binaries into C++ and provides a runtime to execute the generated code.

### Modules

* `ps2xAnalyzer`: scans ELF/functions and writes TOML config (`stubs`, `skip`, instruction patches).
* `ps2xRecomp`: reads TOML + ELF, decodes R5900 instructions, and generates C++ output.
* `ps2xRuntime`: hosts memory, function registration, syscall dispatch, and hardware stubs.
* `ps2xIOP`: R3000A IRX execution, a virtual IOP kernel, and generic HLE fallbacks.

### Features

* Translates MIPS R5900 instructions to C++ code
* PS2-specific MMI and VU0 macro support.
* Single-file or multi-file output.
* Configurable stubs, skips, and instruction patches.
* Instruction-driven syscall handling.

### How It Works
PS2Recomp works by:

* Parsing a PS2 ELF file to extract functions, symbols, and relocations
* Decoding the MIPS R5900 instructions in each function
* Translating those instructions to equivalent C++ code
* Generating a runtime that can execute the recompiled code

The translated code is very literal, with each MIPS instruction mapping to a C++ operation. For example, `addiu $r4, $r4, 0x20` becomes `ctx->r4 = ADD32(ctx->r4, 0X20);`.

### Current Behavior

* `stubs` entries generate wrappers that call known runtime syscall/stub handlers by name.
* `stubs` also supports address bindings with `handler@0xADDRESS` for stripped games (for example `sceCdRead@0x00123456`).
* Address bindings also support generic return handlers for triage: `ret0`, `ret1`, `reta0`.
* Recompiler now tries relocation-symbol auto-binding at callsites (`J/JAL`) before raw address dispatch; when relocation symbol is known (for example `sceCdRead`), it can call runtime handlers without manual address mapping.
* Recompiler discovers additional internal static entry targets and emits `entry_...` wrappers for those addresses.
* For unresolved static `J/JAL` sites, generated code falls back to `runtime->lookupFunction(0x...)`.
* `skip` entries are not recompiled and generate explicit `ps2_stubs::TODO_NAMED(...)` wrappers.
* Recompiled `SYSCALL` now calls `runtime->handleSyscall(...)` with the encoded syscall immediate.
* Runtime syscall dispatch tries encoded syscall ID first, then falls back to `$v1`.

### Requirements

* CMake 3.20+
* C++20 compiler (currently tested mainly with MSVC)
* SSE4/AVX host support for some vector paths

### Build

```bash
git clone --recurse-submodules https://github.com/ran-j/PS2Recomp.git
cd PS2Recomp

cmake -S . -B out/build
cmake --build out/build --config Debug
```

### Usage

Preferred workflow for retail or stripped games:

1. Open the ELF in Ghidra.
2. Run `ps2xRecomp/tools/ghidra/ExportPS2Functions.java`.
3. Use the exported TOML and CSV map.
4. Recompile with the exported TOML:

```bash
./ps2_recomp config.toml
```

Fallback workflow for quick local experiments or ELFs with debug symbol :

```bash
./ps2_analyzer your_game.elf config.toml
```

See the [Ghidra Workflow](ps2xAnalyzer/Readme.md#3-ghidra-integration-for-retail-and-stripped-games-preferred) for ghdira instructions.

Then build generated output and link with `ps2xRuntime`.

### Configuration

Main fields in `config.toml`:

* `general.input`: source ELF path.
* `general.ghidra_output`: recommended function map CSV exported from Ghidra.
* `general.output`: generated C++ output folder.
* `general.single_file_output`: one combined cpp or one file per function.
* `general.low_memory_mode`: reduce peak output-generation memory by avoiding retained disassembly strings and forcing serial output generation. Generated instruction comments are still emitted; disassembly text is produced while writing each output file instead of being kept in memory.
* `general.output_worker_threads`: number of output-generation workers (clamped to nproc * 2). A positive value uses exactly that many workers. `0` uses `nproc - 1` when at least two hardware threads are available, otherwise serial output generation. `1` forces serial output generation.
* `general.patch_syscalls`: apply configured patches to `SYSCALL` instructions (`false` recommended).
* `general.patch_cop0`: apply configured patches to COP0 instructions.
* `general.patch_cache`: apply configured patches to CACHE instructions.
* `general.stubs`: names to force as stubs. Also accepts `handler@0xADDRESS` to bind a stripped function address directly to a runtime syscall/stub handler. Includes generic handlers `ret0`, `ret1`, `reta0`.
* `general.skip`: names to force as skipped wrappers.
* `patches.instructions`: raw instruction replacements by address.

Address binding for stripped ELFs:

* Use `handler@0xADDRESS` inside `general.stubs` to map a stripped function start directly to a runtime handler.
* Example: `sceCdRead@0x00123456` binds function start `0x00123456` to `ps2_stubs::sceCdRead(...)`.
* Generic temporary handlers are available: `ret0@0xADDR`, `ret1@0xADDR`, `reta0@0xADDR`.
* Before manual binding, prefer recompilation from a Ghidra-exported TOML/CSV first. The extra boundaries and synthetic entry points are usually more important than manual early triage.
* The address must be the function start in that exact ELF build.
* Addresses are not portable across different games/regions/builds.
* The handler name must exist in runtime call lists (`PS2_SYSCALL_LIST` or `PS2_STUB_LIST`).

Example:

```toml
# stripped function binding by address:
stubs = ["sceCdRead@0x00123456", "SifLoadModule@0x00127890"]
# temporary return handlers:
stubs = ["ret0@0x001D9410", "ret1@0x001D5BC8", "reta0@0x0024B7C0"]
# mixed example:
stubs = ["printf", "sceCdRead@0x00123456", "SifLoadModule@0x00127890"] 
```

### Runtime

To execute the recompiled code.

`ps2xRuntime` currently provides:

* Guest memory model and function dispatch table.
* Some syscall dispatcher with common kernel IDs.
* Basic GS/VU/file/system stubs.
* Foundation to expand and port your game.
* `ps2xIOP` execution of original IRX modules with generic HLE fallbacks.

See [IOP emulation](ps2xIOP/README.md) for module execution and the service boundary.

### Game Override Hooks

Game overrides are runtime-side, build-scoped patch modules.

A game override is C++ code that runs during `loadELF` and can replace EE function bindings by address for one specific game build. IOP RPC/DMA behavior is handled by the `ps2xIOP` emulator and its runtime transport. This is separate from recompilation output and separate from global runtime stubs/syscalls.

API:

* Header: `ps2xRuntime/include/game_overrides.h`
* Register macro: `PS2_REGISTER_GAME_OVERRIDE(name, elfName, entry, crc32, applyFn)`
* Direct bind helper: `ps2_game_overrides::bindAddressHandler(runtime, addr, "handler")`

Use Game Override modules when:

* You need per-game/per-build routing or patches without polluting global behavior.
* You need to bind many addresses, or install custom replacement logic for a specific title.

#### Recommended Iteration Loop

1. Run with minimal config and no aggressive skipping.
2. Fix hard blockers first (`function not found`, syscall TODO, critical IO stubs).
3. Use temporary return stubs only to classify call importance.
4. Promote temporary fixes to real implementations.
5. Move per-game hacks into game overrides keyed by ELF metadata.
6. Re-test from cold boot after each batch.

### Describing Your Game Project

A game project built with PS2Recomp can describe itself in a `.recomp.json` file at the root of its repository. Lists of recomp and decomp projects, such as [recomp.board](https://recomp.fyi), read that file instead of guessing the game, system and status from the README.

> [!NOTE]
> This file is optional: PS2Recomp does not read it and works the same without it. `.recomp.json` and recomp.board are third-party projects; the PS2Recomp developers have no ties to them.

Starter file:

```json
{
  "$schema": "https://recomp.fyi/schema/v1.json",
  "game": "<title as it shipped>",
  "system": "PS2",
  "type": "recomp",
  "toolchain": "PS2Recomp",
  "status": "in-progress",
  "original": { "region": "USA", "serial": "SLUS-20312" }
}
```

* `original` is the release a user must own. On retail discs the ELF is named after the serial (`SLUS_203.12` is `SLUS-20312`), and the prefix gives the region: `SLUS`/`SCUS` USA, `SLES`/`SCES` Europe, `SLPS`/`SLPM`/`SCPS` Japan.
* `status` is one of `exploring`, `in-progress`, `playable`, `released`, `complete`, `paused`. Edit it when the project moves on: a stale status is worse than none.
* Never put a game file, or a link to one, in the file.

Other fields (Wikidata item, target platforms, maintainers, links, what help is wanted) and the JSON Schema are in the [specification](https://recomp.fyi/spec).

### Limitations
 
* Performance is very bad for VU and GS
* Hardware emulation is partial and many paths are stubbed.

###  Acknowledgments

* Inspired by N64Recomp
* Uses ELFIO for ELF parsing
* Uses toml11 for TOML parsing
* Uses fmt for string formatting
* Reference for runtime PCSX2