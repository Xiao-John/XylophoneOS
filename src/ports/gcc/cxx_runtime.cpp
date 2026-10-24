// SPDX-License-Identifier: Apache-2.0
/* Minimal C++ allocation runtime for GCC host tools, not libstdc++. */
#include <new>
#include <stdlib.h>

namespace std { const nothrow_t nothrow{}; }

static void* allocate(std::size_t size) noexcept {
    return malloc(size == 0 ? 1 : size);
}

void* operator new(std::size_t size) noexcept { return allocate(size); }
void* operator new[](std::size_t size) noexcept { return allocate(size); }
void* operator new(std::size_t size, const std::nothrow_t&) noexcept { return allocate(size); }
void* operator new(std::size_t, void* where) noexcept { return where; }
void operator delete(void*, void*) noexcept {}
void* operator new[](std::size_t size, const std::nothrow_t&) noexcept { return allocate(size); }
void operator delete(void* pointer) noexcept { free(pointer); }
void operator delete[](void* pointer) noexcept { free(pointer); }
void operator delete(void* pointer, std::size_t) noexcept { free(pointer); }
void operator delete[](void* pointer, std::size_t) noexcept { free(pointer); }
void operator delete(void* pointer, const std::nothrow_t&) noexcept { free(pointer); }
void operator delete[](void* pointer, const std::nothrow_t&) noexcept { free(pointer); }
