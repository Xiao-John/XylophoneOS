// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstddef>
#include <cstdint>
namespace aurora {
// Deterministic separable box blur; premultiplied ARGB words. Clamped edges,
// rounded channel means, caller-owned distinct buffers, no allocation or threads.
bool box_blur_argb32(const std::uint32_t *input,std::uint32_t *output,
                    std::uint32_t *scratch,std::size_t width,std::size_t height,
                    std::size_t capacity,unsigned radius);
}
