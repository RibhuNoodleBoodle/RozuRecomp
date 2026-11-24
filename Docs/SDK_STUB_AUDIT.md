# Rule of Rose (SLUS-21448 v1.00) — SDK Stub Audit

Policy (`ADR-005`, `Port/recomp/rozu.toml`):
- `auto_stub_by_name = false`, `direct_tail_calls = false`, `patch_syscalls = false`, `patch_cop0 = false`, `patch_cache = false`.
- Only hardware/IOP/RPC/CDVD/MC/FIO/TTY/MPEG/IPU/DECI2 boundaries present in `SLUS_214.48` AND resolved in `External/PS2Recomp/ps2xRuntime/include/ps2_call_list.h` are stubbed.
- Genuine EE code—newlib C/math/heap (`malloc`, `free`, `cos`, `sin`, `memcpy`, etc.), `libdma`, `libgraph` (`sceGs*`), `libvu0` (`sceVu0*`), `sceDev*`, EE `libkernl` syscall stubs (`0x0025D4C0..0x0025DD58`), game math functions (`0x00236AC8`..`0x00237788` misidentified by `ps2_analyzer`), and `.gnu.linkonce.t.*` C++ methods—remain recompiled.

## 1. Rejected `ps2_analyzer` False Positives & Intentionally Unstubbed Libraries

| Range / Address | Analyzer Candidate | Decision | Evidence & Rationale |
|---|---|---|---|
| `0x00236AC8..0x00237788` | `sceVu0ClampVector`, `sceVu0TransposeMatrix` | **Keep recompiled** | Game math routines well below SCE SDK region (`< 0x0024B000`); real `libvu0` resides at `0x0025B658..0x0025C2B0`. |
| `0x00258F78..0x0025AD08` | `sceGs*` (`libgraph`) | **Keep recompiled** | Direct EE GS/GIF packet builders & privileged MMIO writes (`ADR-005`). |
| `0x0025AF68..0x0025B5A8` | `sceDma*` (`libdma`) | **Keep recompiled** | Direct EE DMAC channel register writes (`ADR-005`). |
| `0x0025B658..0x0025D448` | `sceVu0*`, `sceDevVu0*`, `sceDevVu1*`, `sceDevVif0*`, `sceDevVif1*` | **Keep recompiled** | Pure EE MMI/COP2/VIF register operations (`ADR-005`). |
| `0x0025D4C0..0x0025DD58`, `0x0025E438..0x0025E7A0` | `InitThread`, `StartThread`, `iWakeupThread`, `DelayThread`, `InitTLB`, `InitAlarm` | **Keep recompiled** | `libkernl` `syscall` wrappers; `patch_syscalls = false` lowers `syscall` opcodes directly to `ps2_syscalls::*`. |
| `malloc`, `free`, `calloc`, `memcpy`, `memclr`, `sbrk`, math | Newlib / libm | **Keep recompiled** | Runs natively in guest RDRAM without crossing IOP/host boundary. |

## 2. Verified Boundary Stubs (`Port/recomp/rozu.toml`)

### 2.1 `libcdvd` (`0x0024B490..0x0024D130`)
Evidence: `SLUS_214.48` embeds `"libcdvd 3000"`, `"cdvdman.irx"`, `"cdvdfsv.irx"`, SIF RPC IDs `0x80000592` (`sceCdInit`), `0x80000597` (`sceCdLayerSearchFile`), `0x8000059C` (`sceCdDiskReady`), and `"cdvd bind err CdSearchFile"`.

