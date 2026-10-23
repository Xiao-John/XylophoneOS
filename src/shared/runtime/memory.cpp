#include <xos/abi_types.hpp>

// GCC emits memset for aggregate initialization even in freestanding mode.
// Volatile stores prevent this implementation from becoming a call to itself.
extern "C" void* memset(void* destination, int value, xos::usize length) {
    auto* bytes = static_cast<volatile xos::u8*>(destination);
    for (xos::usize i = 0; i < length; ++i) { bytes[i] = static_cast<xos::u8>(value); }
    return destination;
}

extern "C" void* memcpy(void* destination, const void* source, xos::usize length) {
    auto* to = static_cast<volatile xos::u8*>(destination);
    const auto* from = static_cast<const volatile xos::u8*>(source);
    for (xos::usize i = 0; i < length; ++i) { to[i] = from[i]; }
    return destination;
}

extern "C" void* memmove(void* destination, const void* source, xos::usize length) {
    auto* to = static_cast<volatile xos::u8*>(destination);
    const auto* from = static_cast<const volatile xos::u8*>(source);
    if (to < from) {
        for (xos::usize i = 0; i < length; ++i) { to[i] = from[i]; }
    } else if (to > from) {
        for (xos::usize i = length; i != 0; --i) { to[i - 1] = from[i - 1]; }
    }
    return destination;
}

extern "C" int memcmp(const void* left, const void* right, xos::usize length) {
    const auto* a = static_cast<const volatile xos::u8*>(left);
    const auto* b = static_cast<const volatile xos::u8*>(right);
    for (xos::usize i = 0; i < length; ++i) {
        if (a[i] != b[i]) { return a[i] < b[i] ? -1 : 1; }
    }
    return 0;
}

extern "C" char* strchr(const char* text, int value) {
    const char target = static_cast<char>(value);
    for (;;) {
        if (*text == target) { return const_cast<char*>(text); }
        if (*text == '\0') { return nullptr; }
        ++text;
    }
}

extern "C" xos::usize strlen(const char* text) {
    xos::usize length = 0;
    while (text[length] != '\0') { ++length; }
    return length;
}
