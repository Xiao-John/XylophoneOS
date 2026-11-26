// SPDX-License-Identifier: Apache-2.0
#include "config.h"

#include <wtf/Assertions.h>
#include <wtf/MemoryFootprint.h>
#include <wtf/PageBlock.h>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace WTF {

size_t memoryFootprint()
{
    xos::thread_stats stats { };
    const auto status = xos::sdk::syscall(xos::sys_thread_stats,
                                          reinterpret_cast<xos::u64>(&stats));
    RELEASE_ASSERT(!status && stats.header.version == xos::thread_abi_version
        && stats.header.size == sizeof(stats) && !stats.header.reserved);

    // Use the logical user pages charged to the calling process.
    return static_cast<size_t>(stats.process_user_pages) * pageSize();
}

} // namespace WTF
