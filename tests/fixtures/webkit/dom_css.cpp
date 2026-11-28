// SPDX-License-Identifier: Apache-2.0
#include "page.hpp"
#include <array>
#include <cstdio>
#include <cstring>

namespace {
using clarke_page::rectangle;
struct pixel { unsigned x, y; unsigned char red, green, blue; };
std::array<unsigned char, 320 * 180 * 4> rgba{};
char html[65537];
bool bounds(const rectangle& actual, const rectangle& expected) {
    return actual.found && actual.x == expected.x && actual.y == expected.y &&
        actual.width == expected.width && actual.height == expected.height;
}
}
int main(int argc, char** argv) {
    if (argc != 4) return 2;
    auto* source = std::fopen(argv[2], "rb");
    if (!source) return 3;
    const auto size = std::fread(html, 1, sizeof(html), source);
    const bool complete = std::feof(source) && !std::ferror(source);
    if (std::fclose(source) || !complete || !size || size > 65536) return 4;
    rectangle expected[5]{}; unsigned count = 0;
    pixel samples[6]{}; unsigned sample_count = 0;
    bool text = false;
    if (!std::strcmp(argv[1], "box")) {
        expected[count++] = {"panel", true, 12, 12, 144, 84}; expected[count++] = {"inside", true, 24, 24, 50, 20};
        samples[sample_count++] = {12,12,0,0,0}; samples[sample_count++] = {20,20,255,255,0};
        samples[sample_count++] = {30,30,255,0,0}; samples[sample_count++] = {0,0,255,255,255};
    } else if (!std::strcmp(argv[1], "flex")) {
        expected[count++] = {"row", true, 10,20,240,60}; expected[count++] = {"one",true,10,40,50,20};
        expected[count++] = {"two",true,70,30,180,40};
        samples[sample_count++] = {20,45,255,0,0}; samples[sample_count++] = {80,40,0,128,0}; samples[sample_count++] = {65,45,255,255,255};
    } else if (!std::strcmp(argv[1], "grid")) {
        expected[count++] = {"grid",true,16,16,200,100}; expected[count++] = {"a",true,16,16,60,30};
        expected[count++] = {"b",true,86,16,130,30}; expected[count++] = {"c",true,16,56,60,60}; expected[count++] = {"d",true,86,56,130,60};
        samples[sample_count++] = {20,20,255,0,0}; samples[sample_count++] = {100,20,0,0,255};
        samples[sample_count++] = {20,70,255,255,0}; samples[sample_count++] = {100,70,0,128,0}; samples[sample_count++] = {80,50,255,255,255};
    } else if (!std::strcmp(argv[1], "cascade")) {
        expected[count++] = {"target",true,20,20,84,44}; expected[count++] = {"inside",true,26,26,20,10};
        samples[sample_count++] = {20,20,0,0,255}; samples[sample_count++] = {24,24,0,128,0}; samples[sample_count++] = {120,100,255,255,255};
    } else if (!std::strcmp(argv[1], "clip")) {
        expected[count++] = {"clip",true,20,20,100,60}; expected[count++] = {"moved",true,80,50,80,40};
        samples[sample_count++] = {90,60,255,0,0}; samples[sample_count++] = {125,65,255,255,255}; samples[sample_count++] = {30,30,255,255,0};
    } else if (!std::strcmp(argv[1], "text")) {
        expected[count++] = {"text",true,12,16,260,30}; text = true;
        samples[sample_count++] = {0,0,255,255,255};
    } else return 5;
    rectangle actual[5]{};
    for (unsigned i = 0; i < count; ++i) actual[i].id = expected[i].id;
    if (!clarke_page::render(html, size, rgba.data(), actual, count)) return 6;
    for (unsigned i = 0; i < count; ++i) {
        std::printf("CLARKE_DOM id=%s found=%u x=%.2f y=%.2f width=%.2f height=%.2f\n",
                    actual[i].id, actual[i].found, actual[i].x, actual[i].y, actual[i].width, actual[i].height);
        if (!bounds(actual[i], expected[i])) return 10;
    }
    for (unsigned i = 0; i < sample_count; ++i) {
        const auto& sample = samples[i]; const auto* pixel = rgba.data() + (sample.y * 320 + sample.x) * 4;
        if (pixel[0] != sample.red || pixel[1] != sample.green || pixel[2] != sample.blue || pixel[3] != 255) return 11;
    }
    if (text) {
        unsigned dark = 0, red = 0;
        for (unsigned y = 16; y < 46; ++y) for (unsigned x = 12; x < 272; ++x) {
            const auto* pixel = rgba.data() + (y * 320 + x) * 4;
            dark += pixel[0] < 64 && pixel[1] < 64 && pixel[2] < 64;
            red += pixel[0] > 180 && pixel[1] < 100 && pixel[2] < 100;
        }
        std::printf("CLARKE_TEXT dark=%u red=%u\n", dark, red);
        if (dark < 40 || red < 10) return 12;
    }
    auto* output = std::fopen(argv[3], "wb");
    if (!output) return 13;
    bool written = std::fprintf(output, "P6\n320 180\n255\n") > 0;
    for (unsigned i = 0; written && i < 320 * 180; ++i) written = std::fwrite(rgba.data() + i * 4, 1, 3, output) == 3;
    if (std::fclose(output) || !written) return 14;
    std::printf("XOS_WEBCORE_DOM_CSS_PASS case=%s rectangles=%u pixels=%u viewport=320x180\n", argv[1], count, sample_count);
    return 0;
}
