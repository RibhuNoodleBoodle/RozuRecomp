#include "game_overrides.h"
#include "Kernel/Stubs/CD.h"
#include "ps2_runtime.h"
#include "ps2_runtime_calls.h"
#include "ps2_stubs.h"
#include "ps2_syscalls.h"
#include "ps2_log.h"
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <iostream>
#include <mutex>
#include <optional>
#include <vector>

namespace
{
    std::mutex &registryMutex()
    {
        static std::mutex mutex;
        return mutex;
    }

    std::vector<ps2_game_overrides::Descriptor> &descriptorRegistry()
    {
        static std::vector<ps2_game_overrides::Descriptor> registry;
        return registry;
    }

    bool equalsIgnoreCaseAscii(std::string_view lhs, std::string_view rhs)
    {
        if (lhs.size() != rhs.size())
        {
            return false;
        }

        for (size_t i = 0; i < lhs.size(); ++i)
        {
            const auto l = static_cast<unsigned char>(lhs[i]);
            const auto r = static_cast<unsigned char>(rhs[i]);
            if (std::tolower(l) != std::tolower(r))
            {
                return false;
            }
        }

        return true;
    }

    std::string basenameFromPath(const std::string &path)
    {
        std::error_code ec;
        const std::filesystem::path fsPath(path);
        const std::filesystem::path leaf = fsPath.filename();
        if (leaf.empty())
        {
            return path;
        }
        return leaf.string();
    }

