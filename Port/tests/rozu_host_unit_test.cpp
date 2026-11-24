#include "rozu/config.h"
#include "rozu/diagnostics.h"
#include "rozu/log.h"
#include "rozu/sha256.h"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

#if defined(__SSE2__) || defined(_M_X64) || defined(_M_IX86)
#include <pmmintrin.h>
#include <xmmintrin.h>
#endif

namespace
{
    int g_failures = 0;

    void check(bool condition, const std::string &message)
    {
        if (!condition)
        {
            std::cerr << "[FAIL] " << message << '\n';
            ++g_failures;
        }
        else
        {
            std::cout << "[PASS] " << message << '\n';
        }
    }

    void unsetEnvVar(const char *name)
    {
#if defined(_WIN32)
        _putenv_s(name, "");
#else
        unsetenv(name);
#endif
    }

    void setEnvVar(const char *name, const char *value)
    {
#if defined(_WIN32)
        _putenv_s(name, value);
#else
        setenv(name, value, 1);
#endif
    }

    void testSha256()
    {
        const std::string abc = rozu::Sha256::hex("abc", 3);
        check(abc == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
              "Sha256::hex(\"abc\") matches NIST vector");

        const std::string empty = rozu::Sha256::hex("", 0);
        check(empty == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
              "Sha256::hex(\"\") matches NIST vector");
    }

    void testConfigLoad()
    {
        namespace fs = std::filesystem;
        const fs::path tempDir = fs::temp_directory_path() / "rozu_host_unit_test_cfg";
        std::error_code ec;
        fs::remove_all(tempDir, ec);
        fs::create_directories(tempDir, ec);
        const fs::path iniPath = tempDir / "rozu.ini";

        unsetEnvVar("ROZU_VIDEO_MODE");
        unsetEnvVar("PS2X_MTVU");
        unsetEnvVar("ROZU_UNIT_TEST_KEY");
        unsetEnvVar("PS2X_UNIT_TEST_KEY");
        unsetEnvVar("SOTC_WIDESCREEN");

        rozu::config::load(iniPath);
        check(fs::exists(iniPath), "config::load creates default rozu.ini when absent");
        const char *videoMode = std::getenv("ROZU_VIDEO_MODE");
        check(videoMode && std::string(videoMode) == "NTSC", "config::load defaults ROZU_VIDEO_MODE=NTSC");
        const char *mtvu = std::getenv("PS2X_MTVU");
        check(mtvu && std::string(mtvu) == "0", "config::load defaults PS2X_MTVU=0");

        {
            std::ofstream custom(iniPath, std::ios::trunc);
            custom << "\xEF\xBB\xBF[Settings]\n"
                   << "ROZU_UNIT_TEST_KEY=\"hello\"\n"
                   << "PS2X_UNIT_TEST_KEY=42\n"
                   << "SOTC_WIDESCREEN=1\n"
                   << "INVALID_PREFIX=99\n";
        }
        setEnvVar("PS2X_UNIT_TEST_KEY", "already_set");
        rozu::config::load(iniPath);

        const char *rozuKey = std::getenv("ROZU_UNIT_TEST_KEY");
        check(rozuKey && std::string(rozuKey) == "hello", "config::load applies ROZU_* keys and strips quotes");
        const char *ps2xKey = std::getenv("PS2X_UNIT_TEST_KEY");
        check(ps2xKey && std::string(ps2xKey) == "already_set", "config::load does not overwrite existing environment variables");
        check(std::getenv("SOTC_WIDESCREEN") == nullptr, "config::load rejects legacy SOTC_* keys");
        check(std::getenv("INVALID_PREFIX") == nullptr, "config::load rejects non-ROZU/PS2X keys");

        unsetEnvVar("ROZU_VIDEO_MODE");
        unsetEnvVar("PS2X_MTVU");
        unsetEnvVar("ROZU_UNIT_TEST_KEY");
        unsetEnvVar("PS2X_UNIT_TEST_KEY");
        fs::remove_all(tempDir, ec);
    }

    void testEeFloatingPointMode()
    {
#if defined(__SSE2__) || defined(_M_X64) || defined(_M_IX86)
        const unsigned int saved = _mm_getcsr();
        _MM_SET_ROUNDING_MODE(_MM_ROUND_NEAREST);
        _MM_SET_FLUSH_ZERO_MODE(_MM_FLUSH_ZERO_OFF);
        _MM_SET_DENORMALS_ZERO_MODE(_MM_DENORMALS_ZERO_OFF);

        rozu::applyEeFloatingPointMode();

        const unsigned int mode = _MM_GET_ROUNDING_MODE();
        const unsigned int ftz = _MM_GET_FLUSH_ZERO_MODE();
        const unsigned int daz = _MM_GET_DENORMALS_ZERO_MODE();
        _mm_setcsr(saved);

        check(mode == _MM_ROUND_TOWARD_ZERO, "applyEeFloatingPointMode sets _MM_ROUND_TOWARD_ZERO");
        check(ftz == _MM_FLUSH_ZERO_ON, "applyEeFloatingPointMode sets _MM_FLUSH_ZERO_ON");
        check(daz == _MM_DENORMALS_ZERO_ON, "applyEeFloatingPointMode sets _MM_DENORMALS_ZERO_ON");
#else
        rozu::applyEeFloatingPointMode();
        check(true, "applyEeFloatingPointMode callable on non-SSE host");
#endif
    }

    void testLogging()
    {
        rozu::log::setTraceMask(static_cast<uint32_t>(rozu::log::Category::Boot));
        check(rozu::log::traceEnabled(rozu::log::Category::Boot), "log traceEnabled matches setTraceMask");
        check(!rozu::log::traceEnabled(rozu::log::Category::Gs), "log traceEnabled returns false for unset category");
        check(rozu::log::name(rozu::log::Category::Loader) == "LOADER", "log::name returns LOADER");
    }
}

int main()
{
    testSha256();
    testConfigLoad();
    testEeFloatingPointMode();
    testLogging();
    if (g_failures != 0)
    {
        std::cerr << g_failures << " test(s) failed.\n";
        return 1;
    }
    std::cout << "All rozu_host_unit_test checks passed.\n";
    return 0;
}
