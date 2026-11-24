#include "ps2_recompiled_functions.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "rozu_layout_generated.h"

#include <cfenv>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace
{
    int g_failures = 0;

    void check(bool cond, const char *desc)
    {
        if (!cond)
        {
            std::fprintf(stderr, "FAIL: %s\n", desc);
            ++g_failures;
        }
        else
        {
            std::printf("PASS: %s\n", desc);
        }
    }

    uint32_t readU32(const uint8_t *rdram, uint32_t addr)
    {
        uint32_t val = 0;
        std::memcpy(&val, rdram + (addr & PS2_RAM_MASK), sizeof(val));
        return val;
    }

    void writeU32(uint8_t *rdram, uint32_t addr, uint32_t val)
    {
        std::memcpy(rdram + (addr & PS2_RAM_MASK), &val, sizeof(val));
    }

    uint32_t floatBits(float v)
    {
        uint32_t bits = 0;
        std::memcpy(&bits, &v, sizeof(bits));
        return bits;
    }
}

int main()
{
    std::fesetround(FE_TOWARDZERO);
    _MM_SET_ROUNDING_MODE(_MM_ROUND_TOWARD_ZERO);

    PS2Runtime runtime;
    check(runtime.memory().initialize(), "PS2Runtime 32MB RDRAM initialize");
    uint8_t *rdram = runtime.memory().getRDRAM();
    check(rdram != nullptr, "RDRAM pointer non-null");

    check(rozu::generated::kBootEntry == 0x00100008u, "layout header kBootEntry == 0x00100008");
    check(rozu::generated::kVutextStart == 0x00291230u && rozu::generated::kVutextEnd == 0x002953B0u,
          "layout header .vutext range matches SLUS-21448");

    R5900Context ctxStorage;
    R5900Context *ctx = &ctxStorage;
    constexpr uint32_t kReturnPc = 0x0010DEADu;
    constexpr uint32_t kDummyActor = 0x00900000u;

    // 1. DogActor::setId / getId (sw/lw at +0x01A0)
    SET_GPR_U32(ctx, 4, kDummyActor);
    SET_GPR_U32(ctx, 5, 0x0000A55Au);
    SET_GPR_U32(ctx, 31, kReturnPc);
    fn_00280fd4_setId_8DogActori_0x280fd4(rdram, ctx, &runtime);
    check(ctx->pc == kReturnPc, "setId returns to $ra");
    check(readU32(rdram, kDummyActor + 0x01A0u) == 0x0000A55Au,
          "setId stores ID at RDRAM[obj + 0x1A0]");

    SET_GPR_U32(ctx, 2, 0u);
    SET_GPR_U32(ctx, 4, kDummyActor);
    SET_GPR_U32(ctx, 31, kReturnPc);
    fn_00280fdc_getId_C8DogActor_0x280fdc(rdram, ctx, &runtime);
    check(ctx->pc == kReturnPc, "getId returns to $ra");
    check(GPR_U32(ctx, 2) == 0x0000A55Au, "getId loads ID into $v0");

    // 2. DogActor::setMotionSpeed / getMotionSpeed (swc1/lwc1 at +0x01E8)
    const float expectedSpeed = 1.375f;
    SET_GPR_U32(ctx, 4, kDummyActor);
    ctx->f[12] = expectedSpeed;
    SET_GPR_U32(ctx, 31, kReturnPc);
    fn_00281020_setMotionSpeed_8DogActorf_0x281020(rdram, ctx, &runtime);
    check(ctx->pc == kReturnPc, "setMotionSpeed returns to $ra");
    check(readU32(rdram, kDummyActor + 0x01E8u) == floatBits(expectedSpeed),
          "setMotionSpeed stores IEEE float at RDRAM[obj + 0x1E8]");

    ctx->f[0] = 0.0f;
    SET_GPR_U32(ctx, 4, kDummyActor);
    SET_GPR_U32(ctx, 31, kReturnPc);
    fn_00281028_getMotionSpeed_C8DogActor_0x281028(rdram, ctx, &runtime);
    check(floatBits(ctx->f[0]) == floatBits(expectedSpeed),
          "getMotionSpeed returns exact IEEE float bits in $f0");

    // 3. DogActor::setBaseRotate(x, y, z) (+0x03C0 vec4 with W = 1.0f)
    SET_GPR_U32(ctx, 4, kDummyActor);
    ctx->f[12] = -0.25f;
    ctx->f[13] = 3.5f;
    ctx->f[14] = 12.125f;
    SET_GPR_U32(ctx, 31, kReturnPc);
    fn_0028126c_setBaseRotate_8DogActorfff_0x28126c(rdram, ctx, &runtime);
    check(readU32(rdram, kDummyActor + 0x03C0u) == floatBits(-0.25f) &&
              readU32(rdram, kDummyActor + 0x03C4u) == floatBits(3.5f) &&
              readU32(rdram, kDummyActor + 0x03C8u) == floatBits(12.125f) &&
              readU32(rdram, kDummyActor + 0x03CCu) == floatBits(1.0f),
          "setBaseRotate stores (x, y, z, 1.0f) vector at +0x3C0");

    // 4. .text branch + delay-slot + movn classifier (sub_00103390)
    SET_GPR_U32(ctx, 4, 5u << 23);
    SET_GPR_U32(ctx, 31, kReturnPc);
    sub_00103390_0x103390(rdram, ctx, &runtime);
    check(GPR_U32(ctx, 2) == 1u, "sub_00103390(5 << 23) == 1 (beq + delay slot)");

    SET_GPR_U32(ctx, 4, 6u << 23);
    SET_GPR_U32(ctx, 31, kReturnPc);
    sub_00103390_0x103390(rdram, ctx, &runtime);
    check(GPR_U32(ctx, 2) == 2u, "sub_00103390(6 << 23) == 2 (movn not taken)");

    SET_GPR_U32(ctx, 4, 9u << 23);
    SET_GPR_U32(ctx, 31, kReturnPc);
    sub_00103390_0x103390(rdram, ctx, &runtime);
    check(GPR_U32(ctx, 2) == 0u, "sub_00103390(9 << 23) == 0 (movn clears $v0)");

    // 5. .text R5900 3-operand mult LCG PRNG step (sub_001041c4)
    constexpr uint32_t kSeedAddr = 0x00308484u;
    const int64_t seed0 = 0x12345678;
    writeU32(rdram, kSeedAddr, static_cast<uint32_t>(seed0));
    SET_GPR_U32(ctx, 31, kReturnPc);
    sub_001041c4_0x1041c4(rdram, ctx, &runtime);
    const uint32_t seed1 = static_cast<uint32_t>(seed0 * 1897 + 31993);
    check(GPR_U32(ctx, 2) == seed1 && readU32(rdram, kSeedAddr) == seed1,
          "sub_001041c4 LCG step 1 matches R5900 mult + sw in delay slot");

    SET_GPR_U32(ctx, 31, kReturnPc);
    sub_001041c4_0x1041c4(rdram, ctx, &runtime);
    const uint32_t seed2 = static_cast<uint32_t>(static_cast<int64_t>(static_cast<int32_t>(seed1)) * 1897 + 31993);
    check(GPR_U32(ctx, 2) == seed2 && readU32(rdram, kSeedAddr) == seed2,
          "sub_001041c4 LCG step 2 chains deterministically via RDRAM");

    if (g_failures != 0)
    {
        std::fprintf(stderr, "rozu_poc_test FAILED (%d assertion(s))\n", g_failures);
        return 1;
    }
    std::printf("rozu_poc_test PASSED (all assertions)\n");
    return 0;
}
