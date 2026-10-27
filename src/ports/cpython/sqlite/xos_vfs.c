/* SPDX-License-Identifier: Apache-2.0 */
/* Restricted XOS SQLite VFS: one process, rollback journal, exclusive locks. */
#include <sqlite3.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define XOS_SQLITE_MAX_PATH 256

/* Present in the XOS target ABI once the SQLite-specific libc hook lands. */
extern int ftruncate(int, off_t);

typedef struct XosFile XosFile;
struct XosFile {
    sqlite3_file base;
    int fd;
    int lock_level;
    int delete_on_close;
    char path[XOS_SQLITE_MAX_PATH];
    XosFile *next;
};

static XosFile *open_files;
static uint64_t random_state = UINT64_C(0x58534f53514c4954);
static unsigned long temp_counter;
static sqlite3_vfs xos_vfs;

static int xClose(sqlite3_file *raw);
static int xRead(sqlite3_file *raw, void *buffer, int amount, sqlite3_int64 offset);
static int xWrite(sqlite3_file *raw, const void *buffer, int amount, sqlite3_int64 offset);
static int xTruncate(sqlite3_file *raw, sqlite3_int64 size);
static int xSync(sqlite3_file *raw, int flags);
static int xFileSize(sqlite3_file *raw, sqlite3_int64 *size);
static int xLock(sqlite3_file *raw, int level);
static int xUnlock(sqlite3_file *raw, int level);
static int xCheckReservedLock(sqlite3_file *raw, int *result);
static int xFileControl(sqlite3_file *raw, int op, void *arg);
static int xSectorSize(sqlite3_file *raw);
static int xDeviceCharacteristics(sqlite3_file *raw);

static const sqlite3_io_methods io_methods = {
    1, xClose, xRead, xWrite, xTruncate, xSync, xFileSize, xLock, xUnlock,
    xCheckReservedLock, xFileControl, xSectorSize, xDeviceCharacteristics,
    0, 0, 0, 0, 0, 0
};

static int map_errno(void) {
    if (errno == EBUSY) return SQLITE_BUSY;
    if (errno == ENOSPC) return SQLITE_FULL;
    if (errno == EACCES || errno == EPERM || errno == EROFS) return SQLITE_READONLY;
    if (errno == ENOENT) return SQLITE_CANTOPEN;
    return SQLITE_IOERR;
}

static int seek_to(int fd, sqlite3_int64 offset) {
    if (offset < 0 || (sqlite3_int64)lseek(fd, (off_t)offset, SEEK_SET) != offset) return -1;
    return 0;
}

static int xClose(sqlite3_file *raw) {
    XosFile *file = (XosFile *)raw;
    XosFile **link = &open_files;
    while (*link && *link != file) link = &(*link)->next;
    if (*link) *link = file->next;
    int result = close(file->fd);
    if (file->delete_on_close && file->path[0]) (void)unlink(file->path);
    file->fd = -1;
    file->base.pMethods = 0;
    return result == 0 ? SQLITE_OK : map_errno();
}

static int xRead(sqlite3_file *raw, void *buffer, int amount, sqlite3_int64 offset) {
    XosFile *file = (XosFile *)raw;
    struct stat status;
    if (amount < 0 || offset < 0) return SQLITE_IOERR_READ;
    if (fstat(file->fd, &status) != 0) return SQLITE_IOERR_FSTAT;
    if (offset >= (sqlite3_int64)status.st_size) {
        memset(buffer, 0, (size_t)amount);
        return SQLITE_IOERR_SHORT_READ;
    }
    sqlite3_int64 available = (sqlite3_int64)status.st_size - offset;
    int wanted = available < amount ? (int)available : amount;
    if (seek_to(file->fd, offset) != 0) return SQLITE_IOERR_SEEK;
    int done = 0;
    while (done < wanted) {
        ssize_t got = read(file->fd, (char *)buffer + done, (size_t)(wanted - done));
        if (got < 0 && errno == EINTR) continue;
        if (got < 0) return SQLITE_IOERR_READ;
        if (got == 0) {
            memset((char *)buffer + done, 0, (size_t)(amount - done));
            return SQLITE_IOERR_SHORT_READ;
        }
        done += (int)got;
    }
    if (done < amount) {
        memset((char *)buffer + done, 0, (size_t)(amount - done));
        return SQLITE_IOERR_SHORT_READ;
    }
    return SQLITE_OK;
}

