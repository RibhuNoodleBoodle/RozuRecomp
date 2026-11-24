cmake_minimum_required(VERSION 3.21)

project(RozuRecomp LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if((CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang") AND (CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64|amd64|i.86"))
    add_compile_options(-msse4.1)
endif()

option(PS2X_BUILD_TEST "Build PS2Recomp and RozuRecomp unit tests" ON)
if(PS2X_BUILD_TEST)
    enable_testing()
    set(PS2X_IOP_BUILD_TESTS ON CACHE BOOL "" FORCE)
endif()

set(PS2X_BUILD_RECOMP ON CACHE BOOL "" FORCE)
set(PS2X_BUILD_RUNTIME ON CACHE BOOL "" FORCE)
set(PS2X_BUILD_ANALYZER ON CACHE BOOL "" FORCE)
set(PS2X_BUILD_STUDIO OFF CACHE BOOL "" FORCE)
set(PS2X_ENABLE_DEBUG_UI OFF CACHE BOOL "" FORCE)
set(PS2X_ENABLE_AGRESSIVE_LOGS OFF CACHE BOOL "" FORCE)
set(PS2X_ENABLE_SCCACHE OFF CACHE BOOL "" FORCE)

set(ROZU_FFMPEG_DEFAULT OFF)
if(WIN32)
    set(ROZU_FFMPEG_DEFAULT ON)
else()
    find_package(PkgConfig QUIET)
    if(PkgConfig_FOUND)
        pkg_check_modules(ROZU_FFMPEG_PROBE QUIET
            libavcodec
            libavformat
            libavutil
            libswresample
            libswscale
        )
        if(ROZU_FFMPEG_PROBE_FOUND)
            set(ROZU_FFMPEG_DEFAULT ON)
        endif()
    endif()
endif()

option(ROZU_ENABLE_FFMPEG "Enable FFmpeg-backed MPEG video decoding for .PSS FMVs" ${ROZU_FFMPEG_DEFAULT})
set(PS2X_ENABLE_FFMPEG ${ROZU_ENABLE_FFMPEG} CACHE BOOL "" FORCE)

add_subdirectory(External/PS2Recomp EXCLUDE_FROM_ALL)

if(NOT TARGET vu1_recomp)
    add_executable(vu1_recomp EXCLUDE_FROM_ALL External/PS2Recomp/ps2xTest/tools/vu1_recomp.cpp)
    target_link_libraries(vu1_recomp PRIVATE ps2_runtime)
    target_include_directories(vu1_recomp PRIVATE External/PS2Recomp/ps2xRuntime/src/lib/vu)
endif()

add_subdirectory(Port)
