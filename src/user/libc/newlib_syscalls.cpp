#include <xos/sdk.hpp>
#include <errno.h>
#include <sys/stat.h>
#include <unistd.h>
#include <stdint.h>

namespace {
unsigned char heap[65536];
unsigned long used;
}

extern "C" void* _sbrk(int increment) {
    if (increment < 0) { errno = ENOMEM; return reinterpret_cast<void*>(-1); }
    const unsigned long need = static_cast<unsigned long>(increment);
    if (used + need > sizeof(heap)) { errno = ENOMEM; return reinterpret_cast<void*>(-1); }
    void* result = heap + used;
    used += need;
    return result;
}

extern "C" int _write(int fd, const void* data, int length) {
    const auto* bytes = static_cast<const char*>(data);
    int done = 0;
    while (done < length) {
        int chunk = length - done;
        if (chunk > 256) { chunk = 256; }
        const xos::i64 sent = xos::sdk::write(static_cast<xos::u32>(fd), bytes + done,
                                               static_cast<xos::u64>(chunk));
        if (sent <= 0) { errno = EIO; return -1; }
        done += static_cast<int>(sent);
    }
    return done;
}

extern "C" int _read(int fd, void* data, int length) {
    if (length <= 0) { return 0; }
    const xos::i64 got = xos::sdk::read(static_cast<xos::u32>(fd), data, 1);
    if (got < 0) { errno = EAGAIN; return -1; }
    return static_cast<int>(got);
}

extern "C" int _close(int fd) { return xos::sdk::close(static_cast<xos::u32>(fd)) == 0 ? 0 : -1; }
extern "C" int _fstat(int, struct stat* status) {
    status->st_mode = S_IFCHR;
    return 0;
}
extern "C" int _isatty(int fd) { return fd >= 0 && fd <= 2 ? 1 : 0; }
extern "C" int _lseek(int, int, int) { errno = ESPIPE; return -1; }
extern "C" void _exit(int code) { xos::sdk::exit(code); }
extern "C" int open(const char*, int, ...) { errno = ENOSYS; return -1; }
extern "C" int stat(const char*, struct stat*) { errno = ENOSYS; return -1; }
extern "C" int unlink(const char*) { errno = ENOSYS; return -1; }
extern "C" int _getpid() { return static_cast<int>(xos::sdk::pid()); }
extern "C" int _kill(int, int) { errno = EINVAL; return -1; }
extern "C" int _times(void*) { errno = ENOSYS; return -1; }

extern "C" void* sbrk(int increment) { return _sbrk(increment); }
extern "C" int write(int fd, const void* data, size_t length) { return _write(fd, data, static_cast<int>(length)); }
extern "C" int read(int fd, void* data, size_t length) { return _read(fd, data, static_cast<int>(length)); }
extern "C" int close(int fd) { return _close(fd); }
extern "C" int fstat(int fd, struct stat* status) { return _fstat(fd, status); }
extern "C" int isatty(int fd) { return _isatty(fd); }
extern "C" off_t lseek(int fd, off_t offset, int whence) { return _lseek(fd, static_cast<int>(offset), whence); }
extern "C" int kill(int pid, int sig) { return _kill(pid, sig); }
extern "C" int getpid() { return _getpid(); }