static int xWrite(sqlite3_file *raw, const void *buffer, int amount, sqlite3_int64 offset) {
    XosFile *file = (XosFile *)raw;
    if (seek_to(file->fd, offset) != 0) return SQLITE_IOERR_SEEK;
    int done = 0;
    while (done < amount) {
        ssize_t put = write(file->fd, (const char *)buffer + done, (size_t)(amount - done));
        if (put < 0 && errno == EINTR) continue;
        if (put <= 0) return map_errno();
        done += (int)put;
    }
    return SQLITE_OK;
}

static int xTruncate(sqlite3_file *raw, sqlite3_int64 size) {
    XosFile *file = (XosFile *)raw;
    if (size < 0 || ftruncate(file->fd, (off_t)size) != 0) return SQLITE_IOERR_TRUNCATE;
    return SQLITE_OK;
}

static int xSync(sqlite3_file *raw, int flags) {
    (void)flags;
    XosFile *file = (XosFile *)raw;
    if (fsync(file->fd) != 0) return SQLITE_IOERR_FSYNC;
    return SQLITE_OK;
}

static int xFileSize(sqlite3_file *raw, sqlite3_int64 *size) {
    struct stat status;
    if (fstat(((XosFile *)raw)->fd, &status) != 0) return SQLITE_IOERR_FSTAT;
    *size = (sqlite3_int64)status.st_size;
    return SQLITE_OK;
}

static int xLock(sqlite3_file *raw, int level) {
    XosFile *file = (XosFile *)raw;
    if (level <= file->lock_level) return SQLITE_OK;
    for (XosFile *other = open_files; other; other = other->next) {
        if (other == file || strcmp(other->path, file->path) != 0) continue;
        int conflict = 0;
        if (level == SQLITE_LOCK_SHARED)
            conflict = other->lock_level >= SQLITE_LOCK_PENDING;
        else if (level == SQLITE_LOCK_RESERVED || level == SQLITE_LOCK_PENDING)
            conflict = other->lock_level >= SQLITE_LOCK_RESERVED;
        else if (level == SQLITE_LOCK_EXCLUSIVE)
            conflict = other->lock_level != SQLITE_LOCK_NONE;
        if (conflict) return SQLITE_BUSY;
    }
    file->lock_level = level;
    return SQLITE_OK;
}

static int xUnlock(sqlite3_file *raw, int level) {
    XosFile *file = (XosFile *)raw;
    if (level < SQLITE_LOCK_NONE) return SQLITE_IOERR_UNLOCK;
    file->lock_level = level;
    return SQLITE_OK;
}

static int xCheckReservedLock(sqlite3_file *raw, int *result) {
    XosFile *file = (XosFile *)raw;
    *result = file->lock_level >= SQLITE_LOCK_RESERVED;
    if (*result) return SQLITE_OK;
    for (XosFile *other = open_files; other; other = other->next) {
        if (other != file && other->lock_level >= SQLITE_LOCK_RESERVED &&
            strcmp(other->path, file->path) == 0) { *result = 1; break; }
    }
    return SQLITE_OK;
}

static int xFileControl(sqlite3_file *raw, int op, void *arg) {
    (void)raw; (void)op; (void)arg;
    return SQLITE_NOTFOUND;
}

static int xSectorSize(sqlite3_file *raw) { (void)raw; return 512; }
static int xDeviceCharacteristics(sqlite3_file *raw) { (void)raw; return 0; }

static int xOpen(sqlite3_vfs *vfs, const char *name, sqlite3_file *raw,
                 int flags, int *out_flags) {
    (void)vfs;
    XosFile *file = (XosFile *)raw;
    memset(file, 0, sizeof(*file));
    file->fd = -1;
    file->delete_on_close = (flags & SQLITE_OPEN_DELETEONCLOSE) != 0;
    const char *path = name;
    char temporary[XOS_SQLITE_MAX_PATH];
    if (!path) {
        ++temp_counter;
        (void)snprintf(temporary, sizeof(temporary), "/tmp/sqlite-%lu-%lu.tmp",
                       (unsigned long)getpid(), temp_counter);
        path = temporary;
        file->delete_on_close = 1;
    }
    size_t length = strlen(path);
    if (length == 0 || length >= sizeof(file->path)) return SQLITE_CANTOPEN;
    memcpy(file->path, path, length + 1);
    int oflags = (flags & SQLITE_OPEN_READWRITE) ? O_RDWR : O_RDONLY;
    if (flags & SQLITE_OPEN_CREATE) oflags |= O_CREAT;
    if (flags & SQLITE_OPEN_EXCLUSIVE) oflags |= O_EXCL;
    file->fd = open(path, oflags, 0666);
    if (file->fd < 0) return map_errno();
    file->base.pMethods = &io_methods;
    file->next = open_files;
    open_files = file;
    if (out_flags) *out_flags = (flags & SQLITE_OPEN_READWRITE) ? SQLITE_OPEN_READWRITE : SQLITE_OPEN_READONLY;
    return SQLITE_OK;
}

