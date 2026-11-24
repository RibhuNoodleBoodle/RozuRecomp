set(ROZU_HOST_SOURCES
    src/rozu/config.cpp
    src/rozu/debug_script.cpp
    src/rozu/diagnostics.cpp
    src/rozu/display.cpp
    src/rozu/function_hooks.cpp
    src/rozu/log.cpp
    src/rozu/sha256.cpp
    src/rozu/watchdog.cpp
)

if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/rozu/game_disc.cpp")
    list(APPEND ROZU_HOST_SOURCES src/rozu/game_disc.cpp)
endif()

add_library(rozu_host_lib STATIC ${ROZU_HOST_SOURCES})
target_include_directories(rozu_host_lib PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/src")
target_link_libraries(rozu_host_lib PUBLIC ps2_runtime)

if(WIN32)
    target_link_libraries(rozu_host_lib PRIVATE dbghelp)
endif()

if(MSVC)
    target_compile_options(rozu_host_lib PRIVATE /fp:precise /W3 /utf-8)
    target_compile_definitions(rozu_host_lib PUBLIC _CRT_SECURE_NO_WARNINGS)
elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(rozu_host_lib PRIVATE -fno-fast-math -ffp-contract=off -fno-associative-math -Wall -Wextra)
endif()

add_executable(rozu_host_unit_test
    tests/rozu_host_unit_test.cpp
    tests/test_function_table_stub.cpp
)
target_link_libraries(rozu_host_unit_test PRIVATE rozu_host_lib)
if(MSVC)
    target_compile_options(rozu_host_unit_test PRIVATE /fp:precise /W3 /utf-8)
elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(rozu_host_unit_test PRIVATE -fno-fast-math -ffp-contract=off -fno-associative-math -Wall -Wextra)
endif()
add_test(NAME rozu_host_unit_test COMMAND rozu_host_unit_test)

set(ROZU_GENERATED_DIR "${CMAKE_CURRENT_SOURCE_DIR}/generated")

if(NOT EXISTS "${ROZU_GENERATED_DIR}/register_functions.cpp" OR NOT EXISTS "${ROZU_GENERATED_DIR}/rozu_layout_generated.h")
    message(STATUS
        "Recompiled Rule of Rose game code not found in ${ROZU_GENERATED_DIR}; "
        "rozu_game_code and rozu targets will be enabled after Tools/generate.py produces it.")
    return()
endif()

file(GLOB ROZU_GENERATED_SOURCES CONFIGURE_DEPENDS "${ROZU_GENERATED_DIR}/*.cpp")

set(ROZU_GAME_CODE_LIBRARY "" CACHE FILEPATH "Reuse an unchanged generated EE library for host-only builds")
if(ROZU_GAME_CODE_LIBRARY)
    if(NOT EXISTS "${ROZU_GAME_CODE_LIBRARY}")
        message(FATAL_ERROR "Cached generated EE library does not exist: ${ROZU_GAME_CODE_LIBRARY}")
    endif()
    add_library(rozu_game_code STATIC IMPORTED)
    set_target_properties(rozu_game_code PROPERTIES IMPORTED_LOCATION "${ROZU_GAME_CODE_LIBRARY}")
    target_include_directories(rozu_game_code INTERFACE "${ROZU_GENERATED_DIR}")
    target_link_libraries(rozu_game_code INTERFACE ps2_runtime)
else()
    add_library(rozu_game_code STATIC ${ROZU_GENERATED_SOURCES})
    target_include_directories(rozu_game_code PUBLIC "${ROZU_GENERATED_DIR}")
    target_link_libraries(rozu_game_code PUBLIC ps2_runtime)
    set_target_properties(rozu_game_code PROPERTIES UNITY_BUILD OFF)
    target_precompile_headers(rozu_game_code PRIVATE
        "${CMAKE_SOURCE_DIR}/External/PS2Recomp/ps2xRuntime/include/ps2_runtime_macros.h"
        "${CMAKE_SOURCE_DIR}/External/PS2Recomp/ps2xRuntime/include/ps2_runtime.h"
        "${ROZU_GENERATED_DIR}/ps2_recompiled_functions.h"
        "${ROZU_GENERATED_DIR}/ps2_recompiled_stubs.h"
        "${CMAKE_SOURCE_DIR}/External/PS2Recomp/ps2xRuntime/include/ps2_syscalls.h"
        "${CMAKE_SOURCE_DIR}/External/PS2Recomp/ps2xRuntime/include/ps2_stubs.h"
    )
endif()

add_executable(rozu src/main.cpp)
target_include_directories(rozu PRIVATE src "${ROZU_GENERATED_DIR}")
target_link_libraries(rozu PRIVATE rozu_host_lib rozu_game_code ps2_runtime)

file(GLOB ROZU_VU1_SOURCES CONFIGURE_DEPENDS "${ROZU_GENERATED_DIR}/vu1/*.cpp")
if(ROZU_VU1_SOURCES)
    add_library(rozu_vu1_code STATIC ${ROZU_VU1_SOURCES})
    target_include_directories(rozu_vu1_code PRIVATE "${CMAKE_SOURCE_DIR}/External/PS2Recomp/ps2xRuntime/src/lib/vu")
    target_link_libraries(rozu_vu1_code PUBLIC ps2_runtime)
    target_link_libraries(rozu PRIVATE rozu_vu1_code)
    target_compile_definitions(rozu PRIVATE ROZU_HAS_VU1_PROGRAMS=1)
    if(MSVC)
        target_compile_options(rozu_vu1_code PRIVATE /bigobj /fp:precise /arch:AVX2 /W0 /MP $<$<CONFIG:RelWithDebInfo>:/Ob2>)
    elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(rozu_vu1_code PRIVATE -fno-fast-math -ffp-contract=off -fno-associative-math -w)
    endif()
    add_executable(rozu_vu1_bench tools/vu1_bench.cpp)
    target_include_directories(rozu_vu1_bench PRIVATE "${CMAKE_SOURCE_DIR}/External/PS2Recomp/ps2xRuntime/src/lib/vu")
    target_link_libraries(rozu_vu1_bench PRIVATE rozu_vu1_code ps2_runtime)
    set_target_properties(rozu_vu1_bench PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
    if(MSVC)
        target_compile_options(rozu_vu1_bench PRIVATE /fp:precise /W3 /utf-8)
    endif()
endif()

if(MSVC)
    if(NOT ROZU_GAME_CODE_LIBRARY)
        target_compile_options(rozu_game_code PRIVATE /bigobj /fp:precise /arch:AVX2 /GS- /d2OptimizeHugeFunctions /W0 /MP)
        set_source_files_properties("${ROZU_GENERATED_DIR}/register_functions.cpp" PROPERTIES COMPILE_OPTIONS "/Z7;/Ob0;/Od" SKIP_PRECOMPILE_HEADERS ON)
    endif()
    target_compile_options(rozu PRIVATE /fp:precise /W3 /utf-8)
    target_link_options(rozu PRIVATE /FORCE:MULTIPLE /STACK:16777216)
elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    if(NOT ROZU_GAME_CODE_LIBRARY)
        target_compile_options(rozu_game_code PRIVATE -fno-fast-math -ffp-contract=off -fno-associative-math -w)
        set_source_files_properties("${ROZU_GENERATED_DIR}/register_functions.cpp" PROPERTIES COMPILE_OPTIONS "-O0;-g" SKIP_PRECOMPILE_HEADERS ON)
    endif()
    target_compile_options(rozu PRIVATE -fno-fast-math -ffp-contract=off -fno-associative-math -Wall -Wextra)
endif()

set_target_properties(rozu PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    VS_DEBUGGER_WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)
