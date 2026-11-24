#include "rozu/hle/cdvd_bridge.h"
#include "rozu/function_hooks.h"
#include "ps2_runtime_macros.h"
#include "runtime/ps2_memory.h"

#include <cstdint>
#include <cstring>

namespace rozu
{
    namespace
    {
        // PS2 EE libcdvd S-command: int sceCdReadDvdDualInfo(int *on_dual, u32 *layer1_start).
        // Without this boundary replacement the guest libcdvd helper loops in sceCd_scmd_prechk
        // trying to bind IOP S-Cmd RPC server 0x80000593. SLUS-21448 is a single-layer DVD-5 image.
        void hleSceCdReadDvdDualInfo(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
        {
            if (!ctx)
            {
                return;
            }
            const uint32_t zero = 0u;
            if (rdram)
            {
                const uint32_t onDualPtr = GPR_U32(ctx, 4);
                const uint32_t layer1Ptr = GPR_U32(ctx, 5);
                if (onDualPtr != 0u)
                {
                    const uint32_t phys = onDualPtr & PS2_RAM_MASK;
                    if (phys <= (PS2_RAM_MASK - 3u))
                    {
                        std::memcpy(rdram + phys, &zero, sizeof(zero));
                    }
                }
                if (layer1Ptr != 0u)
                {
                    const uint32_t phys = layer1Ptr & PS2_RAM_MASK;
                    if (phys <= (PS2_RAM_MASK - 3u))
                    {
                        std::memcpy(rdram + phys, &zero, sizeof(zero));
                    }
                }
            }
            SET_GPR_S32(ctx, 2, 1);
            ctx->pc = GPR_U32(ctx, 31);
        }
    }

    void installCdvdBridge(PS2Runtime &)
    {
        FunctionHooks::instance().replace(0x0024CEA8u,
                                          "sceCdReadDvdDualInfo",
                                          &hleSceCdReadDvdDualInfo,
                                          ReplacementStatus::Hle,
                                          "Single-layer DVD-5 dual-info query without IOP S-Cmd RPC 0x80000593");
    }
}
