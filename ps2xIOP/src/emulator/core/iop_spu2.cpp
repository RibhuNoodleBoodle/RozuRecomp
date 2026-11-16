#include "emulator/core/iop_spu2.h"

#include "emulator/core/iop_memory.h"
#include "ps2x/iop/iop_host.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>

namespace ps2x::iop::detail
{
    namespace
    {
        constexpr uint32_t kCoreStride = 0x400u;
        constexpr uint32_t kGlobalRegStart = 0x760u;
        constexpr uint32_t kSoundRamHalfMask = (IopSpu2::SoundRamSize / 2u) - 1u;
        constexpr size_t kMaxAutoDmaBufferedFrames = 48000u;
        constexpr size_t kAutoDmaBlockBytes = 1024u;
        constexpr size_t kAutoDmaChannelBytes = 512u;

        // PS-ADPCM filter coefficients in Q6 fixed-point (matching Sony SPU / ps2_audio_vag).
        constexpr std::array<int32_t, 5> kAdpcmPosCoeff = {0, 60, 115, 98, 122};
        constexpr std::array<int32_t, 5> kAdpcmNegCoeff = {0, 0, -52, -55, -60};

        inline int16_t readLe16(const uint8_t *ptr) noexcept
        {
            uint16_t raw = 0;
            std::memcpy(&raw, ptr, sizeof(raw));
            return static_cast<int16_t>(raw);
        }

        inline float volumeRegToFloat(uint16_t reg) noexcept
        {
            if ((reg & 0x8000u) != 0u)
            {
                // Sweep/envelope mode: start near unity so sweeps remain audible.
                return 0.75f;
            }
            const int32_t magnitude = static_cast<int32_t>(reg & 0x3FFFu);
            const float sign = (reg & 0x4000u) != 0u ? -1.0f : 1.0f;
            return sign * (static_cast<float>(magnitude) / 16384.0f);
        }
    }

    IopSpu2::IopSpu2()
        : m_soundRam(SoundRamSize, 0u)
    {
        m_outputBuffer.reserve(OutputBatchFrames * 2u);
        reset();
    }

    void IopSpu2::reset()
    {
        std::fill(m_soundRam.begin(), m_soundRam.end(), uint8_t{0});
        m_regs.fill(0u);
        for (auto &core : m_cores)
        {
            core = CoreState{};
        }
        m_regs[0x760u / 2u] = 0x3FFFu;
        m_regs[0x762u / 2u] = 0x3FFFu;
        m_regs[0x788u / 2u] = 0x3FFFu;
        m_regs[0x78Au / 2u] = 0x3FFFu;
        m_cycleAccumulator = 0;
        m_outputBuffer.clear();
    }

    uint16_t IopSpu2::read16(uint32_t physAddress) const
    {
        if (physAddress < BaseAddress || physAddress >= BaseAddress + RegisterSpan)
            return 0u;
        const uint32_t offset = (physAddress - BaseAddress) & ~1u;
        if (offset >= kGlobalRegStart)
            return readGlobalReg16(offset);
        const uint32_t core = offset / kCoreStride;
        const uint32_t regOffset = offset % kCoreStride;
        return readCoreReg16(core, regOffset);
    }

    void IopSpu2::write16(uint32_t physAddress, uint16_t value)
    {
        if (physAddress < BaseAddress || physAddress >= BaseAddress + RegisterSpan)
            return;
        const uint32_t offset = (physAddress - BaseAddress) & ~1u;
        m_regs[offset / 2u] = value;
        if (offset >= kGlobalRegStart)
        {
            writeGlobalReg16(offset, value);
            return;
        }
        const uint32_t core = offset / kCoreStride;
        const uint32_t regOffset = offset % kCoreStride;
        writeCoreReg16(core, regOffset, value);
    }

