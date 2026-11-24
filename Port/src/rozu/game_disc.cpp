#include "rozu/game_disc.h"
#include "rozu/log.h"
#include "rozu/sha256.h"
#include "rozu_layout_generated.h"
#include "runtime/ps2_cd_image.h"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace rozu
{
    namespace
    {
        bool hasIsoExtension(const std::filesystem::path &path)
        {
            std::string ext = path.extension().string();
            std::transform(ext.begin(), ext.end(), ext.begin(), [](unsigned char c)
                           { return static_cast<char>(std::tolower(c)); });
            return ext == ".iso";
        }

        bool readDiscFile(const PS2CdImage &cd, const char *discPath, std::vector<uint8_t> &outBytes, std::string &error)
        {
            PS2CdImage::Entry entry{};
            if (!cd.find(discPath, entry) || entry.directory)
            {
                error = std::string("missing disc file: ") + discPath;
                return false;
            }
            outBytes.resize(static_cast<size_t>(entry.size));
            if (!cd.read(static_cast<uint64_t>(entry.lba) * PS2CdImage::kSectorSize, outBytes.data(), outBytes.size()))
            {
                error = std::string("failed to read disc file: ") + discPath;
                return false;
            }
            return true;
        }

        bool verifyEntryHash(const PS2CdImage &cd, const char *discPath, uint64_t expectedSize, const char *expectedSha256,
                             std::vector<uint8_t> &outBytes, std::string &error)
        {
            if (!readDiscFile(cd, discPath, outBytes, error))
            {
                return false;
            }
            if (outBytes.size() != expectedSize)
            {
                std::ostringstream oss;
                oss << "size mismatch for " << discPath << " (" << generated::kSerial << " v" << generated::kVersion
                    << "): expected " << expectedSize << " bytes, got " << outBytes.size();
                error = oss.str();
                return false;
            }
            const std::string actualSha = Sha256::hex(outBytes.data(), outBytes.size());
            if (actualSha != expectedSha256)
            {
                std::ostringstream oss;
                oss << "SHA-256 mismatch for " << discPath << " (" << generated::kSerial << " v" << generated::kVersion
                    << "): expected " << expectedSha256 << ", got " << actualSha;
                error = oss.str();
                return false;
            }
            return true;
        }

        bool fileMatchesSha256(const std::filesystem::path &path, uint64_t expectedSize, const char *expectedSha256)
        {
            std::error_code ec;
            if (!std::filesystem::is_regular_file(path, ec) || ec)
                return false;
            if (std::filesystem::file_size(path, ec) != expectedSize || ec)
                return false;
            std::ifstream in(path, std::ios::binary);
            if (!in)
                return false;
            std::vector<uint8_t> bytes(static_cast<size_t>(expectedSize));
            if (expectedSize > 0 && !in.read(reinterpret_cast<char *>(bytes.data()), static_cast<std::streamsize>(expectedSize)))
                return false;
            return Sha256::hex(bytes.data(), bytes.size()) == expectedSha256;
        }
    }

    std::filesystem::path findDiscImage(const std::vector<std::filesystem::path> &searchDirs)
    {
        std::error_code ec;
        for (const auto &dir : searchDirs)
        {
            if (!std::filesystem::exists(dir, ec) || !std::filesystem::is_directory(dir, ec))
                continue;
            for (const auto &entry : std::filesystem::directory_iterator(dir, ec))
            {
                if (!entry.is_regular_file(ec) || !hasIsoExtension(entry.path()))
                    continue;
                if (entry.file_size(ec) == generated::kDiscSize && !ec)
                    return entry.path();
            }
        }
        return {};
    }

    DiscCheckResult verifyDiscAndPrepare(const std::filesystem::path &isoPath, const std::filesystem::path &cacheDir)
    {
        DiscCheckResult result;
        std::error_code ec;
        if (!std::filesystem::is_regular_file(isoPath, ec) || ec)
        {
            result.error = "disc image not found: " + isoPath.string() + " (expected " + generated::kSerial + " v" + generated::kVersion + ")";
            return result;
        }
        const uint64_t actualSize = std::filesystem::file_size(isoPath, ec);
        if (ec || actualSize != generated::kDiscSize)
        {
            std::ostringstream oss;
            oss << "wrong disc image size for " << generated::kSerial << " v" << generated::kVersion
                << " (expected " << generated::kDiscSize << " bytes, disc SHA-256 " << generated::kDiscSha256
                << "; got " << actualSize << " bytes)";
            result.error = oss.str();
            return result;
        }

        PS2CdImage &cd = PS2CdImage::instance();
        if (!cd.open(isoPath))
        {
            result.error = "invalid ISO9660 image: " + isoPath.string() + " (expected " + generated::kSerial + " v" + generated::kVersion + ")";
            return result;
        }

        std::vector<uint8_t> bytes;
        for (const auto &req : generated::kRequiredFiles)
        {
            if (!verifyEntryHash(cd, req.discPath, req.size, req.sha256, bytes, result.error))
            {
                cd.close();
                return result;
            }
            if (std::string_view(req.discPath) == "SYSTEM.CNF")
            {
                const std::string cnf(reinterpret_cast<const char *>(bytes.data()), bytes.size());
                if (cnf.find(generated::kBootElfDiscPath) == std::string::npos)
                {
                    cd.close();
                    result.error = std::string("SYSTEM.CNF does not reference ") + generated::kBootElfDiscPath;
                    return result;
                }
            }
        }

        if (!verifyEntryHash(cd, generated::kBootElfDiscPath, generated::kBootElfSize, generated::kBootElfSha256, bytes, result.error))
        {
            cd.close();
            return result;
        }

        std::filesystem::create_directories(cacheDir, ec);
        if (ec)
        {
            cd.close();
            result.error = "failed to create cache directory " + cacheDir.string() + ": " + ec.message();
            return result;
        }

        const std::filesystem::path cachedElf = cacheDir / generated::kBootElfDiscPath;
        if (!fileMatchesSha256(cachedElf, generated::kBootElfSize, generated::kBootElfSha256))
        {
            const std::filesystem::path tmpPath = cachedElf.string() + ".tmp";
            {
                std::ofstream out(tmpPath, std::ios::binary | std::ios::trunc);
                if (!out || !out.write(reinterpret_cast<const char *>(bytes.data()), static_cast<std::streamsize>(bytes.size())))
                {
                    cd.close();
                    result.error = "failed to write cached boot ELF: " + cachedElf.string();
                    return result;
                }
            }
            std::filesystem::rename(tmpPath, cachedElf, ec);
            if (ec)
            {
                cd.close();
                result.error = "failed to finalize cached boot ELF: " + ec.message();
                return result;
            }
        }

        if (!fileMatchesSha256(cachedElf, generated::kBootElfSize, generated::kBootElfSha256))
        {
            cd.close();
            result.error = "cached boot ELF verification failed after write: " + cachedElf.string();
            return result;
        }

        ROZU_INFO(Loader, "verified " << generated::kSerial << " v" << generated::kVersion << " (" << (std::size(generated::kRequiredFiles) + 1)
                                      << " files); boot ELF cached at " << cachedElf.string());
        result.ok = true;
        result.bootElfPath = cachedElf;
        return result;
    }
}
