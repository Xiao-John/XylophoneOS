// SPDX-License-Identifier: Apache-2.0
#include "include/core/SkCanvas.h"
#include "include/core/SkFont.h"
#include "include/core/SkFontMgr.h"
#include "include/core/SkImageInfo.h"
#include "include/core/SkPaint.h"
#include "include/core/SkPixmap.h"
#include "include/core/SkStream.h"
#include "include/core/SkSurface.h"
#include "include/core/SkTypeface.h"
#include "include/ports/SkFontMgr_empty.h"
#include "src/core/SkOSFile.h"
#include <array>
#include <cerrno>
#include <cstdio>
#include <limits>
#include <memory>
#include <sys/stat.h>
#include <unistd.h>

static bool check_positioned_stream(const char* path)
{
    std::unique_ptr<FILE, decltype(&std::fclose)> file(std::fopen(path, "rb"), std::fclose);
    if (!file)
        return false;
    const int fd = fileno(file.get());
    struct stat info = {};
    if (fd < 0 || fstat(fd, &info) || !S_ISREG(info.st_mode) || info.st_size < 9000)
        return false;
    const size_t length = static_cast<size_t>(info.st_size);
    std::array<unsigned char, 8192> expected{}, got{};
    if (std::fseek(file.get(), 31, SEEK_SET) || std::fread(expected.data(), 1, expected.size(), file.get()) != expected.size()
        || std::fseek(file.get(), 0, SEEK_SET))
        return false;

    FILE* underlying = file.release();
    SkFILEStream stream(underlying);
    if (std::fseek(underlying, 11, SEEK_SET))
        return false;
    const auto descriptor_position = lseek(fd, 0, SEEK_CUR);
    if (descriptor_position < 0 || stream.getLength() != length || !stream.seek(31)
        || stream.read(got.data(), got.size()) != got.size() || got != expected
        || stream.getPosition() != 31 + got.size() || std::ftell(underlying) != 11 || lseek(fd, 0, SEEK_CUR) != descriptor_position)
        return false;

    constexpr size_t tail = 17;
    if (sk_qread(underlying, got.data(), got.size(), length - tail) != tail
        || sk_qread(underlying, got.data(), got.size(), length) != 0
        || sk_qread(underlying, got.data(), got.size(), 0xfffffffeULL) != 0
        || sk_qread(underlying, nullptr, 0, 19) != 0)
        return false;
    errno = 0;
    if (sk_qread(underlying, got.data(), got.size(), 0xffffffffULL) != SIZE_MAX || errno != EOVERFLOW)
        return false;
    errno = 0;
    if (sk_qread(underlying, got.data(), got.size(), std::numeric_limits<size_t>::max()) != SIZE_MAX || errno != EOVERFLOW)
        return false;
    if (std::ftell(underlying) != 11 || lseek(fd, 0, SEEK_CUR) != descriptor_position)
        return false;
    std::puts("XOS_SKIA_FILE_STREAM_PASS full=8192 tail=17 eof=0 offsets=preserved overflow=checked");
    return true;
}

int main(int argc, char** argv)
{
    if (argc != 2)
        return 2;
    auto manager = SkFontMgr_New_Custom_Empty();
    auto typeface = manager ? manager->makeFromFile(argv[1]) : nullptr;
    if (!typeface) {
        std::puts("XOS_SKIA_FAT_FONT_UNAVAILABLE");
        return 3;
    }
    if (!check_positioned_stream(argv[1]))
        return 4;
    SkFont font(typeface, 18);
    const char text[] = "XOS";
    SkGlyphID glyphs[3]{};
    if (font.textToGlyphs(text, 3, SkTextEncoding::kUTF8, glyphs) != 3 || !glyphs[0] || !glyphs[1] || !glyphs[2])
        return 5;
    auto surface = SkSurfaces::Raster(SkImageInfo::MakeN32Premul(70, 24));
    if (!surface)
        return 6;
    auto* canvas = surface->getCanvas();
    canvas->clear(SK_ColorWHITE);
    SkPaint paint;
    paint.setColor(SK_ColorBLACK);
    canvas->drawSimpleText(text, 3, SkTextEncoding::kUTF8, 4, 18, font, paint);
    SkPixmap pixels;
    if (!surface->peekPixels(&pixels) || pixels.getColor(0, 0) != SK_ColorWHITE)
        return 7;
    unsigned ink = 0;
    for (int y = 0; y < pixels.height(); ++y)
        for (int x = 0; x < pixels.width(); ++x)
            ink += pixels.getColor(x, y) != SK_ColorWHITE;
    if (ink == 0 || ink >= 70U * 24)
        return 8;
    std::printf("XOS_SKIA_FAT_FONT_PASS glyphs=%u,%u,%u ink=%u\n",
        static_cast<unsigned>(glyphs[0]), static_cast<unsigned>(glyphs[1]), static_cast<unsigned>(glyphs[2]), ink);
    return 0;
}