    uint16_t IopSpu2::readCoreReg16(uint32_t core, uint32_t regOffset) const
    {
        if (core >= CoreCount)
            return 0u;
        const CoreState &state = m_cores[core];
        if (regOffset < 0x180u)
        {
            const uint32_t voiceIdx = regOffset / 0x10u;
            const uint32_t field = regOffset % 0x10u;
            const Voice &voice = state.voices[voiceIdx];
            switch (field)
            {
            case 0x0u:
                return voice.voll;
            case 0x2u:
                return voice.volr;
            case 0x4u:
                return voice.pitch;
            case 0x6u:
                return voice.adsr1;
            case 0x8u:
                return voice.adsr2;
            case 0xAu:
                return voice.envx;
            case 0xCu:
                return voice.volxl;
            case 0xEu:
                return voice.volxr;
            default:
                return 0u;
            }
        }
        if (regOffset >= 0x1C0u && regOffset < 0x2E0u)
        {
            const uint32_t voiceIdx = (regOffset - 0x1C0u) / 0x0Cu;
            const uint32_t field = (regOffset - 0x1C0u) % 0x0Cu;
            const Voice &voice = state.voices[voiceIdx];
            switch (field)
            {
            case 0x0u:
                return static_cast<uint16_t>((voice.ssaHalfAddr >> 16u) & 0x1Fu);
            case 0x2u:
                return static_cast<uint16_t>(voice.ssaHalfAddr & 0xFFFFu);
            case 0x4u:
                return static_cast<uint16_t>((voice.lsaxHalfAddr >> 16u) & 0x1Fu);
            case 0x6u:
                return static_cast<uint16_t>(voice.lsaxHalfAddr & 0xFFFFu);
            case 0x8u:
                return static_cast<uint16_t>((voice.currentHalfAddr >> 16u) & 0x1Fu);
            case 0xAu:
                return static_cast<uint16_t>(voice.currentHalfAddr & 0xFFFFu);
            default:
                return 0u;
            }
        }

        switch (regOffset)
        {
        case 0x198u:
            return state.mmix;
        case 0x19Au:
            return state.coreAttr;
        case 0x1A0u:
            return static_cast<uint16_t>(state.kon & 0xFFFFu);
        case 0x1A2u:
            return static_cast<uint16_t>((state.kon >> 16u) & 0xFFu);
        case 0x1A4u:
            return static_cast<uint16_t>(state.koff & 0xFFFFu);
        case 0x1A6u:
            return static_cast<uint16_t>((state.koff >> 16u) & 0xFFu);
        case 0x1A8u:
            return static_cast<uint16_t>((state.transferHalfAddr >> 16u) & 0x1Fu);
        case 0x1AAu:
            return static_cast<uint16_t>(state.transferHalfAddr & 0xFFFFu);
        case 0x1B0u:
            return state.admas;
        case 0x340u:
            return static_cast<uint16_t>(state.endx & 0xFFFFu);
        case 0x342u:
            return static_cast<uint16_t>((state.endx >> 16u) & 0xFFu);
        case 0x344u:
            return state.statx;
        default:
            return m_regs[(core * kCoreStride + regOffset) / 2u];
        }
    }

