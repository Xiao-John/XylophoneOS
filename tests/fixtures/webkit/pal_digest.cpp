// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include <pal/crypto/CryptoDigest.h>

#include <array>
#include <cstdio>
#include <span>
#include <string_view>
#include <wtf/MainThread.h>

using PAL::Crypto::CryptoDigest;

static bool matchesDigest(CryptoDigest::Algorithm algorithm, std::string_view expected)
{
    static constexpr std::array<uint8_t, 3> input { 'a', 'b', 'c' };
    static constexpr std::string_view hex = "0123456789abcdef";
    auto digest = CryptoDigest::create(algorithm);
    if (!digest)
        return false;
    digest->addBytes(std::span { input }.first(1));
    digest->addBytes(std::span { input }.subspan(1));
    const auto result = digest->computeHash();
    if (result.size() * 2 != expected.size())
        return false;
    for (size_t i = 0; i < result.size(); ++i) {
        if (hex[result[i] >> 4] != expected[2 * i] || hex[result[i] & 0x0f] != expected[2 * i + 1])
            return false;
    }
    return true;
}

int main()
{
    WTF::initializeMainThread();
    using Algorithm = CryptoDigest::Algorithm;
    if (!matchesDigest(Algorithm::SHA_1, "a9993e364706816aba3e25717850c26c9cd0d89d"))
        return 1;
    if (!matchesDigest(Algorithm::SHA_256, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"))
        return 2;
    if (!matchesDigest(Algorithm::SHA_384, "cb00753f45a35e8bb5a03d699ac65007272c32ab0eded1631a8b605a43ff5bed"
            "8086072ba1e7cc2358baeca134c825a7"))
        return 3;
    if (!matchesDigest(Algorithm::SHA_512, "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
            "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f"))
        return 4;
    std::puts("XOS_WEBCORE_PAL_DIGEST_OK sha1 sha256 sha384 sha512 streaming");
    return 0;
}
