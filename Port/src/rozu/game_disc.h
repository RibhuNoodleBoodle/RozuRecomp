#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace rozu
{
    struct DiscCheckResult
    {
        bool ok = false;
        std::filesystem::path bootElfPath;
        std::string error;
    };

    std::filesystem::path findDiscImage(const std::vector<std::filesystem::path> &searchDirs);
    DiscCheckResult verifyDiscAndPrepare(const std::filesystem::path &isoPath, const std::filesystem::path &cacheDir);
}
