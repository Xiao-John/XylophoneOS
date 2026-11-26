// SPDX-License-Identifier: Apache-2.0
#include "config.h"

#include <array>
#include <cerrno>
#include <cstdio>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <wtf/FileHandle.h>
#include <wtf/FileSystem.h>
#include <wtf/Locker.h>
#include <wtf/MappedFileData.h>
#include <wtf/MemoryFootprint.h>
#include <wtf/OSRandomSource.h>
#include <wtf/PageBlock.h>
#include <wtf/ProcessID.h>
#include <wtf/Threading.h>
#include <wtf/ThreadingPrimitives.h>
#include <wtf/WallTime.h>
#include <wtf/WTFConfig.h>

int main(int argc, char** argv)
{
    WTF::initialize();
    if (WTF::getCurrentProcessID() != getpid() || getpid() <= 0
            || WTF::pageSize() != static_cast<size_t>(getpagesize()))
        return 5;
    auto& primary = WTF::Thread::currentSingleton();
    char primary_stack = 0;
    if (!primary.stack().contains(&primary_stack))
        return 1;

    WTF::Mutex lock;
    WTF::ThreadCondition changed;
    WTF::Thread* observed_worker = nullptr;
    bool worker_stack_ok = false;
    bool finish = false;
    auto worker = WTF::Thread::create("ClarkE-WTF"_s, [&] {
        auto& self = WTF::Thread::currentSingleton();
        char worker_stack = 0;
        WTF::Locker locker { lock };
        worker_stack_ok = self.stack().contains(&worker_stack);
        observed_worker = &self;
        changed.broadcast();
        while (!finish)
            changed.wait(lock);
    });

    bool worker_ok;
    bool suspend_rejected = false;
    {
        WTF::Locker locker { lock };
        const auto deadline = WTF::WallTime::now() + WTF::Seconds { 3 };
        while (!observed_worker && changed.timedWait(lock, deadline)) { }
        worker_ok = observed_worker == worker.ptr() && observed_worker != &primary && worker_stack_ok;
        if (worker_ok) {
            WTF::ThreadSuspendLocker suspend_lock;
            auto suspend = worker->suspend(suspend_lock);
            suspend_rejected = !suspend && suspend.error() == ENOTSUP;
        }
        finish = true;
        changed.broadcast();
    }

    if (worker->waitForCompletion())
        return 2;
    if (!worker_ok || !suspend_rejected)
        return 3;

    // Exercise two full 256-byte requests and a final one-byte request.
    std::array<uint8_t, 513> first { }, second { };
    WTF::cryptographicallyRandomValuesFromOS(first);
    WTF::cryptographicallyRandomValuesFromOS(second);
    if (first == second)
        return 4;

    const auto footprint = WTF::memoryFootprint();
    const auto mapping_size = 3 * WTF::pageSize();
    void* mapping = mmap(nullptr, mapping_size, PROT_NONE,
                         MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mapping == MAP_FAILED || WTF::memoryFootprint() != footprint
        || mprotect(mapping, mapping_size, PROT_READ | PROT_WRITE))
        return 6;
    const auto mapped_footprint = WTF::memoryFootprint();
    WTF::permanentlyFreezePages(mapping, mapping_size, WTF::FreezePagePermission::ReadOnly);
    if (munmap(mapping, mapping_size) || WTF::memoryFootprint() != footprint
            || mapped_footprint != footprint + mapping_size)
        return 7;

    const int fd = argc > 0 ? open(argv[0], O_RDONLY) : -1;
    if (fd < 0)
        return 8;
    auto file = WTF::FileSystemImpl::FileHandle::adopt(fd);
    errno = 0;
    if (file.map(WTF::FileSystemImpl::MappedFileMode::Private,
                 WTF::FileSystemImpl::FileOpenMode::Read) || errno != ENOTSUP)
        return 9;

    std::puts("CLARKE_WTF_PTHREAD_OK");
    return 0;
}
