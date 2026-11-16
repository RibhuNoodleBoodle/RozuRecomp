#include "MiniTest.h"
#include "ps2x/iop/ps2_path.h"
#include "emulator/core/iop_memory.h"
#include "emulator/core/iop_spu2.h"
#include "../../ps2xIOP/tests/iop_compat_test_support.h"

#include <cmath>
#include <cstring>
#include <vector>

void register_ps2_iop_tests()
{
    MiniTest::Case("PS2IopSubsystem", [](TestCase &tc)
    {
        tc.Run("PS2 path parsing is shared and normalizes ISO/module names", [](TestCase &t)
        {
            const ps2x::iop::ParsedPs2Path cd = ps2x::iop::parsePs2Path("CDROM0:\\MODULES\\LIBSD.IRX;1");
            t.Equals(cd.device, ps2x::iop::Ps2PathDevice::Cdrom,
                     "device names should be case-insensitive");
            t.Equals(cd.path, std::string("MODULES/LIBSD.IRX"),
                     "separators and ISO version suffixes should normalize once");
            t.Equals(ps2x::iop::ps2PathLeafKey(cd), std::string("libsd"),
                     "module lookup should use a normalized IRX leaf key");

            const ps2x::iop::ParsedPs2Path rom = ps2x::iop::parsePs2Path("rom0:ROMVER");
            t.Equals(rom.device, ps2x::iop::Ps2PathDevice::Rom0,
                     "ROM0 should remain a distinct virtual device");
            t.IsFalse(static_cast<bool>(ps2x::iop::parsePs2Path("unknown0:file.irx")),
                      "unsupported devices must not fall through to cdrom0");
        });

        tc.Run("HLE services activate only after a recognized module load", [](TestCase &t)
        {
            iop_test::Host host;
            ps2x::iop::IopSubsystem subsystem(host);
            t.IsFalse(subsystem.canBindRpc(0x80000701u),
                      "LIBSD RPC must not exist before LIBSD is loaded");

            const ps2x::iop::ModuleLoadResult unknown = subsystem.loadModule("rom0:NOT_A_REAL_MODULE");
            t.IsTrue(unknown.handled, "the module manager should return a real load result");
            t.IsTrue(unknown.moduleId < 0, "unknown ROM modules must fail instead of receiving fake IDs");

            const ps2x::iop::ModuleLoadResult loaded = subsystem.loadModule("rom0:LIBSD");
            t.IsTrue(loaded.moduleId > 0, "a registered no-BIOS HLE module should load");
            t.IsTrue(subsystem.canBindRpc(0x80000701u),
                     "loading LIBSD should activate its HLE RPC endpoint");

            ps2x::iop::RpcRequest request{};
            request.sid = 0x80000701u;
            request.function = 3u;
            t.IsTrue(subsystem.handleRpc(request).handled,
                     "the activated LIBSD service should handle its RPC");
            t.Equals(host.audioCalls, 1u, "the RPC should reach the HLE audio contract");

            int32_t stopResult = -1;
            t.IsTrue(subsystem.stopModule(loaded.moduleId, &stopResult),
                     "an HLE module should have a real stoppable lifecycle");
            t.Equals(stopResult, 0, "stopping an HLE module should report success");
            t.IsFalse(subsystem.canBindRpc(0x80000701u),
                      "stopping LIBSD should deactivate its RPC endpoint");
        });

        tc.Run("unknown SID remains unhandled without a loaded IRX", [](TestCase &t)
        {
            iop_test::Host host;
            ps2x::iop::IopSubsystem subsystem(host);

            ps2x::iop::RpcRequest request{};
            request.sid = 0xDEADC0DEu;
            request.function = 0x99u;
            const ps2x::iop::RpcResult result = subsystem.handleRpc(request);
            t.IsFalse(result.handled, "an unknown SID should not be claimed by the IOP subsystem");
            t.Equals(result.resultAddress, 0u, "an unknown SID should not return a guest result address");
            t.IsFalse(result.signalNowaitCompletion, "an unknown SID should not signal nowait completion");
            t.Equals(result.callbackPolicy, ps2x::iop::CallbackPolicy::RuntimeDefault,
                     "an unknown SID should preserve runtime callback handling");

        });

        tc.Run("IOPCONF.CNF module sequence resolves mixed-case IRX paths and activates RPC", [](TestCase &t)
        {
            const ps2x::iop::ParsedPs2Path pad = ps2x::iop::parsePs2Path("cdrom0:\\modules\\pad2\\ds1o_d.irx;1");
            t.Equals(pad.device, ps2x::iop::Ps2PathDevice::Cdrom, "mixed-case nested IRX path should parse as Cdrom");
            t.Equals(pad.path, std::string("modules/pad2/ds1o_d.irx"), "nested path should normalize separators and ;1");
            t.Equals(ps2x::iop::ps2PathLeafKey(pad), std::string("ds1o_d"), "leaf key should strip dir and .irx extension");

            iop_test::Host host;
            ps2x::iop::IopSubsystem subsystem(host);

            const char *const hleSequence[] = {
                "cdrom0:\\modules\\sio2man.irx;1",
                "cdrom0:\\modules\\sio2d.irx;1",
                "cdrom0:\\modules\\dbcman.irx;1",
                "cdrom0:\\modules\\mcman.irx;1",
                "cdrom0:\\modules\\mcserv.irx;1",
                "cdrom0:\\modules\\libsd.irx;1",
            };
            for (const char *path : hleSequence)
            {
                const ps2x::iop::ModuleLoadResult res = subsystem.loadModule(path);
                t.IsTrue(res.moduleId > 0, std::string("expected positive module ID for ") + path);
            }

            t.IsTrue(subsystem.canBindRpc(0x80000400u), "mcserv RPC should bind after IOPCONF sequence");
            t.IsTrue(subsystem.canBindRpc(0x80000701u), "libsd RPC should bind after IOPCONF sequence");
        });

        tc.Run("IopSpu2 synthesizes Core 0 AutoDMA and PS-ADPCM voice PCM via submitAudioPcm", [](TestCase &t)
        {
            class PcmCaptureHost final : public ps2x::iop::IopHost
            {
            public:
                bool readGuest(uint32_t, void *, size_t) const override { return false; }
                bool writeGuest(uint32_t, const void *, size_t) override { return false; }
                bool zeroGuest(uint32_t, size_t) override { return false; }
                bool normalizeGuestAddress(uint32_t, uint32_t &) const override { return false; }
                uint32_t allocateIopHandle(ps2x::iop::IopHandleKind) override { return 1u; }
                uint32_t allocateGuest(uint32_t, uint32_t) override { return 0u; }
                void freeGuest(uint32_t) override {}
                void audioCommand(uint32_t, uint32_t, ps2x::iop::GuestBuffer, ps2x::iop::GuestBuffer) override {}
                void submitAudioPcm(const int16_t *samples, size_t frameCount, uint32_t sampleRate) override
                {
                    if (!samples || frameCount == 0u)
                        return;
                    lastRate = sampleRate;
                    pcm.insert(pcm.end(), samples, samples + frameCount * 2u);
                }
                std::string hostPath(ps2x::iop::HostPathKind) const override { return {}; }
                std::string translateGuestPath(std::string_view p) const override { return std::string(p); }
                uint64_t openHostFile(std::string_view) override { return 0u; }
                bool hostFileSize(uint64_t, uint64_t &) const override { return false; }
                bool readHostFile(uint64_t, uint64_t, void *, size_t, size_t &) override { return false; }
                void closeHostFile(uint64_t) override {}
                int32_t memoryCard(const ps2x::iop::MemoryCardRequest &) override { return 0; }
                bool hasGuestFunction(uint32_t) const override { return false; }
                bool invokeGuestFunction(uint64_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t *) override { return false; }
                void log(ps2x::iop::LogLevel, std::string_view) override {}

                uint32_t lastRate = 0u;
                std::vector<int16_t> pcm;
            };

            PcmCaptureHost host;
            ps2x::iop::detail::IopMemory mem;
            ps2x::iop::detail::IopSpu2 spu2;
            mem.setSpu2(&spu2);

            // 1) Core 0 AutoDMA (512B Left + 512B Right planar stereo chunk)
            std::vector<uint8_t> autoDmaBlock(1024u, 0u);
            for (size_t i = 0; i < 256u; ++i)
            {
                const int16_t l = static_cast<int16_t>(std::lround(12000.0 * std::sin(static_cast<double>(i) * 0.15)));
                const int16_t r = static_cast<int16_t>(-l);
                std::memcpy(autoDmaBlock.data() + i * 2u, &l, sizeof(l));
                std::memcpy(autoDmaBlock.data() + 512u + i * 2u, &r, sizeof(r));
            }
            t.IsTrue(mem.writeRam(0x00010000u, autoDmaBlock.data(), autoDmaBlock.size()),
                     "should stage AutoDMA chunk in IOP RAM");
            mem.write16(0x1F9001B0u, 0x0001u); // ADMAS Core 0
            mem.write32(0x1F8010C0u, 0x00010000u); // Core 0 DMA MADR
            mem.write32(0x1F8010C4u, 0x00010100u); // 1 block * 256 words = 1024 bytes
            mem.write32(0x1F8010C8u, 0x01000201u); // Start DMA RAM -> SPU2 Core 0
            const auto dma0 = mem.takeDmaStart();
            t.IsTrue(dma0.has_value(), "Core 0 SPU2 DMA start should be queued");
            spu2.handleDmaTransfer(dma0->core, dma0->madr, dma0->byteCount, dma0->chcr, mem);
            spu2.stepCycles(256u * ps2x::iop::detail::IopSpu2::CyclesPerSample, host);
            spu2.flushPendingAudio(host);

            t.Equals(host.lastRate, 48000u, "IopSpu2 should emit 48 kHz PCM");
            t.Equals(host.pcm.size(), static_cast<size_t>(256u * 2u), "AutoDMA should output 256 stereo frames");
            int32_t peakAuto = 0;
            for (int16_t s : host.pcm)
                peakAuto = std::max(peakAuto, std::abs(static_cast<int32_t>(s)));
            t.IsTrue(peakAuto > 5000, "AutoDMA PCM should contain non-zero synthesized samples");

            // 2) Core 0 Voice 0 PS-ADPCM SoundRAM DMA + KeyOn
            host.pcm.clear();
            spu2.reset();
            std::array<uint8_t, 16> adpcmBlock{};
            adpcmBlock[0] = 0x02u; // shift=2, filter=0
            adpcmBlock[1] = 0x01u; // flags=end (single block)
            for (size_t i = 2; i < 16; ++i)
                adpcmBlock[i] = 0x55u;
            t.IsTrue(mem.writeRam(0x00020000u, adpcmBlock.data(), adpcmBlock.size()),
                     "should stage ADPCM block in IOP RAM");
            mem.write16(0x1F9001B0u, 0x0000u); // Normal SoundRAM DMA
            mem.write16(0x1F9001A8u, 0x0000u); // TSAH
            mem.write16(0x1F9001AAu, 0x0800u); // TSAL (byte addr 0x1000)
            mem.write32(0x1F8010C0u, 0x00020000u);
            mem.write32(0x1F8010C4u, 0x00010004u); // 1 block * 4 words = 16 bytes
            mem.write32(0x1F8010C8u, 0x01000201u);
            const auto dma1 = mem.takeDmaStart();
            t.IsTrue(dma1.has_value(), "SoundRAM DMA start should be queued");
            spu2.handleDmaTransfer(dma1->core, dma1->madr, dma1->byteCount, dma1->chcr, mem);

            mem.write16(0x1F900000u, 0x3FFFu); // Voice 0 VOLL
            mem.write16(0x1F900002u, 0x3FFFu); // Voice 0 VOLR
            mem.write16(0x1F900004u, 0x1000u); // Voice 0 PITCH (48 kHz)
            mem.write16(0x1F9001C0u, 0x0000u); // Voice 0 SSA_H
            mem.write16(0x1F9001C2u, 0x0800u); // Voice 0 SSA_L
            mem.write16(0x1F9001A0u, 0x0001u); // Voice 0 KeyOn

            spu2.stepCycles(32u * ps2x::iop::detail::IopSpu2::CyclesPerSample, host);
            spu2.flushPendingAudio(host);

            int32_t peakAdpcm = 0;
            for (int16_t s : host.pcm)
                peakAdpcm = std::max(peakAdpcm, std::abs(static_cast<int32_t>(s)));
            t.IsTrue(peakAdpcm > 100, "ADPCM Voice KeyOn should synthesize non-zero PCM output");
            t.IsTrue((mem.read16(0x1F900340u) & 0x0001u) != 0u, "Voice 0 ENDX bit should latch after end block");
        });

    });
}
