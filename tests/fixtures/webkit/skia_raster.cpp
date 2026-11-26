// SPDX-License-Identifier: Apache-2.0
#include "include/core/SkCanvas.h"
#include "include/core/SkColor.h"
#include "include/core/SkImageInfo.h"
#include "include/core/SkPaint.h"
#include "include/core/SkPixmap.h"
#include "include/core/SkRect.h"
#include "include/core/SkSurface.h"
#include <cstdio>

int main()
{
    auto surface = SkSurfaces::Raster(SkImageInfo::MakeN32Premul(12, 10));
    if (!surface)
        return 1;
    auto* canvas = surface->getCanvas();
    canvas->clear(SK_ColorWHITE);
    canvas->clipRect(SkRect::MakeXYWH(2, 2, 8, 6));
    SkPaint paint;
    paint.setColor(SK_ColorBLUE);
    canvas->drawRect(SkRect::MakeXYWH(0, 0, 6, 6), paint);
    paint.setColor(SK_ColorRED);
    canvas->drawRect(SkRect::MakeXYWH(4, 4, 8, 6), paint);
    SkPixmap pixels;
    if (!surface->peekPixels(&pixels) || pixels.getColor(0, 0) != SK_ColorWHITE ||
        pixels.getColor(2, 2) != SK_ColorBLUE || pixels.getColor(5, 5) != SK_ColorRED ||
        pixels.getColor(9, 7) != SK_ColorRED || pixels.getColor(10, 7) != SK_ColorWHITE)
        return 2;
    std::puts("WEBKIT_SKIA_RASTER_PASS 12x10 background=white clipped=blue overlap=red");
    return 0;
}
