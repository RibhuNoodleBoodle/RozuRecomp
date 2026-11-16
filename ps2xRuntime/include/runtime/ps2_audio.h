#ifndef PS2_AUDIO_H
#define PS2_AUDIO_H

#include <cstddef>
#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <vector>

class PS2AudioBackend
{
public:
    struct AudioStats
    {
        uint64_t totalFrames = 0;
        uint64_t nonZeroFrames = 0;
        int32_t peakAbsSample = 0;
        double rms = 0.0;
    };

    PS2AudioBackend();
    ~PS2AudioBackend();

    void onVagTransfer(const uint8_t *rdram, uint32_t srcAddr, uint32_t sizeBytes);
    void onVagTransferFromBuffer(const uint8_t *data, uint32_t sizeBytes, uint32_t keyAddr);
    void onSoundCommand(uint32_t sid, uint32_t rpcNum,
                        const uint8_t *sendBuf, uint32_t sendSize,
                        uint8_t *recvBuf, uint32_t recvSize);
    void onPcmSamples(const int16_t *samples, size_t frameCount, uint32_t sampleRate);
    void serviceStream();

    void play(uint32_t sampleAddr, float pitch = 1.0f, float volume = 1.0f,
              uint32_t voiceIndex = 0xFFFFFFFFu);
    void stop(uint32_t voiceId);
    void stopAll();
    void setAudioReady(bool ready) { m_audioReady = ready; }

    [[nodiscard]] AudioStats audioStats() const;
    void resetStats();

private:
    struct DecodedSample
    {
        std::vector<int16_t> pcm;
        uint32_t sampleRate = 44100;
    };

    struct Impl;
    std::unique_ptr<Impl> m_impl;
    bool m_audioReady = false;
    uint32_t m_mostRecentSampleKey = 0;
    std::vector<DecodedSample> m_loadOrderSamples;
    std::vector<uint32_t> m_loadOrderSampleKeys;
    std::unordered_map<uint32_t, DecodedSample> m_sampleBank;
    std::deque<int16_t> m_streamPcmQueue;
    uint64_t m_totalFrames = 0;
    uint64_t m_nonZeroFrames = 0;
    uint64_t m_totalSamples = 0;
    double m_sumSquares = 0.0;
    int32_t m_peakAbsSample = 0;
    mutable std::mutex m_mutex;

    void playDecodedSample(uint32_t sampleKey, DecodedSample &sample, float pitch, float volume,
                          bool isBgm = false);
    void pruneFinishedSounds();
};

#endif
