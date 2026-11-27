// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include "DOMRect.h"
#include "Document.h"
#include "DocumentView.h"
#include "Element.h"
#include "GraphicsContextSkia.h"
#include "LocalFrame.h"
#include "LocalFrameInlines.h"
#include "LocalFrameView.h"
#include "Page.h"
#include "TestPage.h"

#include <JavaScriptCore/InitializeThreading.h>
#include <cstdio>
#include <skia/core/SkCanvas.h>
#include <skia/core/SkPixmap.h>
#include <skia/core/SkSurface.h>
#include <span>
#include <wtf/MainThread.h>
#include <wtf/text/AtomString.h>
#include <wtf/text/WTFString.h>

int main(int argc, char** argv)
{
    if (argc != 2)
        return 2;
    auto* input = std::fopen(argv[1], "rb");
    if (!input)
        return 3;
    char bytes[8192];
    const auto count = std::fread(bytes, 1, sizeof(bytes), input);
    const bool complete = std::feof(input) && !std::ferror(input);
    if (std::fclose(input) || !count || !complete)
        return 4;
    JSC::initialize();
    WTF::initializeMainThread();
    const auto html = String::fromUTF8(std::span<const char>(bytes, count));
    if (html.isNull())
        return 5;

    WebCore::TestPageOptions options;
    options.viewportSize = { 120, 90 };
    auto page = WebCore::createTestPage(options);
    auto* frame = page->localMainFrame();
    if (!frame || !frame->view())
        return 6;
    WebCore::loadHTMLIntoTestPage(*frame, html);
    auto* document = frame->document();
    if (!document)
        return 7;
    auto base = document->getElementById(AtomString::fromUTF8("base"));
    auto overlay = document->getElementById(AtomString::fromUTF8("overlay"));
    if (!base || !overlay)
        return 8;
    const auto baseBounds = base->getBoundingClientRect();
    const auto overlayBounds = overlay->getBoundingClientRect();
    if (baseBounds->x() != 10 || baseBounds->y() != 20 || baseBounds->width() != 60 || baseBounds->height() != 40
        || overlayBounds->x() != 40 || overlayBounds->y() != 30 || overlayBounds->width() != 50 || overlayBounds->height() != 40)
        return 9;

    const WebCore::IntRect bounds { 0, 0, 120, 90 };
    auto surface = SkSurfaces::Raster(SkImageInfo::MakeN32Premul(bounds.width(), bounds.height()));
    if (!surface)
        return 10;
    auto& canvas = *surface->getCanvas();
    canvas.clear(SK_ColorMAGENTA);
    WebCore::GraphicsContextSkia context(canvas, WebCore::RenderingMode::Unaccelerated, WebCore::RenderingPurpose::DOM);
    frame->view()->paintContents(context, bounds);
    SkPixmap pixels;
    if (!surface->peekPixels(&pixels)
        || pixels.getColor(20, 25) != SK_ColorRED || pixels.getColor(50, 40) != SK_ColorBLUE
        || pixels.getColor(80, 40) != SK_ColorBLUE || pixels.getColor(100, 75) != SK_ColorWHITE)
        return 11;

    std::puts("XOS_WEBCORE_LOCAL_PAGE_PASS 120x90 DOM CSS red blue white");
    return 0;
}
