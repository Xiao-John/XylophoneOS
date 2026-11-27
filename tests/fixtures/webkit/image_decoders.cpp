// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include "ImageDecoder.h"
#include "SharedBuffer.h"
#include "image_decoder_data.h"

#include <array>
#include <cstdio>
#include <cstdlib>
#include <skia/core/SkColor.h>
#include <skia/core/SkImage.h>
#include <skia/core/SkPixmap.h>
#include <wtf/MainThread.h>

using namespace WebCore;

static RefPtr<ImageDecoder> decode(std::span<const uint8_t> bytes, const String& mimeType)
{
    auto buffer = SharedBuffer::create(bytes);
    auto decoder = ImageDecoder::create(buffer, mimeType, AlphaOption::NotPremultiplied,
        GammaAndColorProfileOption::Ignored);
    if (decoder)
        decoder->setData(buffer, true);
    return decoder;
}

static bool matchesTransparentImage(std::span<const uint8_t> bytes, const String& mimeType)
{
    auto decoder = decode(bytes, mimeType);
    if (!decoder || decoder->size() != IntSize { 2, 2 })
        return false;
    auto image = decoder->createFrameImageAtIndex(0);
    SkPixmap pixels;
    if (!image || !decoder->frameIsCompleteAtIndex(0) || !image->peekPixels(&pixels))
        return false;
    static constexpr std::array<SkColor, 4> expected {
        SkColorSetARGB(255, 255, 0, 0), SkColorSetARGB(128, 0, 255, 0),
        SkColorSetARGB(255, 0, 0, 255), SkColorSetARGB(64, 255, 255, 0),
    };
    for (int y = 0; y < 2; ++y) {
        for (int x = 0; x < 2; ++x) {
            if (pixels.getColor(x, y) != expected[y * 2 + x])
                return false;
        }
    }
    return true;
}

static bool matchesOpaqueJpeg()
{
    auto decoder = decode(solidJpeg, "image/jpeg"_s);
    if (!decoder || decoder->size() != IntSize { 4, 4 })
        return false;
    auto image = decoder->createFrameImageAtIndex(0);
    SkPixmap pixels;
    if (!image || !decoder->frameIsCompleteAtIndex(0) || !image->peekPixels(&pixels))
        return false;
    const auto color = pixels.getColor(2, 2);
    return SkColorGetA(color) == 255 && std::abs(static_cast<int>(SkColorGetR(color)) - 240) <= 4
        && std::abs(static_cast<int>(SkColorGetG(color)) - 16) <= 4
        && std::abs(static_cast<int>(SkColorGetB(color)) - 32) <= 4;
}

int main()
{
    WTF::initializeMainThread();
    if (!matchesTransparentImage(rgbaPng, "image/png"_s))
        return 1;
    if (!matchesTransparentImage(rgbaWebP, "image/webp"_s))
        return 2;
    if (!matchesOpaqueJpeg())
        return 3;
    auto truncated = decode(std::span { rgbaPng }.first(20), "image/png"_s);
    if (!truncated || truncated->createFrameImageAtIndex(0) || truncated->frameIsCompleteAtIndex(0))
        return 4;
    std::puts("XOS_WEBKIT_IMAGE_DECODERS_OK png webp jpeg truncated");
    return 0;
}
