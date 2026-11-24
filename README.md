# RozuRecomp

Native PC static recompilation port of **Rule of Rose** (PlayStation 2, NTSC-U `SLUS-21448` v1.00).

> **Current Status:** **M01 skeleton — not yet booted or playable.**  
> Core host utilities, CMake presets, and the pinned `External/PS2Recomp` engine/test suite are active; disc profile generation, `SLUS_214.48` static recompilation, and runtime bring-up follow in M02+.

## Legal & Media Notice

This repository contains **source code and build tooling only**. No copyrighted game binaries, disc images, BIOS dumps, audio/video assets, or generated game C++ sources are included or committed. You must supply your own legally owned **Rule of Rose (USA, NTSC-U, `SLUS-21448` v1.00)** disc image in `Game/` (see [Game/PLACE-YOUR-ISO-HERE.txt](Game/PLACE-YOUR-ISO-HERE.txt)).

## Supported Targets

- **Primary Deployment Target:** Windows x64 (MSVC, Visual Studio 2022+ / Ninja)
- **Local Dev / Test Target:** Linux x64 (GCC 12+ / Ninja, headless & CPU GS `GSCpuBackend`; GPU OpenGL backend in `PS2Recomp` is currently WGL-only on Windows)

## Quick Build (Current M01 Baseline)

### Linux (GCC + Ninja)
```bash
git submodule update --init --recursive
cmake --preset linux-gcc
cmake --build build/linux --target ps2_recomp ps2_analyzer vu1_recomp rozu_host_lib rozu_host_unit_test ps2x_tests ps2_iop_emulator_tests
ctest --test-dir build/linux --output-on-failure
```

### Windows x64 (MSVC + Ninja)
```bat
git submodule update --init --recursive
configure.bat
build.bat rozu_host_unit_test
```

## License & Attribution

Licensed under the **GNU General Public License v3.0** (see [LICENSE](LICENSE)).

Adapted from and built upon:
- [LightVelox/sotc-vibe-pc](https://github.com/LightVelox/sotc-vibe-pc) (GPL-3.0) — host architecture, diagnostic utilities, and static recompilation workflow patterns
- [LightVelox/PS2Recomp](https://github.com/LightVelox/PS2Recomp) (GPL-3.0) — R5900 static recompiler, `ps2xAnalyzer`, `ps2xRuntime`, `ps2xIOP`, and `ps2xTest`
- [ran-j/PS2Recomp](https://github.com/ran-j/PS2Recomp) (GPL-3.0) — upstream PS2 static recompiler
- Third-party dependencies fetched by `External/PS2Recomp`: `raylib` (zlib/libpng), `ELFIO` (MIT), `rabbitizer` (MIT), `fmt` (MIT), `toml11` (MIT), `libdwarf` (LGPL), `nlohmann/json` (MIT), and `FFmpeg` (LGPL when enabled)
