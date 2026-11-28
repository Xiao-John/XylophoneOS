// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include "page.hpp"
#include "DOMRect.h"
#include "Document.h"
#include "Element.h"
#include "GraphicsContextSkia.h"
#include "LocalFrame.h"
#include "LocalFrameView.h"
#include "Page.h"
#include "Settings.h"
#include "TestPage.h"
#include <JavaScriptCore/InitializeThreading.h>
#include <fontconfig/fontconfig.h>
#include <skia/core/SkCanvas.h>
#include <skia/core/SkPixmap.h>
#include <skia/core/SkSurface.h>
#include <span>
#include <wtf/MainThread.h>
#include <wtf/text/AtomString.h>
#include <wtf/text/WTFString.h>

namespace clarke_page {
bool render(const char* bytes, std::size_t length, std::uint8_t* rgba, rectangle* rectangles, std::size_t count)
{
    if (!bytes || !length || length > 65536 || !rgba || (count && !rectangles)) return false;
    // A private Fontconfig configuration uses the explicitly installed font.
    // No host font cache or Linux font path participates in target rendering.
    auto* fonts = FcConfigCreate();
    const auto* config = reinterpret_cast<const FcChar8*>(
        "<?xml version=\"1.0\"?><!DOCTYPE fontconfig SYSTEM \"urn:fontconfig:fonts.dtd\">"
        "<fontconfig><alias><family>sans-serif</family><prefer><family>DejaVu Sans</family>"
        "</prefer></alias></fontconfig>");
    if (!fonts) return false;
    const bool configured = FcConfigParseAndLoadFromMemory(fonts, config, FcTrue) &&
        FcConfigAppFontAddFile(fonts, reinterpret_cast<const FcChar8*>("/usr/share/fonts/clarke/DejaVuSans.ttf")) &&
        FcConfigSetCurrent(fonts);
    FcConfigDestroy(fonts);
    if (!configured) return false;
    JSC::initialize();
    WTF::initializeMainThread();
    const auto html = String::fromUTF8(std::span<const char>(bytes, length));
    if (html.isNull()) return false;
    WebCore::TestPageOptions options;
    options.viewportSize = {320, 180};
    options.configureSettings = [](WebCore::Settings& settings) {
        settings.setStandardFontFamily("DejaVu Sans"_s);
        settings.setSansSerifFontFamily("DejaVu Sans"_s);
        settings.setSerifFontFamily("DejaVu Sans"_s);
        settings.setFixedFontFamily("DejaVu Sans"_s);
        settings.setDefaultFontSize(16);
    };
    auto page = WebCore::createTestPage(options);
    auto* frame = page->localMainFrame();
    if (!frame || !frame->view()) return false;
    WebCore::loadHTMLIntoTestPage(*frame, html);
    auto* document = frame->document();
    if (!document) return false;
    for (std::size_t index = 0; index < count; ++index) {
        auto& output = rectangles[index];
        auto element = document->getElementById(AtomString::fromUTF8(output.id));
        output.found = !!element;
        if (!element) continue;
        const auto bounds = element->getBoundingClientRect();
        output.x = bounds->x(); output.y = bounds->y();
        output.width = bounds->width(); output.height = bounds->height();
    }
    auto surface = SkSurfaces::Raster(SkImageInfo::MakeN32Premul(320, 180));
    if (!surface) return false;
    auto& canvas = *surface->getCanvas();
    canvas.clear(SK_ColorWHITE);
    WebCore::GraphicsContextSkia context(canvas, WebCore::RenderingMode::Unaccelerated, WebCore::RenderingPurpose::DOM);
    frame->view()->paintContents(context, {0, 0, 320, 180});
    SkPixmap pixels;
    if (!surface->peekPixels(&pixels)) return false;
    for (int y = 0; y < 180; ++y) for (int x = 0; x < 320; ++x) {
        const auto value = pixels.getColor(x, y);
        auto* target = rgba + (y * 320 + x) * 4;
        target[0] = SkColorGetR(value); target[1] = SkColorGetG(value);
        target[2] = SkColorGetB(value); target[3] = SkColorGetA(value);
    }
    return true;
}
}
