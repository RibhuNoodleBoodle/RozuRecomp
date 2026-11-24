#pragma once

#include <filesystem>

namespace rozu::config
{
    void load(const std::filesystem::path &path);
}
