/* SPDX-License-Identifier: Apache-2.0 */
/* Force the libc startup FD receiver into each opted-in executable. */
extern const unsigned int __xos_file_startup_capabilities
    __attribute__((visibility("hidden")));

__attribute__((used, retain))
static const void *const file_runtime = &__xos_file_startup_capabilities;

__attribute__((used, section(".xos.exec")))
static const struct { unsigned long long magic; unsigned int version, size; }
receiver = { 0x3349424143455858ULL, 3, 16 };