    std::optional<PS2Runtime::RecompiledFunction> resolveHandlerByName(std::string_view handlerName)
    {
        const std::string_view resolvedSyscall = ps2_runtime_calls::resolveSyscallName(handlerName);
        if (!resolvedSyscall.empty())
        {
#define PS2_RESOLVE_SYSCALL(name)                   \
    if (resolvedSyscall == std::string_view{#name}) \
    {                                               \
        return &ps2_syscalls::name;                 \
    }
            PS2_SYSCALL_LIST(PS2_RESOLVE_SYSCALL)
#undef PS2_RESOLVE_SYSCALL
        }

        const std::string_view resolvedStub = ps2_runtime_calls::resolveStubName(handlerName);
        if (!resolvedStub.empty())
        {
#define PS2_RESOLVE_STUB(name)                   \
    if (resolvedStub == std::string_view{#name}) \
    {                                            \
        return &ps2_stubs::name;                 \
    }
            PS2_STUB_LIST(PS2_RESOLVE_STUB)
#undef PS2_RESOLVE_STUB
        }

        return std::nullopt;
    }
}
namespace ps2_game_overrides
{
    AutoRegister::AutoRegister(const Descriptor &descriptor)
    {
        registerDescriptor(descriptor);
    }

    void registerDescriptor(const Descriptor &descriptor)
    {
        if (!descriptor.apply)
        {
            std::cerr << "[game_overrides] ignoring descriptor with null apply callback." << std::endl;
            return;
        }

        std::lock_guard<std::mutex> lock(registryMutex());
        descriptorRegistry().push_back(descriptor);
    }

    bool bindAddressHandler(PS2Runtime &runtime, uint32_t address, std::string_view handlerName)
    {
        const auto resolved = resolveHandlerByName(handlerName);
        if (!resolved.has_value())
        {
            std::cerr << "[game_overrides] unresolved handler '" << handlerName
                      << "' for address 0x" << std::hex << address << std::dec << std::endl;
            return false;
        }

        return runtime.replaceFunction(address, resolved.value());
    }

    void applyMatching(PS2Runtime &runtime,
                       const std::string &elfPath,
                       uint32_t entry,
                       uint32_t fileCrc32,
                       bool fileCrcValid)
    {

        std::vector<Descriptor> descriptors;
        {
            std::lock_guard<std::mutex> lock(registryMutex());
            descriptors = descriptorRegistry();
        }

        if (descriptors.empty())
        {
            return;
        }

        const std::string elfName = basenameFromPath(elfPath);
        size_t appliedCount = 0;
        for (const Descriptor &descriptor : descriptors)
        {
            if (!descriptor.apply)
            {
                continue;
            }

            if (descriptor.elfName && descriptor.elfName[0] != '\0')
            {
                if (!equalsIgnoreCaseAscii(descriptor.elfName, elfName))
                {
                    continue;
                }
            }

            if (descriptor.entry != 0u && descriptor.entry != entry)
            {
                continue;
            }

            if (descriptor.crc32 != 0u)
            {
                if (!fileCrcValid || fileCrc32 != descriptor.crc32)
                {
                    continue;
                }
            }

            const char *name = (descriptor.name && descriptor.name[0] != '\0')
                                   ? descriptor.name
                                   : "unnamed";
            RUNTIME_LOG("[game_overrides] applying '" << name << "'");
            descriptor.apply(runtime);
            ++appliedCount;
        }

        if (appliedCount > 0)
        {
            RUNTIME_LOG("[game_overrides] applied " << appliedCount << " matching override(s).");
        }
    }
}

namespace
{
    template <void (*StubFn)(uint8_t *, R5900Context *, PS2Runtime *)>
    void guestStubThunk(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        ctx->pc = getRegU32(ctx, 31);
        StubFn(rdram, ctx, runtime);
    }

    void applyRuleOfRoseOverride(PS2Runtime &runtime)
    {
        // Always stop cleanly on missing targets so function-map gaps never silently skip or mis-dispatch.
        runtime.setMissingFunctionPolicy(PS2Runtime::MissingFunctionPolicy::Stop);

        // Ensure raw LBN reads (e.g. LBN 0x10 PVD / PACK headers) resolve against Rule of Rose (USA).iso when present.
        PS2Runtime::IoPaths ioPaths = PS2Runtime::getIoPaths();
        if (ioPaths.cdImage.empty())
        {
            std::error_code ec;
            const std::filesystem::path candidates[] = {
                ioPaths.elfDirectory / "Rule of Rose (USA).iso",
                ioPaths.elfDirectory.parent_path() / "Rule of Rose (USA).iso",
                ioPaths.elfDirectory.parent_path().parent_path() / "Rule of Rose (USA).iso",
                std::filesystem::current_path(ec) / "Rule of Rose (USA).iso",
            };
            for (const auto &candidate : candidates)
            {
                if (!candidate.empty() && std::filesystem::is_regular_file(candidate, ec))
                {
                    ioPaths.cdImage = candidate;
                    PS2Runtime::setIoPaths(ioPaths);
                    RUNTIME_LOG("[game_overrides:rozu] Configured cdImage=" << candidate.string());
                    break;
                }
            }
        }

        // SLUS-21448 libcdvd entry points missed by ps2xRecomp stub matching / CSV classification.
        runtime.replaceFunction(0x0024B948u, &guestStubThunk<ps2_stubs::sceCdPOffCallback>);
        runtime.replaceFunction(0x0024BA98u, &guestStubThunk<ps2_stubs::sceCdLayerSearchFile>);
        runtime.replaceFunction(0x0024BD98u, &guestStubThunk<ps2_stubs::sceCdSearchFile>);
        runtime.replaceFunction(0x0024C5A8u, &guestStubThunk<ps2_stubs::sceCdDiskReady>);
        runtime.replaceFunction(0x0024CBC0u, &guestStubThunk<ps2_stubs::sceCdGetDiskType>);
        runtime.replaceFunction(0x0024CDD0u, &guestStubThunk<ps2_stubs::sceCdSetTimeout>);
        runtime.replaceFunction(0x0024CEA8u, &guestStubThunk<ps2_stubs::sceCdReadDvdDualInfo>);

        RUNTIME_LOG("[game_overrides:rozu] Configured Rule of Rose (SLUS_214.48, crc32=0x8cf7b024) with MissingFunctionPolicy::Stop + libcdvd HLE bindings");
    }
}

PS2_REGISTER_GAME_OVERRIDE("Rule of Rose (NTSC-U)", "SLUS_214.48", 0x00100008u, 0x8cf7b024u, applyRuleOfRoseOverride)