    void IopSpu2::writeCoreReg16(uint32_t core, uint32_t regOffset, uint16_t value)
    {
        if (core >= CoreCount)
            return;
        CoreState &state = m_cores[core];
        if (regOffset < 0x180u)
        {
            const uint32_t voiceIdx = regOffset / 0x10u;
            const uint32_t field = regOffset % 0x10u;
            Voice &voice = state.voices[voiceIdx];
            switch (field)
            {
            case 0x0u:
                voice.voll = value;
                voice.volxl = value;
                break;
            case 0x2u:
                voice.volr = value;
                voice.volxr = value;
                break;
            case 0x4u:
                voice.pitch = value;
                break;
            case 0x6u:
                voice.adsr1 = value;
                break;
            case 0x8u:
                voice.adsr2 = value;
                break;
            default:
                break;
            }
            return;
        }
        if (regOffset >= 0x1C0u && regOffset < 0x2E0u)
        {
            const uint32_t voiceIdx = (regOffset - 0x1C0u) / 0x0Cu;
            const uint32_t field = (regOffset - 0x1C0u) % 0x0Cu;
            Voice &voice = state.voices[voiceIdx];
            switch (field)
            {
            case 0x0u:
                voice.ssaHalfAddr = (voice.ssaHalfAddr & 0x0000FFFFu) | ((static_cast<uint32_t>(value) & 0x1Fu) << 16u);
                break;
            case 0x2u:
                voice.ssaHalfAddr = (voice.ssaHalfAddr & 0xFFFF0000u) | value;
                break;
            case 0x4u:
                voice.lsaxHalfAddr = (voice.lsaxHalfAddr & 0x0000FFFFu) | ((static_cast<uint32_t>(value) & 0x1Fu) << 16u);
                break;
            case 0x6u:
                voice.lsaxHalfAddr = (voice.lsaxHalfAddr & 0xFFFF0000u) | value;
                break;
            default:
                break;
            }
            return;
        }

        switch (regOffset)
        {
        case 0x198u:
            state.mmix = value;
            break;
        case 0x19Au:
            state.coreAttr = value;
            break;
        case 0x1A0u:
            state.kon = (state.kon & 0xFFFF0000u) | value;
            keyOnVoices(core, value);
            break;
        case 0x1A2u:
            state.kon = (state.kon & 0x0000FFFFu) | ((static_cast<uint32_t>(value) & 0xFFu) << 16u);
            keyOnVoices(core, (static_cast<uint32_t>(value) & 0xFFu) << 16u);
            break;
        case 0x1A4u:
            state.koff = (state.koff & 0xFFFF0000u) | value;
            keyOffVoices(core, value);
            break;
        case 0x1A6u:
            state.koff = (state.koff & 0x0000FFFFu) | ((static_cast<uint32_t>(value) & 0xFFu) << 16u);
            keyOffVoices(core, (static_cast<uint32_t>(value) & 0xFFu) << 16u);
            break;
        case 0x1A8u:
            state.transferHalfAddr =
                ((state.transferHalfAddr & 0x0000FFFFu) | ((static_cast<uint32_t>(value) & 0x1Fu) << 16u)) & kSoundRamHalfMask;
            break;
        case 0x1AAu:
            state.transferHalfAddr =
                ((state.transferHalfAddr & 0xFFFF0000u) | value) & kSoundRamHalfMask;
            break;
        case 0x1ACu:
        {
            const uint32_t byteAddr = (state.transferHalfAddr & kSoundRamHalfMask) * 2u;
            m_soundRam[byteAddr] = static_cast<uint8_t>(value & 0xFFu);
            m_soundRam[byteAddr + 1u] = static_cast<uint8_t>((value >> 8u) & 0xFFu);
            state.transferHalfAddr = (state.transferHalfAddr + 1u) & kSoundRamHalfMask;
            break;
        }
        case 0x1B0u:
            state.admas = value;
            break;
        case 0x344u:
            state.statx = value;
            break;
        default:
            break;
        }
    }

    uint16_t IopSpu2::readGlobalReg16(uint32_t offset) const
    {
        switch (offset)
        {
        case 0x760u:
            return m_cores[0].mvolL;
        case 0x762u:
            return m_cores[0].mvolR;
        case 0x788u:
            return m_cores[1].mvolL;
        case 0x78Au:
            return m_cores[1].mvolR;
        default:
            return m_regs[offset / 2u];
        }
    }

    void IopSpu2::writeGlobalReg16(uint32_t offset, uint16_t value)
    {
        switch (offset)
        {
        case 0x760u:
            m_cores[0].mvolL = value;
            break;
        case 0x762u:
            m_cores[0].mvolR = value;
            break;
        case 0x788u:
            m_cores[1].mvolL = value;
            break;
        case 0x78Au:
            m_cores[1].mvolR = value;
            break;
        default:
            break;
        }
    }

