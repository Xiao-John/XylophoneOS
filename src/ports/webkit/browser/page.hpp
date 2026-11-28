// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstddef>
#include <cstdint>

namespace clarke_page {
struct rectangle { const char* id; bool found; double x, y, width, height; };
bool render(const char* html, std::size_t length, std::uint8_t* rgba,
            rectangle* rectangles = nullptr, std::size_t count = 0);
}
