// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include "IntSize.h"
#include "ShareableBitmap.h"
#include "SharedMemory.h"

#include <algorithm>
#include <array>
#include <cstdio>
#include <skia/core/SkCanvas.h>
#include <skia/core/SkImage.h>
#include <skia/core/SkImageInfo.h>
#include <skia/core/SkPaint.h>
#include <skia/core/SkPixmap.h>
#include <skia/core/SkSurface.h>
#include <xos/ipc_v1.hpp>
#include <xos/vm_abi.hpp>

namespace {

using WebCore::SharedMemory;
using WebCore::SharedMemoryHandle;
using Protection = SharedMemory::Protection;

bool readonly_remains_protected(std::span<const uint8_t> bytes)
{
    xos::vm_request request {
        xos::vm_abi_version, sizeof(xos::vm_request), static_cast<uint32_t>(xos::vm_operation::protect), 0,
        reinterpret_cast<uintptr_t>(bytes.data()), xos::vm_page_size, 0,
        static_cast<uint32_t>(xos::vm_protection::read_write), 0, 0, 0
    };
    return xos::sdk::syscall(xos::sys_vm, reinterpret_cast<uintptr_t>(&request))
        == static_cast<xos::i64>(xos::ipc_v1_error::busy);
}

bool check_memory()
{
    constexpr auto max = xos::ipc_v1_max_grant_pages * xos::vm_page_size;
    if (SharedMemory::allocate(0) || SharedMemory::allocate(max + 1))
        return false;

    auto memory = SharedMemory::allocate(4097);
    if (!memory || memory->span().size() != 4097 || !std::ranges::all_of(memory->span(), [](auto byte) { return !byte; }))
        return false;
    auto writable = memory->createHandle(Protection::ReadWrite);
    auto readonly = memory->createHandle(Protection::ReadOnly);
    if (!writable || !readonly)
        return false;

    SharedMemoryHandle readonly_copy(*readonly);
    SharedMemoryHandle cow_copy(*readonly);
    auto writer = SharedMemory::map(WTF::move(*writable), Protection::ReadWrite);
    auto reader = SharedMemory::map(WTF::move(*readonly), Protection::ReadOnly);
    if (!writer || !reader || writer->span().data() == memory->span().data()
        || reader->span().data() == writer->span().data() || !reader->mutableSpan().empty()
        || reader->createHandle(Protection::ReadWrite) || !readonly_remains_protected(reader->span())
        || SharedMemory::map(WTF::move(readonly_copy), Protection::ReadWrite)
        || SharedMemory::map(WTF::move(cow_copy), Protection::ReadOnly, SharedMemory::CopyOnWrite::Yes))
        return false;
    memory->mutableSpan().front() = 71;
    writer->mutableSpan().back() = 109;
    if (reader->span().front() != 71 || reader->span().back() != 109)
        return false;
    memory = nullptr;
    writer = nullptr;
    if (reader->span().front() != 71 || reader->span().back() != 109)
        return false;

    std::array<uint8_t, 4> source { 1, 2, 3, 4 };
    auto snapshot = SharedMemoryHandle::createCopy(source, Protection::ReadOnly);
    if (!snapshot)
        return false;
    source.fill(0);
    auto copy = SharedMemory::map(WTF::move(*snapshot), Protection::ReadOnly);
    return copy && copy->span().size() == 4 && copy->span()[2] == 3;
}

bool check_bitmap()
{
    const WebCore::IntSize size(16, 8);
    const WebCore::ShareableBitmapConfiguration configuration(size);
    auto writer = WebCore::ShareableBitmap::create(configuration);
    if (!writer)
        return false;
    auto reader = WebCore::ShareableBitmap::createReadOnly(writer->createReadOnlyHandle());
    if (!reader || !reader.value()->mutableSpan().empty())
        return false;

    auto canvas = SkSurfaces::WrapPixels(SkImageInfo::MakeN32Premul(16, 8), writer->mutableSpan().data(),
                                         writer->bytesPerRow());
    auto image = reader.value()->createPlatformImage(WebCore::BackingStoreCopy::DontCopyBackingStore);
    if (!canvas || !image)
        return false;
    canvas->getCanvas()->clear(SK_ColorWHITE);
    SkPaint paint;
    paint.setColor(SK_ColorRED);
    canvas->getCanvas()->drawRect(SkRect::MakeLTRB(0, 0, 8, 8), paint);
    paint.setColor(SK_ColorBLUE);
    canvas->getCanvas()->drawRect(SkRect::MakeLTRB(8, 0, 16, 4), paint);
    canvas.reset();
    writer = nullptr;
    reader.reset();

    SkPixmap pixels;
    return image->peekPixels(&pixels) && pixels.getColor(2, 2) == SK_ColorRED
        && pixels.getColor(12, 2) == SK_ColorBLUE && pixels.getColor(12, 6) == SK_ColorWHITE;
}

}

int main()
{
    for (int attempt = 0; attempt < 20; ++attempt) {
        if (!check_memory())
            return 1;
        if (!check_bitmap())
            return 2;
    }
    std::puts("XOS_WEBCORE_CPU_BITMAP_GRANT_PASS readonly aliases and 16x8 red blue white");
    return 0;
}
