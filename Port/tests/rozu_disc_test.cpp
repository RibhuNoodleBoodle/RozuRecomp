#include "rozu/game_disc.h"
#include "rozu/sha256.h"
#include "rozu_layout_generated.h"
#include "runtime/ps2_cd_image.h"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace
{
    int g_failures = 0;

    void check(bool cond, const std::string &msg)
    {
        if (!cond)
        {
            std::cerr << "[FAIL] " << msg << '\n';
            ++g_failures;
        }
        else
        {
            std::cout << "[PASS] " << msg << '\n';
        }
    }

    std::string sha256File(const std::filesystem::path &path)
    {
        std::ifstream in(path, std::ios::binary | std::ios::ate);
        if (!in)
            return {};
        const auto size = static_cast<size_t>(in.tellg());
        in.seekg(0);
        std::vector<uint8_t> data(size);
        if (size > 0 && !in.read(reinterpret_cast<char *>(data.data()), static_cast<std::streamsize>(size)))
            return {};
        return rozu::Sha256::hex(data.data(), data.size());
    }
}

int main(int argc, char *argv[])
{
    namespace fs = std::filesystem;
    fs::path validIso;
    fs::path badIso;
    fs::path cacheDir;

    for (int i = 1; i < argc; ++i)
    {
        const std::string arg = argv[i];
        if (arg == "--iso" && i + 1 < argc)
            validIso = argv[++i];
        else if (arg == "--bad-iso" && i + 1 < argc)
            badIso = argv[++i];
        else if (arg == "--cache-dir" && i + 1 < argc)
            cacheDir = argv[++i];
    }

    const fs::path tempRoot = fs::temp_directory_path() / "rozu_disc_test_tmp";
    std::error_code ec;
    fs::remove_all(tempRoot, ec);
    fs::create_directories(tempRoot, ec);

    if (cacheDir.empty())
        cacheDir = tempRoot / "cache";

    bool createdBadIso = false;
    if (badIso.empty())
    {
        badIso = tempRoot / "fake.iso";
        std::ofstream out(badIso, std::ios::binary | std::ios::trunc);
        std::vector<char> zeros(65536, 0);
        out.write(zeros.data(), static_cast<std::streamsize>(zeros.size()));
        createdBadIso = true;
    }

    const rozu::DiscCheckResult badRes = rozu::verifyDiscAndPrepare(badIso, cacheDir);
    check(!badRes.ok, "verifyDiscAndPrepare rejects invalid/fake ISO");
    check(badRes.error.find(rozu::generated::kSerial) != std::string::npos,
          "rejection message names SLUS-21448: " + badRes.error);

    if (!validIso.empty())
    {
        const rozu::DiscCheckResult okRes = rozu::verifyDiscAndPrepare(validIso, cacheDir);
        check(okRes.ok, "verifyDiscAndPrepare accepts valid SLUS-21448 ISO" +
                             (okRes.ok ? std::string{} : (": " + okRes.error)));
        if (okRes.ok)
        {
            check(fs::exists(okRes.bootElfPath), "cached SLUS_214.48 exists in cacheDir");
            check(sha256File(okRes.bootElfPath) == rozu::generated::kBootElfSha256,
                  "cached SLUS_214.48 SHA-256 matches rozu::generated::kBootElfSha256");

            PS2CdImage::Entry nested{};
            check(PS2CdImage::instance().find("MODULES/PAD2/DS1O_D.IRX", nested) && nested.size == 10469u,
                  "PS2CdImage resolves nested MODULES/PAD2/DS1O_D.IRX");
            PS2CdImage::instance().close();

            const fs::path discovered = rozu::findDiscImage({validIso.parent_path()});
            check(!discovered.empty() && fs::exists(discovered), "findDiscImage locates valid ISO by exact byte size");
        }
    }
    else
    {
        std::cout << "[SKIP] --iso not provided; positive ISO test skipped\n";
    }

    if (createdBadIso)
        fs::remove(badIso, ec);
    fs::remove_all(tempRoot, ec);

    if (g_failures != 0)
    {
        std::cerr << g_failures << " test(s) failed.\n";
        return 1;
    }
    std::cout << "All rozu_disc_test checks passed.\n";
    return 0;
}