    void IopSpu2::keyOnVoices(uint32_t core, uint32_t mask)
    {
        CoreState &state = m_cores[core];
        if (std::getenv("PS2_M07_DIAG") && mask != 0u)
        {
            static uint32_t s_konDiag = 0u;
            if (s_konDiag < 32u)
            {
                std::cerr << "[M07_SPU2_KON] core=" << core << " mask=0x" << std::hex << mask
                          << " mvolL=0x" << state.mvolL << " mvolR=0x" << state.mvolR << std::dec << std::endl;
                ++s_konDiag;
            }
        }
        for (uint32_t v = 0; v < VoicesPerCore; ++v)
        {
            if ((mask & (1u << v)) == 0u)
                continue;
            Voice &voice = state.voices[v];
            voice.currentHalfAddr = voice.ssaHalfAddr & kSoundRamHalfMask;
            voice.phaseFrac = 0u;
            voice.hist1 = 0;
            voice.hist2 = 0;
            voice.blockSampleIndex = 28u;
            voice.decodedBlock.fill(0);
            voice.active = true;
            voice.release = false;
            voice.envelope = 1.0f;
            voice.envx = 0x7FFFu;
            state.endx &= ~(1u << v);
        }
    }

    void IopSpu2::keyOffVoices(uint32_t core, uint32_t mask)
    {
        CoreState &state = m_cores[core];
        for (uint32_t v = 0; v < VoicesPerCore; ++v)
        {
            if ((mask & (1u << v)) == 0u)
                continue;
            Voice &voice = state.voices[v];
            if (voice.active)
                voice.release = true;
        }
    }

    void IopSpu2::handleDmaTransfer(uint32_t core, uint32_t madr, uint32_t byteCount, uint32_t chcr, IopMemory &memory)
    {
        if (core >= CoreCount || byteCount == 0u)
            return;

        CoreState &state = m_cores[core];
        const bool isWriteToSpu = (chcr & 1u) != 0u;
        const std::span<const uint8_t> iopRam = memory.ram();
        const uint32_t srcOffset = IopMemory::physicalAddress(madr);

        if (!isWriteToSpu)
        {
            if (srcOffset < iopRam.size())
            {
                const uint32_t copyBytes = std::min<uint32_t>(byteCount, static_cast<uint32_t>(iopRam.size() - srcOffset));
                std::vector<uint8_t> temp(copyBytes);
                for (uint32_t i = 0; i < copyBytes; ++i)
                {
                    const uint32_t ramAddr = ((state.transferHalfAddr * 2u) + i) % SoundRamSize;
                    temp[i] = m_soundRam[ramAddr];
                }
                (void)memory.writeRam(srcOffset, temp.data(), copyBytes);
                state.transferHalfAddr = (state.transferHalfAddr + (copyBytes / 2u)) & kSoundRamHalfMask;
            }
            state.statx |= 0x0080u;
            return;
        }

        if (srcOffset >= iopRam.size())
        {
            state.statx |= 0x0080u;
            return;
        }

        const uint32_t available = std::min<uint32_t>(byteCount, static_cast<uint32_t>(iopRam.size() - srcOffset));
        const uint8_t *src = iopRam.data() + srcOffset;

        // LIBSD sets ADMAS bit 0 (Core 0) and bit 1 (Core 1) — also tolerate core-local bit 0 on Core 1.
        const uint16_t admasCombined = static_cast<uint16_t>(m_cores[0].admas | state.admas);
        const bool isAutoDma = ((admasCombined & (1u << core)) != 0u) || (core == 1u && (state.admas & 0x1u) != 0u);
        if (std::getenv("PS2_M07_DIAG"))
        {
            static uint32_t s_dmaDiagCount = 0u;
            bool anyNonZero = false;
            for (uint32_t i = 0; i < available; ++i)
            {
                if (src[i] != 0u)
                {
                    anyNonZero = true;
                    break;
                }
            }
            if (s_dmaDiagCount < 16u || anyNonZero)
            {
                static uint32_t s_nonZeroDiag = 0u;
                if (s_dmaDiagCount < 16u || s_nonZeroDiag < 16u)
                {
                    std::cerr << "[M07_SPU2_DMA] core=" << core << " bytes=" << available
                              << " admas0=0x" << std::hex << m_cores[0].admas
                              << " admas=" << state.admas << " mvolL=" << state.mvolL
                              << " mvolR=" << state.mvolR << std::dec
                              << " auto=" << isAutoDma << " nz=" << anyNonZero << std::endl;
                    if (anyNonZero)
                        ++s_nonZeroDiag;
                }
                ++s_dmaDiagCount;
            }
        }

        if (isAutoDma)
        {
            // SPU2 AutoDMA feeds planar 512-byte Left + 512-byte Right blocks (256 stereo frames / 1024 bytes).
            uint32_t pos = 0;
            while (pos + kAutoDmaBlockBytes <= available)
            {
                const uint8_t *leftPtr = src + pos;
                const uint8_t *rightPtr = src + pos + kAutoDmaChannelBytes;
                for (size_t s = 0; s < kAutoDmaChannelBytes / 2u; ++s)
                {
                    state.autoDmaSamples.push_back(readLe16(leftPtr + s * 2u));
                    state.autoDmaSamples.push_back(readLe16(rightPtr + s * 2u));
                }
                pos += kAutoDmaBlockBytes;
            }
            while (pos + 4u <= available)
            {
                state.autoDmaSamples.push_back(readLe16(src + pos));
                state.autoDmaSamples.push_back(readLe16(src + pos + 2u));
                pos += 4u;
            }
            while (state.autoDmaSamples.size() > kMaxAutoDmaBufferedFrames * 2u)
            {
                state.autoDmaSamples.pop_front();
                state.autoDmaSamples.pop_front();
            }
        }
        else
        {
            uint32_t dstByte = (state.transferHalfAddr & kSoundRamHalfMask) * 2u;
            for (uint32_t i = 0; i < available; ++i)
            {
                m_soundRam[dstByte] = src[i];
                dstByte = (dstByte + 1u) % SoundRamSize;
            }
            state.transferHalfAddr = (dstByte / 2u) & kSoundRamHalfMask;
        }

        state.statx |= 0x0080u;
    }

