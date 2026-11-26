// SPDX-License-Identifier: Apache-2.0
#include "include/core/SkCanvas.h"
#include "include/core/SkFont.h"
#include "include/core/SkFontMgr.h"
#include "include/core/SkFontScanner.h"
#include "include/core/SkImageInfo.h"
#include "include/core/SkPaint.h"
#include "include/core/SkPixmap.h"
#include "include/core/SkString.h"
#include "include/core/SkSurface.h"
#include "include/core/SkTypeface.h"
#include "include/ports/SkFontMgr_fontconfig.h"
#include "include/ports/SkFontScanner_FreeType.h"

#include <cstdio>
#include <memory>
#include <utility>

int main(int argc, char** argv)
{
    if (argc != 2)
        return 2;
    static const FcChar8 rules[] = "<?xml version=\"1.0\"?>"
        "<fontconfig><alias binding=\"strong\"><family>sans-serif</family>"
        "<prefer><family>DejaVu Sans</family></prefer></alias></fontconfig>";
    std::unique_ptr<FcConfig, decltype(&FcConfigDestroy)> config(FcConfigCreate(), FcConfigDestroy);
    if (!config || !FcConfigParseAndLoadFromMemory(config.get(), rules, FcTrue)
        || !FcConfigAppFontAddDir(config.get(), reinterpret_cast<const FcChar8*>(argv[1])))
        return 3;

    auto scanner = SkFontScanner_Make_FreeType();
    if (!scanner)
        return 4;
    auto manager = SkFontMgr_New_FontConfig(config.release(), std::move(scanner));
    if (!manager)
        return 4;
    if (manager->countFamilies() == 0) {
        std::puts("XOS_SKIA_FONTCONFIG_EMPTY");
        return 5;
    }

    auto generic = manager->matchFamilyStyle("sans-serif", SkFontStyle());
    const char* language[] = { "el" };
    auto fallback = manager->matchFamilyStyleCharacter("sans-serif", SkFontStyle(), language, 1, 0x03bb);
    if (!generic || !fallback || manager->countFamilies() != 1
        || manager->matchFamilyStyleCharacter("sans-serif", SkFontStyle(), language, 1, 0x10ffff))
        return 6;
    SkString family;
    generic->getFamilyName(&family);
    if (!family.equals("DejaVu Sans"))
        return 7;
    fallback->getFamilyName(&family);
    const SkGlyphID glyph = fallback->unicharToGlyph(0x03bb);
    if (!family.equals("DejaVu Sans") || !glyph || glyph != generic->unicharToGlyph(0x03bb))
        return 8;

    auto surface = SkSurfaces::Raster(SkImageInfo::MakeN32Premul(40, 35));
    if (!surface)
        return 9;
    auto* canvas = surface->getCanvas();
    canvas->clear(SK_ColorWHITE);
    SkPaint paint;
    paint.setColor(SK_ColorBLACK);
    constexpr char lambda[] = "\xce\xbb";
    canvas->drawSimpleText(lambda, sizeof(lambda) - 1, SkTextEncoding::kUTF8, 4, 25, SkFont(fallback, 24), paint);
    SkPixmap pixels;
    if (!surface->peekPixels(&pixels) || pixels.getColor(0, 0) != SK_ColorWHITE)
        return 10;
    unsigned ink = 0;
    for (int y = 0; y < pixels.height(); ++y)
        for (int x = 0; x < pixels.width(); ++x)
            ink += pixels.getColor(x, y) != SK_ColorWHITE;
    if (!ink || ink >= static_cast<unsigned>(pixels.width() * pixels.height()))
        return 11;
    std::printf("XOS_SKIA_FONTCONFIG_PASS family=DejaVu_Sans glyph=%u ink=%u\n", static_cast<unsigned>(glyph), ink);
    return 0;
}
