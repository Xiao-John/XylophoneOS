/* SPDX-License-Identifier: Apache-2.0 */
extern "C" int cpp_static_library_value() { return 42; }

__attribute__((noinline)) void throw_from_cpp_archive(int* destroyed) {
    struct archive_guard {
        int* count;
        ~archive_guard() { ++*count; }
    } guard{destroyed};
    throw 3;
}