| Address | Symbol | Evidence | Why Stubbed |
|---|---|---|---|
| `0x0024B490` | `sceCdCallback` | `ps2_analyzer` + `"sceCdCbfunc= %d sceCdCbfunc_num= %d"` | CDVD EE callback registration |
| `0x0024B668` | `sceCdInitEeCB` | `ps2_analyzer` CDVD block | CDVD EE callback thread setup (IOP RPC) |
| `0x0024BD98` | `sceCdSearchFile` | Wrapper calling `sceCdLayerSearchFile@0x0024BA98` with layer `0` | Disc ISO filesystem lookup |
| `0x0024BF10` | `sceCdNcmdDiskReady` | `ps2_analyzer` + `jal sceCdSync` | Non-blocking disc readiness check via IOP RPC |
| `0x0024BFA8` | `sceCdSync` | `ps2_analyzer` (4 direct `jal` callers) | Synchronize CDVD read/command queue |
| `0x0024C048` | `sceCdSyncS` | `ps2_analyzer` (3 direct `jal` callers) | Synchronize S-command |
| `0x0024C2C0` | `sceCdInit` | `ps2_analyzer` + RPC bind `0x80000592` | CDVD RPC initialization |
| `0x0024C7C0` | `sceCdDiskReady` | `ps2_analyzer` + RPC bind `0x8000059C` | Blocking disc readiness RPC |
| `0x0024C9E0` | `sceCdRead` | `ps2_analyzer` CDVD read path | ISO LBA sector read into guest RDRAM |
| `0x0024CC58` | `sceCdGetDiskType` | `ps2_analyzer` (2 callers) | Disc media type query (DVD/CD) |
| `0x0024CC80` | `sceCdGetError` | `ps2_analyzer` (2 callers) | Last CDVD error code |
| `0x0024CD18` | `sceCdStatus` | `ps2_analyzer` (1 caller) | Drive tray/spin status |
| `0x0024CF78` | `sceCdMmode` | `ps2_analyzer` (2 callers) | CD/DVD media mode selection |
| `0x0024D070` | `sceCdReadClock` | `ps2_analyzer` (1 caller) | PS2 RTC clock query via CDVD S-command |
| `0x0024D130` | `sceCdTrayReq` | `ps2_analyzer` (1 caller) | Disc tray check via CDVD S-command |

### 2.2 `libmc` (`0x0024D220..0x0024E948`)
Evidence: `ps2_analyzer` matches the full `libmc` SIF RPC suite (`mcman`/`mcserv` `0x80000400`). Stubbed so saves map cleanly to host memory card storage (`PS2Runtime` `MemoryCard.cpp`) without requiring IOP `mcserv.irx`.

- `sceMcInit@0x0024D220`, `sceMcEnd@0x0024D448`, `sceMcChangeThreadPriority@0x0024D4B0`, `sceMcGetSlotMax@0x0024D570`, `sceMcOpen@0x0024D630`, `sceMcMkdir@0x0024D758`, `sceMcClose@0x0024D790`, `sceMcSeek@0x0024D850`, `mceIntrReadFixAlign@0x0024D930`, `sceMcRead@0x0024D9E0`, `sceMcWrite@0x0024DAF8`, `sceMcSync@0x0024DC70`, `mceGetInfoApdx@0x0024DD38`, `sceMcGetInfo@0x0024DD90`, `sceMcGetDir@0x0024DF80`, `mceStorePwd@0x0024E0D0`, `sceMcChdir@0x0024E160`, `sceMcFormat@0x0024E2A0`, `sceMcDelete@0x0024E370`, `sceMcFlush@0x0024E490`, `sceMcSetFileInfo@0x0024E550`, `sceMcRename@0x0024E720`, `sceMcUnformat@0x0024E878`, `sceMcGetEntSpace@0x0024E948`.

### 2.3 `libmpeg` & `libipu` (`0x0024EB28..0x00253DC0`, `0x00269A38..0x00269D50`)
Evidence: `SLUS_214.48` embeds `"mpeg 3000"`, `"mpeg.cpp"`, `"sceMpegGetPicture was aborted"`, `"sceMpegSliceA0(): error happens"`. `libmpeg` relies heavily on IPU DMA/FIFO (`0x10002000`, DMA ch3/ch4) and hardware CSC/IDEC/BDEC; stubbed cleanly to `PS2Runtime` (`MPEG.cpp` / `IPU.cpp`).

- `sceMpegCreate@0x0024EB28`, `sceMpegInit@0x0024F6D0`, `sceMpegAddBs@0x0024F788`, `sceMpegGetPicture@0x0024F7C8`, `sceMpegGetPictureRAW8@0x0024F810`, `sceMpegReset@0x0024F868`, `sceMpegIsEnd@0x0024F8F8`, `sceMpegSetDecodeMode@0x0024F908`, `sceMpegGetDecodeMode@0x0024F920`, `sceMpegAddCallback@0x0024F940`, `sceMpegClearRefBuff@0x0024FAF8`, `sceMpegGetPictureRAW8xy@0x0024FB50`, `sceMpegSetDefaultPtsGap@0x0024FBA0`, `sceMpegResetDefaultPtsGap@0x0024FBB8`, `sceMpegDispWidth@0x0024FBE0`, `sceMpegDispHeight@0x0024FBF0`, `sceMpegIsRefBuffEmpty@0x0024FC20`, `sceMpegFlush@0x00250798` (`_sceMpegFlush`), `sceMpegDemuxPssRing@0x002539C0`, `sceMpegDemuxPss@0x00253DA0` (wrapper calling `sceMpegDemuxPssRing`), `sceMpegAddStrCallback@0x00253DC0`.
- `sceIpuStopDMA@0x00269A38`, `sceIpuRestartDMA@0x00269B20`, `sceIpuSync@0x00269C70`, `sceIpuInit@0x00269D50`.

