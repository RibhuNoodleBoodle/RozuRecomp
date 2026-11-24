#include "rozu/hle/tty_bridge.h"
#include "rozu/function_hooks.h"
#include "rozu/log.h"
#include "ps2_runtime_macros.h"
#include "runtime/ps2_memory.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdint>
#include <mutex>
#include <string>

namespace rozu
{
    namespace
    {
        std::mutex g_ttyMutex;
        std::array<std::string, 3> g_lineBuffers;

        void emitGuestText(uint32_t fd, const uint8_t *rdram, uint32_t bufAddr, uint32_t len)
        {
            if (!rdram || bufAddr == 0 || len == 0 || len > 65536u)
            {
                return;
            }
            const uint32_t slot = (fd == 2u) ? 2u : 1u;
            std::lock_guard<std::mutex> lock(g_ttyMutex);
            std::string &pending = g_lineBuffers[slot];
            for (uint32_t i = 0; i < len; ++i)
            {
                const uint8_t ch = rdram[(bufAddr + i) & PS2_RAM_MASK];
                if (ch == '\0')
                {
                    break;
                }
                if (ch == '\n')
                {
                    if (!pending.empty())
                    {
                        ROZU_INFO(Game, pending);
                        pending.clear();
                    }
                }
                else if (ch == '\r')
                {
                    continue;
                }
                else if (ch == '\t' || (ch >= 0x20 && ch < 0x7F))
                {
                    pending.push_back(static_cast<char>(ch));
                }
                if (pending.size() >= 1024u)
                {
                    ROZU_INFO(Game, pending);
                    pending.clear();
                }
            }
        }

        void logWriteCall(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
        {
            if (!ctx || !rdram)
            {
                return;
            }
            const uint32_t fd = GPR_U32(ctx, 4);
            if (fd != 1u && fd != 2u)
            {
                return;
            }
            const uint32_t buf = GPR_U32(ctx, 5);
            const uint32_t len = GPR_U32(ctx, 6);
            emitGuestText(fd, rdram, buf, len);
        }

        void logTtyWriteCall(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
        {
            if (!ctx || !rdram)
            {
                return;
            }
            const uint32_t buf = GPR_U32(ctx, 5);
            const uint32_t len = GPR_U32(ctx, 6);
            emitGuestText(1u, rdram, buf, len);
        }

        void logPrintfCall(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
        {
            if (!ctx || !rdram)
            {
                return;
            }
            const uint32_t fmtAddr = GPR_U32(ctx, 4);
            if (fmtAddr == 0)
            {
                return;
            }
            std::string fmt;
            fmt.reserve(128);
            for (uint32_t i = 0; i < 512u; ++i)
            {
                const uint8_t ch = rdram[(fmtAddr + i) & PS2_RAM_MASK];
                if (ch == '\0')
                {
                    break;
                }
                if (ch == '\n' || ch == '\r')
                {
                    fmt.push_back(' ');
                }
                else if (ch >= 0x20 && ch < 0x7F)
                {
                    fmt.push_back(static_cast<char>(ch));
                }
            }
            if (!fmt.empty())
            {
                ROZU_INFO(Game, "scePrintf fmt=\"" << fmt << "\"");
            }
        }
    }

    void installTtyBridge(PS2Runtime &runtime)
    {
        (void)runtime;
        auto &hooks = FunctionHooks::instance();
        hooks.observeEntry(0x0025DEA8u, "tty_write", logWriteCall);
        hooks.observeEntry(0x00263068u, "tty_sceWrite", logWriteCall);
        hooks.observeEntry(0x0025EB80u, "tty_sceTtyWrite", logTtyWriteCall);
        hooks.observeEntry(0x00260110u, "tty_scePrintf", logPrintfCall);
    }
}
