#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <vector>

namespace ps2x::iop
{
    class IopHost;
}

namespace ps2x::iop::detail
{
    class IopMemory;

    /// Lightweight PS2 SPU2 synthesizer supporting 48 PS-ADPCM voices and Core 0/1 AutoDMA PCM streams.
    class IopSpu2
    {
    public:
        static constexpr uint32_t BaseAddress = 0x1F900000u;
        static constexpr uint32_t RegisterSpan = 0x00000800u;
        static constexpr uint32_t SoundRamSize = 2u * 1024u * 1024u; // 2 MiB SPU2 RAM
        static constexpr uint32_t VoicesPerCore = 24u;
        static constexpr uint32_t CoreCount = 2u;
        static constexpr uint32_t SampleRate = 48000u;
        static constexpr uint64_t CyclesPerSample = 768u; // 36.864 MHz / 48000 Hz
        static constexpr size_t OutputBatchFrames = 256u;

        struct Voice
        {
            uint16_t voll = 0;
            uint16_t volr = 0;
            uint16_t pitch = 0x1000u;
            uint16_t adsr1 = 0;
            uint16_t adsr2 = 0;
            uint16_t envx = 0;
            uint16_t volxl = 0;
            uint16_t volxr = 0;

            uint32_t ssaHalfAddr = 0;
            uint32_t lsaxHalfAddr = 0;
            uint32_t currentHalfAddr = 0;

            bool active = false;
            bool release = false;
            float envelope = 0.0f;

            uint32_t phaseFrac = 0; // 16.12 fixed-point sample phase (0x1000 = 1 ADPCM sample)
            int32_t hist1 = 0;
            int32_t hist2 = 0;
            std::array<int16_t, 28> decodedBlock{};
            uint32_t blockSampleIndex = 28u;
        };

        struct CoreState
        {
            std::array<Voice, VoicesPerCore> voices{};
            uint16_t coreAttr = 0;
            uint16_t admas = 0;
            uint16_t statx = 0;
            uint16_t mmix = 0x0FFFu;
            uint16_t mvolL = 0x3FFFu;
            uint16_t mvolR = 0x3FFFu;
            uint32_t kon = 0;
            uint32_t koff = 0;
            uint32_t endx = 0;
            uint32_t transferHalfAddr = 0;

            // Interleaved stereo PCM samples pushed by SPU2 AutoDMA blocks (512B L + 512B R).
            std::deque<int16_t> autoDmaSamples;
        };

        IopSpu2();

        void reset();

        [[nodiscard]] uint16_t read16(uint32_t physAddress) const;
        void write16(uint32_t physAddress, uint16_t value);

        void handleDmaTransfer(uint32_t core, uint32_t madr, uint32_t byteCount, uint32_t chcr, IopMemory &memory);
        void stepCycles(uint64_t cycles, IopHost &host);
        void flushPendingAudio(IopHost &host);

        [[nodiscard]] bool isVoiceActive(uint32_t core, uint32_t voiceIndex) const noexcept;
        [[nodiscard]] size_t pendingAutoDmaFrames(uint32_t core) const noexcept;
        [[nodiscard]] const std::vector<uint8_t> &soundRam() const noexcept { return m_soundRam; }

    private:
        void writeCoreReg16(uint32_t core, uint32_t regOffset, uint16_t value);
        [[nodiscard]] uint16_t readCoreReg16(uint32_t core, uint32_t regOffset) const;
        void writeGlobalReg16(uint32_t offset, uint16_t value);
        [[nodiscard]] uint16_t readGlobalReg16(uint32_t offset) const;

        void keyOnVoices(uint32_t core, uint32_t mask);
        void keyOffVoices(uint32_t core, uint32_t mask);
        void decodeNextAdpcmBlock(uint32_t core, Voice &voice, uint32_t voiceIndex);
        int16_t sampleVoice(uint32_t core, uint32_t voiceIndex, float &outL, float &outR);
        void synthesizeSample(float &outL, float &outR);

        std::vector<uint8_t> m_soundRam;
        std::array<uint16_t, RegisterSpan / 2u> m_regs{};
        std::array<CoreState, CoreCount> m_cores{};
        uint64_t m_cycleAccumulator = 0;
        std::vector<int16_t> m_outputBuffer;
    };
}
