// SPDX-License-Identifier: Apache-2.0
// Segment 1a probe: sys_device (112) header validation must use the frozen
// device_abi error values; known operations are transient device_unknown
// until segments 1b-1e land their machinery.
#include <xos/device_abi.hpp>
using namespace xos;


static i64 device_call(u64 request) {
    register long rax __asm__("rax") = 112;
    register unsigned long rdi __asm__("rdi") = request;
    register unsigned long rsi __asm__("rsi") = 0;
    register unsigned long rdx __asm__("rdx") = 0;
    long result;
    __asm__ volatile("int $0x80" : "+a"(rax) : "D"(rdi), "S"(rsi), "d"(rdx) : "rcx", "r11", "memory");
    result = rax;
    return result;
}
static void emit(const char* text) {
    unsigned long n = 0; while (text[n]) { ++n; }
    register long rax __asm__("rax") = 1;
    register const void* rdi __asm__("rdi") = text;
    register unsigned long rsi __asm__("rsi") = n;
    __asm__ volatile("int $0x80" : "+a"(rax) : "D"(rdi), "S"(rsi) : "memory");
}
static bool expect(const char* name, i64 got, i64 wanted) {
    if (got == wanted) { return true; }
    emit("DEVICE_ABI_PROBE_FAIL "); emit(name); emit(" got=");
    char buffer[16]; int index = 15; buffer[index--] = 0;
    unsigned long magnitude = static_cast<unsigned long>(got < 0 ? -got : got);
    do { buffer[index--] = static_cast<char>('0' + magnitude % 10); magnitude /= 10; } while (magnitude && index > 0);
    if (got < 0) { buffer[index--] = '-'; }
    emit(buffer + index + 1); emit("\n"); return false;
}

int main() {
    alignas(8) static unsigned char storage[64];
    auto* request = reinterpret_cast<xos::device_request*>(storage);
    bool ok = true;
    auto reset = [&]() {
        *request = xos::device_request{};
        request->version = 1; request->size = sizeof(xos::device_request);
        request->operation = xos::device_operation::grant;
    };
    reset(); request->version = 2;
    ok &= expect("bad_version", device_call(reinterpret_cast<u64>(request)), xos::device_invalid);
    reset(); request->size = 63;
    ok &= expect("bad_size", device_call(reinterpret_cast<u64>(request)), xos::device_invalid);
    reset(); request->reserved = 1;
    ok &= expect("bad_reserved", device_call(reinterpret_cast<u64>(request)), xos::device_invalid);
    reset(); request->flags = 1;
    ok &= expect("bad_flags", device_call(reinterpret_cast<u64>(request)), xos::device_invalid);
    reset(); request->operation = static_cast<xos::device_operation>(999);
    ok &= expect("bad_op", device_call(reinterpret_cast<u64>(request)), xos::device_invalid);
    reset(); request->deadline_ns = 1;
    ok &= expect("deadline_on_query", device_call(reinterpret_cast<u64>(request)), xos::device_invalid);
    ok &= expect("unaligned_request", device_call(reinterpret_cast<u64>(request) + 1), xos::device_invalid);
    reset(); request->input_address = 1; request->input_length = 8;
    ok &= expect("unreadable_input", device_call(reinterpret_cast<u64>(request)), xos::device_fault);
    reset();
    ok &= expect("grant_unimplemented", device_call(reinterpret_cast<u64>(request)), xos::device_unknown);
    if (!ok) { emit("DEVICE_ABI_PROBE done_with_failures\n"); return 1; }
    emit("DEVICE_ABI_PROBE ok\n"); return 0;
}