### 2.4 POSIX I/O, TTY, `scePrintf`, `libfio` (`0x0025DEA8..0x00260110`, `0x002622B0..0x00263328`)
Evidence: `scePrintf@0x00260110` has 71 game callers (`kputchar`/`deci2Putchar` wrapper); `write@0x0025DEA8`/`read@0x0025DF28` wrap DECI2/FIO stdout/stdin; `sceFsInit..sceIoctl` (`0x002622B0..0x00263328`) are IOP FILEIO SIF RPC (`0x80000001`).

- `write@0x0025DEA8`, `read@0x0025DF28`, `sceTtyHandler@0x0025E9E8`, `sceTtyWrite@0x0025EB80`, `sceTtyRead@0x0025ECF8`, `sceTtyInit@0x0025EDC8`, `scePrintf@0x00260110`.
- `sceFsInit@0x002622B0`, `sceFsReset@0x00262548`, `sceOpen@0x002627B0`, `sceClose@0x00262A40`, `sceLseek@0x00262BB8`, `sceRead@0x00262DF8`, `sceWrite@0x00263068`, `sceIoctl@0x00263328`.

### 2.5 SIF / RPC / IOP Heap / Loadfile / DECI2 (`0x00260288..0x00261A60`, `0x002656D8..0x00266B58`, `0x00269710..0x002698F8`)
Evidence: EE-to-IOP DMA/FIFO/RPC transport (`0x80000003` IOPHEAP, `0x80000006` LOADFILE), called by Rule of Rose IOP loader (`0x00246030..0x00246274`, `"rxfile : Load module '%s'\n"` calling `sceSifLoadModule@0x00266628` at `0x00246120` and `sceSifRebootIop@0x00266B58`).

- SIF Cmd/RPC: `sceSifInitCmd@0x00260288`, `sceSifExitCmd@0x00260508`, `sceSifAddCmdHandler@0x00260570`, `sceSifRemoveCmdHandler@0x002605E8`, `sceSifSendCmd@0x00260770`, `sceSifCmdIntrHdlr@0x002607F0`, `sceSifWriteBackDCache@0x00260938`, `sceSifInitRpc@0x002609E8`, `sceRpcGetFPacket@0x00260C78`, `sceRpcGetFPacket2@0x00260CA8`, `sceSifGetOtherData@0x00260EC8`, `sceSifBindRpc@0x00261190`, `sceSifCallRpc@0x00261370`, `sceSifCheckStatRpc@0x00261570`, `sceSifSetRpcQueue@0x002615B0`, `sceSifRegisterRpc@0x00261648`, `sceSifRemoveRpc@0x00261718`, `sceSifRemoveRpcQueue@0x002617B0`, `sceSifGetNextRequest@0x00261840`, `sceSifExecRequest@0x00261898`, `sceSifRpcLoop@0x00261A60`.
- IOP Heap / Loadfile: `sceSifInitIopHeap@0x002656D8`, `sceSifAllocIopHeap@0x00265760`, `sceSifAllocSysMemory@0x002657D0`, `sceSifLoadIopHeap@0x002658E8`, `sceSifLoadFileReset@0x00265DB8`, `sceSifLoadModuleBuffer@0x002663C0` (wrapper calling `_sceSifLoadModuleBuffer@0x00265DF0`), `sceSifLoadModule@0x00266628` (3-arg wrapper calling `_sceSifLoadModule@0x00266400`), `sceSifLoadElfPart@0x00266668`, `sceSifLoadElf@0x00266790`, `sceSifGetIopAddr@0x002667B8`, `sceSifSetIopAddr@0x002668A8`, `sceSifResetIop@0x00266988`, `sceSifIsAliveIop@0x00266AE0`, `sceSifSyncIop@0x00266B08`, `sceSifRebootIop@0x00266B58` (`sceSifStopModule@0x00265FF8` omitted: 0 callers in `SLUS_214.48` and not in `PS2_STUB_LIST`).
- DECI2 host debug: `sceDeci2Open@0x00269710`, `sceDeci2Close@0x00269758`, `sceDeci2ReqSend@0x00269780`, `sceDeci2Poll@0x002697B0`, `sceDeci2ExRecv@0x00269830`, `sceDeci2ExSend@0x00269868`, `sceDeci2ExReqSend@0x002698A0`, `sceDeci2ExLock@0x002698D0`, `sceDeci2ExUnLock@0x002698F8`.
