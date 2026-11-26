// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include "OSAllocator.h"

#include <QtCore/qlogging.h>
#include <xos/vm.hpp>

#include <limits>

namespace WTF {
namespace {

using xos::vm_operation;
using xos::vm_page_size;
using xos::vm_protection;
using xos::vm_error_denied;
using xos::vm_error_invalid;

[[noreturn]] void vm_failure(const char *operation, xos::i64 result)
{
    qFatal("QV4 XOS VM %s failed (%lld)", operation, static_cast<long long>(result));
}

size_t page_length(size_t bytes)
{
    if (!bytes || bytes > std::numeric_limits<size_t>::max() - (vm_page_size - 1))
        vm_failure("invalid length", vm_error_invalid);
    return (bytes + vm_page_size - 1) & ~(vm_page_size - 1);
}

void change_range(vm_operation operation, void *base, size_t length, const char *description,
                  vm_protection protection = vm_protection::none)
{
    const auto result = xos::sdk::vm_change(operation, reinterpret_cast<xos::u64>(base),
                                           page_length(length), protection);
    if (result != 0)
        vm_failure(description, result);
}

}  // namespace

void *OSAllocator::reserveUncommitted(size_t bytes, Usage, bool, bool executable)
{
    if (executable)
        vm_failure("executable reservation unavailable", vm_error_denied);
    const auto result = xos::sdk::vm_reserve(0, page_length(bytes));
    if (result <= 0)
        vm_failure("reserve", result);
    return reinterpret_cast<void *>(static_cast<xos::u64>(result));
}

void *OSAllocator::reserveAndCommit(size_t bytes, Usage usage, bool writable, bool executable,
                                  bool includes_guard_pages)
{
    const size_t length = page_length(bytes);
    const size_t guard = includes_guard_pages ? vm_page_size : 0;
    if (length <= 2 * guard)
        vm_failure("invalid guard extent", vm_error_invalid);

    auto *base = static_cast<char *>(reserveUncommitted(length, usage, writable, executable));
    const auto protection = writable ? vm_protection::read_write : vm_protection::read;
    const auto result = xos::sdk::vm_change(vm_operation::commit,
            reinterpret_cast<xos::u64>(base + guard), length - 2 * guard, protection);
    if (result != 0) {
        releaseDecommitted(base, length);
        vm_failure("initial commit", result);
    }

    return base;
}

void OSAllocator::commit(void *base, size_t length, bool writable, bool executable)
{
    if (executable)
        vm_failure("executable commit unavailable", vm_error_denied);
    change_range(vm_operation::commit, base, length, "commit",
                 writable ? vm_protection::read_write : vm_protection::read);
}

void OSAllocator::decommit(void *base, size_t length)
{
    change_range(vm_operation::decommit, base, length, "decommit");
}

void OSAllocator::releaseDecommitted(void *base, size_t length)
{
    change_range(vm_operation::unmap, base, length, "unmap");
}

bool OSAllocator::canAllocateExecutableMemory()
{
    return false;
}

}  // namespace WTF
