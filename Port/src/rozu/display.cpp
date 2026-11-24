#include "rozu/display.h"
#include "rozu/log.h"
#include "raylib.h"

#include <charconv>
#include <cstdlib>
#include <string>
#include <string_view>

namespace rozu
{
    void configureHostDisplay()
    {
        const char *setting = std::getenv("ROZU_VSYNC");
        const bool vsync = !setting || std::string_view(setting) != "0";
        int limit = 60;
        if (const char *limitSetting = std::getenv("ROZU_FPS_LIMIT"); limitSetting && *limitSetting)
        {
            const std::string_view value(limitSetting);
            const auto [end, error] = std::from_chars(value.data(), value.data() + value.size(), limit);
            if (error != std::errc{} || end != value.data() + value.size() || limit < 0)
            {
                ROZU_ERROR(Boot, "invalid ROZU_FPS_LIMIT='" << value << "'; using 60");
                limit = 60;
            }
        }
        if (vsync)
            SetWindowState(FLAG_VSYNC_HINT);
        SetTargetFPS(limit);
        if (vsync)
            ROZU_INFO(Boot, "host display: monitor VSync" << (limit > 0 ? ", " + std::to_string(limit) + " FPS limit" : std::string{}));
        else
            ROZU_INFO(Boot, "host display: VSync off, " << (limit > 0 ? std::to_string(limit) + " FPS limit" : std::string("uncapped")));
    }
}