    void IopSpu2::decodeNextAdpcmBlock(uint32_t core, Voice &voice, uint32_t voiceIndex)
    {
        const uint32_t blockByteAddr = (voice.currentHalfAddr & kSoundRamHalfMask) * 2u;
        if (blockByteAddr + 16u > SoundRamSize)
        {
            voice.decodedBlock.fill(0);
            voice.blockSampleIndex = 0u;
            voice.active = false;
            m_cores[core].endx |= (1u << voiceIndex);
            return;
        }

        const uint8_t *blk = m_soundRam.data() + blockByteAddr;
        uint32_t shift = blk[0] & 0x0Fu;
        if (shift > 12u)
            shift = 9u;
        const uint32_t filter = std::min<uint32_t>((blk[0] >> 4u) & 0x07u, 4u);
        const uint8_t flags = blk[1];

        if ((flags & 0x04u) != 0u)
            voice.lsaxHalfAddr = voice.currentHalfAddr;

        const int32_t f0 = kAdpcmPosCoeff[filter];
        const int32_t f1 = kAdpcmNegCoeff[filter];

        for (size_t i = 0; i < 28u; ++i)
        {
            const uint8_t byte = blk[2u + (i / 2u)];
            int32_t nibble = (i & 1u) == 0u ? (byte & 0x0Fu) : ((byte >> 4u) & 0x0Fu);
            if (nibble >= 8)
                nibble -= 16;

            int32_t sample = (nibble << (12u - shift)) + ((voice.hist1 * f0 + voice.hist2 * f1 + 32) >> 6);
            sample = std::clamp(sample, -32768, 32767);
            voice.hist2 = voice.hist1;
            voice.hist1 = sample;
            voice.decodedBlock[i] = static_cast<int16_t>(sample);
        }

        voice.blockSampleIndex = 0u;
        voice.currentHalfAddr = (voice.currentHalfAddr + 8u) & kSoundRamHalfMask;

        if ((flags & 0x01u) != 0u)
        {
            m_cores[core].endx |= (1u << voiceIndex);
            if ((flags & 0x02u) != 0u)
            {
                voice.currentHalfAddr = voice.lsaxHalfAddr & kSoundRamHalfMask;
            }
            else
            {
                voice.active = false;
            }
        }
    }

