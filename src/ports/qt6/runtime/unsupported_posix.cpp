// SPDX-License-Identifier: Apache-2.0
// Qt's Unix code references interfaces absent from XOS. Every function here
// fails explicitly; none supplies an identity, changes files, or reports success.
// These shims belong to this experimental Qt build, not the public XOS SDK.
#include <sys/types.h>
#include <sys/stat.h>
#include <pwd.h>
#include <grp.h>
#include <unistd.h>
#include <errno.h>
extern "C" int chmod(const char *, mode_t) { errno = ENOTSUP; return -1; }
extern "C" int fchmod(int, mode_t) { errno = ENOTSUP; return -1; }
extern "C" int link(const char *, const char *) { errno = ENOTSUP; return -1; }
extern "C" int symlink(const char *, const char *) { errno = ENOTSUP; return -1; }
extern "C" ssize_t readlink(const char *, char *, size_t) { errno = ENOTSUP; return -1; }
extern "C" int truncate(const char *, off_t) { errno = ENOTSUP; return -1; }
extern "C" struct passwd *getpwuid(uid_t) { errno = ENOTSUP; return nullptr; }
extern "C" struct group *getgrgid(gid_t) { errno = ENOTSUP; return nullptr; }