static int xDelete(sqlite3_vfs *vfs, const char *path, int sync_dir) {
    (void)vfs; (void)sync_dir;
    return unlink(path) == 0 ? SQLITE_OK : map_errno();
}

static int xAccess(sqlite3_vfs *vfs, const char *path, int flags, int *result) {
    (void)vfs;
    int mode = flags == SQLITE_ACCESS_READWRITE ? R_OK | W_OK : R_OK;
    *result = access(path, mode) == 0;
    if (!*result && errno != ENOENT && errno != EACCES) return map_errno();
    return SQLITE_OK;
}

static int xFullPathname(sqlite3_vfs *vfs, const char *path, int size, char *output) {
    (void)vfs;
    size_t length = strlen(path);
    if (length + 1 > (size_t)size) return SQLITE_CANTOPEN;
    memcpy(output, path, length + 1);
    return SQLITE_OK;
}

static void *xDlOpen(sqlite3_vfs *vfs, const char *path) { (void)vfs; (void)path; return 0; }
static void xDlError(sqlite3_vfs *vfs, int size, char *message) {
    (void)vfs; if (size > 0) message[0] = 0;
}
static void (*xDlSym(sqlite3_vfs *vfs, void *handle, const char *symbol))(void) {
    (void)vfs; (void)handle; (void)symbol; return 0;
}
static void xDlClose(sqlite3_vfs *vfs, void *handle) { (void)vfs; (void)handle; }

static int xRandomness(sqlite3_vfs *vfs, int amount, char *output) {
    (void)vfs;
    time_t now = time(0);
    random_state ^= (uint64_t)now + (uint64_t)(uintptr_t)output + ++temp_counter;
    for (int i = 0; i < amount; ++i) {
        random_state ^= random_state << 13;
        random_state ^= random_state >> 7;
        random_state ^= random_state << 17;
        output[i] = (char)random_state;
    }
    return amount;
}

static int xSleep(sqlite3_vfs *vfs, int microseconds) {
    (void)vfs;
    struct timespec delay = { microseconds / 1000000, (microseconds % 1000000) * 1000 };
    while (nanosleep(&delay, &delay) != 0 && errno == EINTR) {}
    return microseconds;
}

static int xCurrentTime(sqlite3_vfs *vfs, double *julian) {
    (void)vfs;
    time_t seconds = time(0);
    *julian = 2440587.5 + (double)seconds / 86400.0;
    return SQLITE_OK;
}

static int xGetLastError(sqlite3_vfs *vfs, int size, char *message) {
    (void)vfs;
    if (size > 0) (void)snprintf(message, (size_t)size, "XOS errno=%d", errno);
    return errno;
}

int sqlite3_os_init(void) {
    memset(&xos_vfs, 0, sizeof(xos_vfs));
    xos_vfs.iVersion = 1;
    xos_vfs.szOsFile = sizeof(XosFile);
    xos_vfs.mxPathname = XOS_SQLITE_MAX_PATH - 1;
    xos_vfs.zName = "xos";
    xos_vfs.xOpen = xOpen;
    xos_vfs.xDelete = xDelete;
    xos_vfs.xAccess = xAccess;
    xos_vfs.xFullPathname = xFullPathname;
    xos_vfs.xDlOpen = xDlOpen;
    xos_vfs.xDlError = xDlError;
    xos_vfs.xDlSym = xDlSym;
    xos_vfs.xDlClose = xDlClose;
    xos_vfs.xRandomness = xRandomness;
    xos_vfs.xSleep = xSleep;
    xos_vfs.xCurrentTime = xCurrentTime;
    xos_vfs.xGetLastError = xGetLastError;
    return sqlite3_vfs_register(&xos_vfs, 1);
}

int sqlite3_os_end(void) { return SQLITE_OK; }
