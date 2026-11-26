// SPDX-License-Identifier: Apache-2.0
#include "config.h"

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <sys/mman.h>
#include <wtf/MemoryFootprint.h>
#include <wtf/OSAllocator.h>
#include <wtf/PageBlock.h>
#include <wtf/PageReservation.h>
#include <wtf/Threading.h>

static bool exact_available(uintptr_t address, size_t bytes)
{
    void* expected = reinterpret_cast<void*>(address);
    void* mapped = mmap(expected, bytes, PROT_NONE,
        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    return mapped != MAP_FAILED && !munmap(mapped, bytes) && mapped == expected;
}

static bool exercise_page_reservation(size_t page, size_t baseline)
{
    auto reservation = WTF::PageReservation::tryReserveWithGuardPages(3 * page);
    if (!reservation || WTF::memoryFootprint() != baseline)
        return false;
    const auto begin = reinterpret_cast<uintptr_t>(reservation.base());
    auto* middle = reinterpret_cast<volatile uint8_t*>(begin + page);
    auto* commit_address = reinterpret_cast<void*>(begin + page);

    reservation.commit(commit_address, page);
    if (reservation.committed() != page || WTF::memoryFootprint() != baseline + page)
        return false;
    middle[0] = 0x37;
    middle[page - 1] = 0x64;
    if (middle[0] != 0x37 || middle[page - 1] != 0x64)
        return false;

    reservation.decommit(commit_address, page);
    if (reservation.committed() || WTF::memoryFootprint() != baseline)
        return false;
    reservation.commit(commit_address, page);
    if (middle[0] || middle[page - 1])
        return false;
    reservation.decommit(commit_address, page);
    reservation.deallocate();
    return WTF::memoryFootprint() == baseline && exact_available(begin - page, 5 * page);
}

static bool exercise_guarded_alignment(size_t page, size_t baseline)
{
    const size_t alignment = 16 * page;
    const size_t bytes = 2 * page;
    void* aligned = WTF::OSAllocator::tryReserveUncommittedAligned(bytes, alignment,
        WTF::OSAllocator::UnknownUsage, nullptr, true, false, false, 1);
    const auto begin = reinterpret_cast<uintptr_t>(aligned);
    if (!aligned || begin % alignment || WTF::memoryFootprint() != baseline
        || !exact_available(begin - alignment, alignment - page))
        return false;

    WTF::OSAllocator::commit(aligned, bytes, true, false);
    auto* data = static_cast<volatile uint8_t*>(aligned);
    data[page - 1] = 0x14;
    data[page] = 0x61;
    WTF::OSAllocator::protect(aligned, bytes, true, false);
    if (data[page - 1] != 0x14 || data[page] != 0x61 || WTF::memoryFootprint() != baseline + bytes)
        return false;
    WTF::OSAllocator::protect(aligned, bytes, true, true);
    WTF::OSAllocator::zeroFill(aligned, bytes);
    if (data[page - 1] || data[page])
        return false;
    WTF::OSAllocator::decommit(aligned, bytes);
    WTF::OSAllocator::releaseDecommitted(aligned, bytes, 1);
    return WTF::memoryFootprint() == baseline && exact_available(begin - page, 4 * page);
}

static bool exercise_commit_failure(size_t page, size_t baseline)
{
    // One page more than the ordinary XOS VM transaction limit.
    const size_t bytes = 4097 * page;
    const size_t guarded_bytes = bytes + 2 * page;
    void* control = mmap(nullptr, guarded_bytes, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (control == MAP_FAILED)
        return false;
    const auto base = reinterpret_cast<uintptr_t>(control);
    auto* hint = reinterpret_cast<void*>(base + page);
    const bool native_limit = mprotect(hint, bytes, PROT_READ | PROT_WRITE) == -1 && errno == ENOMEM;
    if (munmap(control, guarded_bytes) || !native_limit)
        return false;

    void* allocation = WTF::OSAllocator::tryReserveAndCommit(bytes,
        WTF::OSAllocator::UnknownUsage, hint, true, false, false, 1);
    return !allocation && WTF::memoryFootprint() == baseline && exact_available(base, guarded_bytes);
}

int main()
{
    WTF::initialize();
    const auto page = WTF::pageSize();
    const auto baseline = WTF::memoryFootprint();
    if (!exercise_page_reservation(page, baseline))
        return 1;
    if (!exercise_guarded_alignment(page, baseline))
        return 2;

    void* committed = WTF::OSAllocator::tryReserveAndCommit(2 * page,
        WTF::OSAllocator::UnknownUsage, nullptr, true, false, false, 1);
    if (!committed || WTF::memoryFootprint() != baseline + 2 * page)
        return 3;
    auto* bytes = static_cast<volatile uint8_t*>(committed);
    bytes[0] = 0x23;
    bytes[2 * page - 1] = 0x76;
    if (bytes[0] != 0x23 || bytes[2 * page - 1] != 0x76)
        return 4;
    WTF::OSAllocator::decommit(committed, 2 * page);
    WTF::OSAllocator::releaseDecommitted(committed, 2 * page, 1);
    if (WTF::memoryFootprint() != baseline)
        return 5;

    constexpr size_t large_alignment = size_t { 4 } << 30;
    void* sparse = WTF::OSAllocator::tryReserveUncommittedAligned(large_alignment,
        large_alignment, WTF::OSAllocator::StructureAllocatorPages);
    const auto sparse_address = reinterpret_cast<uintptr_t>(sparse);
    if (!sparse || sparse_address % large_alignment || WTF::memoryFootprint() != baseline)
        return 6;
    WTF::OSAllocator::releaseDecommitted(sparse, large_alignment, 0);
    if (!exact_available(sparse_address, large_alignment))
        return 7;

    if (WTF::OSAllocator::tryReserveUncommitted(std::numeric_limits<size_t>::max())
        || WTF::OSAllocator::tryReserveUncommittedAligned(page, 3 * page)
        || WTF::OSAllocator::tryReserveAndCommit(page, WTF::OSAllocator::UnknownUsage, nullptr, true, true)
        || WTF::OSAllocator::tryReserveUncommitted(page, WTF::OSAllocator::UnknownUsage, nullptr, false, true, true)
        || WTF::memoryFootprint() != baseline)
        return 8;
    if (!exercise_commit_failure(page, baseline))
        return 9;

    std::puts("CLARKE_WTF_OS_ALLOCATOR_OK");
    return 0;
}
