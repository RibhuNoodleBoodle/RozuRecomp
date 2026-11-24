#pragma once

#include <cstdint>
#include <sstream>
#include <string>
#include <string_view>

namespace rozu::log
{
    enum class Category : uint32_t
    {
        Boot = 1u << 0,
        Loader = 1u << 1,
        File = 1u << 2,
        Ee = 1u << 3,
        Iop = 1u << 4,
        Gs = 1u << 5,
        Vu = 1u << 6,
        Spu2 = 1u << 7,
        Input = 1u << 8,
        Game = 1u << 9,
        Hook = 1u << 10,
    };

    enum class Level
    {
        Error,
        Warn,
        Info,
        Trace,
    };

    void configureFromEnvironment();
    void setTraceMask(uint32_t mask);
    bool traceEnabled(Category category);
    void write(Category category, Level level, std::string_view message);
    std::string_view name(Category category);
}

#define ROZU_LOG(cat, lvl, expr)                                                   \
    do                                                                             \
    {                                                                              \
        if ((lvl) != ::rozu::log::Level::Trace || ::rozu::log::traceEnabled(cat)) \
        {                                                                          \
            std::ostringstream rozuLogStream_;                                     \
            rozuLogStream_ << expr;                                                \
            ::rozu::log::write((cat), (lvl), rozuLogStream_.str());                \
        }                                                                          \
    } while (0)

#define ROZU_INFO(cat, expr) ROZU_LOG(::rozu::log::Category::cat, ::rozu::log::Level::Info, expr)
#define ROZU_WARN(cat, expr) ROZU_LOG(::rozu::log::Category::cat, ::rozu::log::Level::Warn, expr)
#define ROZU_ERROR(cat, expr) ROZU_LOG(::rozu::log::Category::cat, ::rozu::log::Level::Error, expr)
#define ROZU_TRACE(cat, expr) ROZU_LOG(::rozu::log::Category::cat, ::rozu::log::Level::Trace, expr)
