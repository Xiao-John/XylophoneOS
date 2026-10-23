#include <xos/sdk.hpp>
namespace xos::sdk {
usize length(const char* text) { usize n = 0; while (text[n] != '\0') { ++n; } return n; }
void print(const char* text, u32 handle) {
    usize remaining = length(text);
    while (remaining != 0) {
        const usize chunk = remaining > 256 ? 256 : remaining;
        const i64 sent = write(handle, text, chunk);
        if (sent <= 0) { return; }
        text += sent;
        remaining -= static_cast<usize>(sent);
    }
}
void decimal(u64 value) {
    char digits[21];
    u32 at = 20;
    digits[at] = '\0';
    do { digits[--at] = static_cast<char>('0' + value % 10); value /= 10; } while (value != 0);
    print(digits + at);
}
void signed_decimal(i64 value) {
    if (value < 0) { print("-"); decimal(u64{0} - static_cast<u64>(value)); }
    else { decimal(static_cast<u64>(value)); }
}
bool equal(const char* left, const char* right) {
    while (*left != '\0' && *left == *right) { ++left; ++right; }
    return *left == *right;
}
}
