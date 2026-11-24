#pragma once

#include "ps2_runtime.h"

#include <cstdint>

namespace rozu
{
    void applyEeFloatingPointMode();
    void installEeFloatingPointMode(PS2Runtime &runtime, uint32_t bootEntry);
    void installCallTracesFromEnvironment(PS2Runtime &runtime);
}
