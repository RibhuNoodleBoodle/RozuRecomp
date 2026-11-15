# 03 — Sources, Prior Art, and Clean-Room Symbol Provenance

## 1. Inspected Repositories & Commit Provenance

| Source | URL / Location | Verified Commit SHA / Date | License | Role in RozuRecomp |
| :--- | :--- | :--- | :--- | :--- |
| **PS2Recomp (Upstream & Local Fork)** | `https://github.com/ran-j/PS2Recomp.git` / `/mnt/6421-8598/building/RozuRecomp` | `e5636981a1c9de368f6b71e819c3dc188dfedbf4` (`2026-10-23`) | `GPL-3.0` (`LICENSE`) | Primary analyzer (`ps2xAnalyzer`), static recompiler (`ps2xRecomp`), IOP emulator (`ps2xIOP`), runtime (`ps2xRuntime`), and test suite (`ps2xTest`). |
| **PS2Recomp Official Wiki** | `https://github.com/ran-j/PS2Recomp.wiki.git` | `19913d78ba89adec620d6571856a76c8c9a8aa14` | `GPL-3.0` (project documentation) | Official reference for TOML configuration schema, Ghidra `ExportPS2Functions.java` workflow, and runtime stub/syscall architecture. |
| **Rule of Rose Decompilation (`notmanrivera/ruleofrose-decomp`)** | `https://github.com/notmanrivera/ruleofrose-decomp.git` | `70d9bcf9621a909083b695eaba4396237341fd8b` (`2026-11-15`) | **No `LICENSE` file present** (Default copyright / All Rights Reserved on author's expressive code) | **Clean-room factual reference ONLY** (verified against identical `SLUS_214.48` SHA-1 `f9abd6dc53070750dfcae3b44184fb9852e603fb`). Used strictly to cross-verify factual function boundary addresses and hardware behavior. **NO C++ source files from this repository may be copied into RozuRecomp.** |

---

## 2. Clean-Room & Licensing Policy

Because `notmanrivera/ruleofrose-decomp` (`70d9bcf9621a909083b695eaba4396237341fd8b`) does not contain an open-source `LICENSE` file:
1. **Strict Prohibition on Copying Decompiled Source**: Neither Argon nor Flash may copy, paste, or adapt C/C++ implementation files (`src/*.cpp`, `include/*.h`) from `ruleofrose-decomp` into `RozuRecomp`. All guest game logic in `RozuRecomp` MUST be generated mechanically by `ps2xRecomp` from the user's own `SLUS_214.48` binary on `/mnt/6421-8598/building/RozuRecomp/Rule of Rose (USA).iso`.
2. **Permissible Factual Metadata & Clean-Room Verification**:
   * Hardware facts (which Sony SDK library calls `SLUS_214.48` invokes, GS display modes, DMA channel numbers, and asset header magic bytes) are uncopyrightable facts of the binary.
   * Function start/end addresses in `SLUS_214.48` are factual instruction boundaries in the user's executable and can be derived directly from the user's `SLUS_214.48` ELF via five independent mechanisms documented in Section 3 below.

---

## 3. Five-Source Symbol & Function Boundary Provenance for `SLUS_214.48`

Even though `SLUS_214.48` has no `.symtab` section, **100% of its executable code boundaries** can be recovered and verified from the binary itself plus `PS2Recomp`'s built-in database:

### Source 1: ELF Section Header Table — `1,449` `.gnu.linkonce.t.*` Functions (`100%` Exact Names & Sizes)
The Sony PS2 `ee-gcc` 2.95.2/2.95.3 linker emitted template instantiations, inline C++ methods, and virtual destructors into individual `.gnu.linkonce.t.<mangled_name>` ELF sections (`Sections [2..1405]` at `0x00280E88`–`0x0029122C` and `Sections [1407..1451]` at `0x002953B0`–`0x00295EB8`), and preserved the full section header string table (`.shstrtab`, Section `[1794]`).
* Every single one of these **1,449 sections** has its exact virtual start address (`sh_addr`), exact byte length (`sh_size`), and original GCC2 mangled C++ symbol name right in `SLUS_214.48`'s ELF section table!
* Examples verified directly from `readelf -SW SLUS_214.48`:
  * `[  2] .gnu.linkonce.t.__tfQ23utl10CAllocater` (`0x00280e88`, size `0x38`)
  * `[117] .gnu.linkonce.t._._9MagSystem` (`0x002821c0`, size `0x28`)
  * `[1407] .gnu.linkonce.t.__t13CStageDataMan1Z9CLightSeti` (`0x002953b0`, size `0x38`)
* **Critical Note on `ElfParser`**: `ps2xRecomp/src/lib/elf_parser.cpp` (`ElfParser::loadSections()`) iterates over ELF sections and marks `.gnu.linkonce.t.*` as `isCode = true`, but `ElfParser::loadSymbols()` only reads `SHT_SYMTAB`! Therefore, Flash M02 MUST extract all 1,449 `.gnu.linkonce.t.*` section starts/sizes (or patch `ElfParser` to register `.gnu.linkonce.t.*` sections as `Function` entries when `SHT_SYMTAB` is absent).

### Source 2: ELF Section Header Table — `284` `.gnu.linkonce.d._vt$*` C++ Virtual Tables
`Sections [1457..1741]` (`0x002E0A80`–`0x002E5300`) are **284 named GCC2 C++ virtual method tables** (e.g., `.gnu.linkonce.d._vt$9MagSystem`, `.gnu.linkonce.d._vt$Q23emy8CEnemyAi`, `.gnu.linkonce.d._vt$11CRpkDataMan`).
* In GCC 2.95 ABI (`-fvtable-thunks` or standard `{delta, index, pfn}` 8-byte/4-byte entries), every virtual function pointer stored in `.gnu.linkonce.d._vt$*`, `.data` (`0x00295F00`–`0x002E014C`), and `.rodata` (`0x002E5300`–`0x00307F70`) points directly to a valid R5900 function entry point in `.text` or `.gnu.linkonce.t.*`.

### Source 3: `.ctors` (`0x002E014C`), `.dtors` (`0x002E0164`), and `.eh_frame` (`0x002E0178`)
* `.ctors` (`0x002E014C`, `0x18` bytes) contains 4 global constructor function pointers (`_GLOBAL_$I$...` at `0x00138BE0`, `0x001AE530`, `0x001CC290`, `0x0024B2D8`), invoked by `__do_global_ctors` (`0x00280E38`) during `main` startup.
* `.eh_frame` (`0x002E0178`, `0x904` bytes) and `.gcc_except_table` (`0x00307F80`, `0x7C` bytes) contain DWARF Frame Description Entries (FDEs) for GCC2 exception-handling / `libgcc2` functions at the end of `.text`.

### Source 4: Sony SDK / Newlib / `libgcc2` Signature Database (`0x0024B490`–`0x00280E88`, `648` Functions)
* `ps2xAnalyzer/include/ps2xAnalyzer/sce_symbol_database_data.h` in `PS2Recomp` contains byte-pattern signatures for Sony PS2 SDK libraries (`libkernel`, `libcdvd`, `libdma`, `libgraph`, `libpad2`, `libdbc`, `libvib`, `libmc`, `libmpeg`, `libipu`, `libsdr`, `libvu0`, `libpc`, Newlib `libc`/`libm`, and `libgcc2`).
* In `SLUS_214.48`, the entire region from `0x0024B490` (`WaitSema` / syscalls) to `0x00280E88` (`__do_global_ctors`) consists of **648 standard Sony SDK, Newlib, and `libgcc2` functions**.
* Identifying these 648 functions allows `ps2xRecomp` and `ps2_game_overrides` to bind runtime stubs (`sceCd*`, `sceDma*`, `sceGs*`, `sceMc*`, `sceMpeg*`, `scePad2*`, `sceDbc*`, `sceVib*`, `sceSd*`, `sceSif*`, `malloc_r`, `free_r`, `memcpy`, `memset`, `printf`, etc.) by exact address even though `.symtab` is stripped!

### Source 5: `.text` Direct Call (`JAL`), Branch, Function Pointer, and Prologue Analysis (`0x00100000`–`0x0024B490`, `~6,866` Game/Engine Functions)
* Every R5900 `JAL` target, `ADDIU $sp, $sp, -frame` prologue, `JR $ra` epilogue, `.data`/`.rodata` function pointer table (including `CSequenceCode` command handler tables at `0x001AE570`+ and task state tables), and tail-call boundary in `.text` (`0x00100000`–`0x0024B490`) defines the `~6,866` game and middleware functions (`bed`, `utl`, `dog`, `mag`, `emy`, `game`, `task`, `sequence`, `mw/i3d`, `mw/sound`).
* Combined with the `648` SDK functions (`0x0024B490`–`0x00280E88`) and `1,449` `.gnu.linkonce.t.*` functions (`0x00280E88`–`0x00291230`, `0x002953B0`–`0x00295EB8`), the total verified R5900 function count is **~8,963 functions**, with **zero functions in `.vutext` (`0x00291230`–`0x002953B0`)**.

---

## 4. Key SDK & Engine Function Addresses in `SLUS_214.48` (`CRC32 0x8cf7b024`)

The table below lists critical verified entry points in `SLUS_214.48` that Flash M02–M08 will use for TOML configuration and `ps2_game_overrides`:

| Subsystem | Symbol / Function Name | Virtual Address | Size (Bytes) | Disposition in `PS2Recomp` |
| :--- | :--- | :--- | ---: | :--- |
| **CRT0 / Entry** | `_start` / `entry` | `0x00100008` | `0x110` | Recompile (initializes BSS, stack, calls `main`) |
| **Main** | `main` | `0x001002D0` | `0xC0` | Recompile (calls `MagSystem::getInstance()`, `initialize()`, `run()`, `terminate()`) |
| **Global Ctors** | `__do_global_ctors` | `0x00280E38` | `0x50` | Recompile (iterates `.ctors` at `0x002E014C`) |
| **Bed / System** | `bedInitSystem` | `0x001005E0` | `0x1AC` | Recompile (reboots IOP with `IOPRP300.IMG`, loads 8 IRX modules from `IOPCONF.CNF`) |
| **Bed / Pad (`libpad2`)** | `BedPad::initialize` | `0x00101BC8` | `0x118` | Recompile (calls `sceDbcInit`, `scePad2Init`, `scePad2CreateSocket`) |
| **Bed / Pad (`libpad2`)** | `BedPad::update` | `0x00101DF0` | `0x2F0` | Recompile (calls `scePad2GetState`, `scePad2Read`, `sceVibSetActParam`) |
| **MagSystem** | `vsyncHandler` | `0x00117654` | `0xA0` | Recompile (VSync callback: increments counter, calls `iSignalSema(m_v_sema)` every `m_v_rate=2` VSyncs) |
| **MagSystem** | `MagSystem::initialize` | `0x00117AA0` | `0x460` | Recompile (sets up GS `512x448`, `m_v_sema`, `sceGsSyncVCallback`, VIF1/GIF DMA channels) |
| **MagSystem** | `MagSystem::run` | `0x00117FC8` | `0x80` | Recompile (main game loop calling `update()` while `m_active`) |
| **MagSystem** | `MagSystem::update` | `0x001182DC` | `0x478` | Recompile (ticks tasks, reads `*T0_COUNT`, sends DMA, calls `waitVSync()`, swaps DBuffDc) |
| **MagSystem** | `MagSystem::waitVSync` | `0x00118754` | `0x1D0` | Recompile (polls `sceDmaSync(m_dma, 1, 0)`, waits on `m_v_sema` via `WaitSema`, calls `sceGsSyncPath(0,0)`) |
| **Script VM** | `CSequenceCode::update` | `0x001AE7C8` | `0x430` | Recompile (executes `ELFR101` bytecode instructions for cutscenes/events/progression) |
| **`libgraph` (SDK)** | `sceGsResetGraph` | `0x00252C20` | `0x158` | Bind to `ps2_stubs::sceGsResetGraph` |
| **`libgraph` (SDK)** | `sceGsSetDefDBuffDc` | `0x002531A8` | `0x228` | Bind to `ps2_stubs::sceGsSetDefDBuffDc` |
| **`libgraph` (SDK)** | `sceGsSwapDBuffDc` | `0x002533D0` | `0x228` | Bind to `ps2_stubs::sceGsSwapDBuffDc` |
| **`libgraph` (SDK)** | `sceGsSyncV` | `0x00253DF0` | `0x68` | Bind to `ps2_stubs::sceGsSyncV` |
| **`libgraph` (SDK)** | `sceGsSyncVCallback` | `0x00253E58` | `0x68` | Bind to `ps2_stubs::sceGsSyncVCallback` |
| **`libgraph` (SDK)** | `sceGsSyncPath` | `0x00253FA8` | `0x140` | Bind to `ps2_stubs::sceGsSyncPath` |
| **`libdma` (SDK)** | `sceDmaReset` | `0x00252360` | `0x90` | Bind to `ps2_stubs::sceDmaReset` |
| **`libdma` (SDK)** | `sceDmaGetChan` | `0x002524C8` | `0x40` | Bind to `ps2_stubs::sceDmaGetChan` |
| **`libdma` (SDK)** | `sceDmaSend` | `0x002526B8` | `0x88` | Bind to `ps2_stubs::sceDmaSend` |
| **`libdma` (SDK)** | `sceDmaSync` | `0x00252930` | `0x138` | Bind to `ps2_stubs::sceDmaSync` |
| **`libpad2` (SDK)** | `scePad2Init` | `0x0026DF00` | `0x140` | Bind to new `scePad2Init` override in `Pad.cpp` / `game_overrides` |
| **`libpad2` (SDK)** | `scePad2End` | `0x0026E040` | `0x88` | Bind to new `scePad2End` override |
| **`libpad2` (SDK)** | `scePad2CreateSocket` | `0x0026E168` | `0x150` | Bind to new `scePad2CreateSocket` override |
| **`libpad2` (SDK)** | `scePad2DeleteSocket` | `0x0026E2B8` | `0x108` | Bind to new `scePad2DeleteSocket` override |
| **`libpad2` (SDK)** | `scePad2Read` | `0x0026E3C0` | `0xF0` | Bind to new `scePad2Read` override (writes 32-byte DualShock 2 state to guest buffer) |
| **`libpad2` (SDK)** | `scePad2GetState` | `0x0026E4B0` | `0xE8` | Bind to new `scePad2GetState` override (returns `SCE_PAD2_STATE_STABLE = 6`) |
| **`libdbc` (SDK)** | `sceDbcInit` | `0x0026FC88` | `0xF0` | Bind to new `sceDbcInit` override (returns `1`) |
| **`libdbc` (SDK)** | `sceDbcEnd` | `0x0026FD78` | `0x70` | Bind to new `sceDbcEnd` override (returns `1`) |
| **`libvib` (SDK)** | `sceVibGetProfile` | `0x002703A8` | `0x120` | Bind to safe no-op stub returning `1` |
| **`libvib` (SDK)** | `sceVibSetActParam` | `0x002705A8` | `0x160` | Bind to safe no-op stub returning `1` |
| **`libmc` (SDK)** | `sceMcInit` .. `sceMcSync` | `0x0026BE60`–`0x0026DC50` | Various | Bind to `ps2_stubs::sceMc*` (`ps2_call_list.h:421-441`) |
| **`libmpeg` (SDK)** | `sceMpegInit` .. `sceMpegGetPicture` | `0x00255E10`–`0x00258E00` | Various | Bind to `ps2_stubs::sceMpeg*` (`ps2_call_list.h:442-465`) |
| **`libcdvd` (SDK)** | `sceCdInit` .. `sceCdSync` | `0x00267D38`–`0x0026BD00` | Various | Bind to `ps2_stubs::sceCd*` (`ps2_call_list.h:288-326`) |
| **`libsdr` (SDK)** | `sceSdRemoteInit`, `sceSdRemote` | `0x00270A20`–`0x00270E00` | Various | Bind to `ps2_stubs::sceSdRemoteInit` / `sceSdRemote` (`ps2_call_list.h:513-516`) |