    int16_t IopSpu2::sampleVoice(uint32_t core, uint32_t voiceIndex, float &outL, float &outR)
    {
        Voice &voice = m_cores[core].voices[voiceIndex];
        if (!voice.active)
            return 0;

        if (voice.blockSampleIndex >= 28u)
        {
            decodeNextAdpcmBlock(core, voice, voiceIndex);
            if (!voice.active && voice.blockSampleIndex >= 28u)
                return 0;
        }

        const int16_t rawSample = voice.decodedBlock[voice.blockSampleIndex];
        const float env = voice.envelope;
        const float sampleF = static_cast<float>(rawSample) * env;
        outL += sampleF * volumeRegToFloat(voice.voll);
        outR += sampleF * volumeRegToFloat(voice.volr);

        if (voice.release)
        {
            voice.envelope = std::max(0.0f, voice.envelope - (1.0f / 256.0f));
            voice.envx = static_cast<uint16_t>(voice.envelope * 32767.0f);
            if (voice.envelope <= 0.0f)
                voice.active = false;
        }

        const uint32_t pitch = std::max<uint32_t>(voice.pitch, 1u);
        voice.phaseFrac += pitch;
        while (voice.phaseFrac >= 0x1000u)
        {
            voice.phaseFrac -= 0x1000u;
            ++voice.blockSampleIndex;
            if (voice.blockSampleIndex >= 28u)
            {
                if (!voice.active)
                    break;
                decodeNextAdpcmBlock(core, voice, voiceIndex);
            }
        }

        return rawSample;
    }

    void IopSpu2::synthesizeSample(float &outL, float &outR)
    {
        outL = 0.0f;
        outR = 0.0f;

        for (uint32_t core = 0; core < CoreCount; ++core)
        {
            CoreState &state = m_cores[core];
            float coreL = 0.0f;
            float coreR = 0.0f;

            for (uint32_t v = 0; v < VoicesPerCore; ++v)
            {
                if (state.voices[v].active)
                    (void)sampleVoice(core, v, coreL, coreR);
            }

            if (state.autoDmaSamples.size() >= 2u)
            {
                coreL += static_cast<float>(state.autoDmaSamples[0]);
                coreR += static_cast<float>(state.autoDmaSamples[1]);
                state.autoDmaSamples.pop_front();
                state.autoDmaSamples.pop_front();
            }

            outL += coreL * volumeRegToFloat(state.mvolL);
            outR += coreR * volumeRegToFloat(state.mvolR);
        }
    }

    void IopSpu2::stepCycles(uint64_t cycles, IopHost &host)
    {
        m_cycleAccumulator += cycles;
        while (m_cycleAccumulator >= CyclesPerSample)
        {
            m_cycleAccumulator -= CyclesPerSample;
            float left = 0.0f;
            float right = 0.0f;
            synthesizeSample(left, right);
            m_outputBuffer.push_back(static_cast<int16_t>(std::clamp(static_cast<int32_t>(std::lround(left)), -32768, 32767)));
            m_outputBuffer.push_back(static_cast<int16_t>(std::clamp(static_cast<int32_t>(std::lround(right)), -32768, 32767)));

            if (m_outputBuffer.size() >= OutputBatchFrames * 2u)
            {
                host.submitAudioPcm(m_outputBuffer.data(), m_outputBuffer.size() / 2u, SampleRate);
                m_outputBuffer.clear();
            }
        }
    }

    void IopSpu2::flushPendingAudio(IopHost &host)
    {
        if (!m_outputBuffer.empty())
        {
            host.submitAudioPcm(m_outputBuffer.data(), m_outputBuffer.size() / 2u, SampleRate);
            m_outputBuffer.clear();
        }
    }

    bool IopSpu2::isVoiceActive(uint32_t core, uint32_t voiceIndex) const noexcept
    {
        if (core >= CoreCount || voiceIndex >= VoicesPerCore)
            return false;
        return m_cores[core].voices[voiceIndex].active;
    }

    size_t IopSpu2::pendingAutoDmaFrames(uint32_t core) const noexcept
    {
        if (core >= CoreCount)
            return 0u;
        return m_cores[core].autoDmaSamples.size() / 2u;
    }
}
