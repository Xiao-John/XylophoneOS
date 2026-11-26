// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include "GraphicsTypes.h"
#include "SkiaRecordingResult.h"
#include "SkiaUtilities.h"

#include <cstdio>
#include <skia/core/SkCanvas.h>
#include <skia/core/SkImageInfo.h>
#include <skia/core/SkPaint.h>
#include <skia/core/SkPictureRecorder.h>
#include <skia/core/SkPixmap.h>
#include <skia/core/SkSurface.h>
#include <wtf/MainThread.h>

int main()
{
    WTF::initializeMainThread();
    WebCore::IntRect bounds { 0, 0, 16, 8 };
    SkPictureRecorder recorder;
    auto* recording = recorder.beginRecording(16, 8);
    recording->clear(SK_ColorWHITE);
    SkPaint paint;
    paint.setColor(SK_ColorRED);
    recording->drawRect(SkRect::MakeLTRB(0, 0, 8, 8), paint);
    paint.setColor(SK_ColorBLUE);
    paint.setBlendMode(WebCore::SkiaUtilities::toSkiaBlendMode(WebCore::BlendMode::Multiply));
    recording->drawRect(SkRect::MakeLTRB(4, 0, 12, 8), paint);

    auto result = WebCore::SkiaRecordingResult::create(recorder.finishRecordingAsPicture(), { }, bounds,
        WebCore::RenderingMode::Unaccelerated, true, 1.0f);
    if (result->hasFences() || result->recordRect() != bounds || !result->contentsOpaque()
        || result->renderingMode() != WebCore::RenderingMode::Unaccelerated || result->contentsScale() != 1.0f)
        return 1;

    auto surface = SkSurfaces::Raster(SkImageInfo::MakeN32Premul(16, 8));
    if (!surface)
        return 2;
    surface->getCanvas()->drawPicture(result->picture());
    SkPixmap pixels;
    if (!surface->peekPixels(&pixels) || pixels.getColor(2, 2) != SK_ColorRED || pixels.getColor(5, 2) != SK_ColorBLACK
        || pixels.getColor(9, 2) != SK_ColorBLUE || pixels.getColor(15, 2) != SK_ColorWHITE)
        return 3;
    std::puts("XOS_WEBCORE_SOFTWARE_RECORDING_PASS 16x8 red black blue white");
    return 0;
}
