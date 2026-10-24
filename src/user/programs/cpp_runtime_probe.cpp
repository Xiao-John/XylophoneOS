// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <unwind.h>

namespace {
using callback = void (*)();

char current_worker_id = '?';
thread_local volatile xos::u64 tls_initialized = 0x584f53544c53494eull;
thread_local volatile xos::u64 tls_zero;
alignas(64) thread_local volatile xos::u8 tls_large[8193];

void print_id(const char* prefix, char id, const char* suffix) {
    char value[2] = {id, '\0'};
    xos::sdk::print(prefix);
    xos::sdk::print(value);
    xos::sdk::print(suffix);
}

void preinit_probe() { xos::sdk::print("[cpp_runtime] preinit\n"); }
void init_probe() { xos::sdk::print("[cpp_runtime] init\n"); }
void fini_probe() { print_id("[cpp_runtime] fini id=", current_worker_id, "\n"); }

__attribute__((used, section(".preinit_array"))) callback preinit_entry = preinit_probe;
__attribute__((used, section(".init_array.00100"))) callback init_entry = init_probe;
__attribute__((used, section(".fini_array.00100"))) callback fini_entry = fini_probe;

struct global_lifetime {
    global_lifetime() { xos::sdk::print("[cpp_runtime] global-ctor\n"); }
    ~global_lifetime() { print_id("[cpp_runtime] global-dtor id=", current_worker_id, "\n"); }
};

global_lifetime global_instance;

bool parse_number(const char* text, xos::u64& value) {
    if (text == nullptr || *text == '\0') { return false; }
    value = 0;
    for (const char* current = text; *current != '\0'; ++current) {
        if (*current < '0' || *current > '9') { return false; }
        const xos::u64 digit = static_cast<xos::u64>(*current - '0');
        if (value > (1000 - digit) / 10) { return false; }
        value = value * 10 + digit;
    }
    return true;
}

struct unwind_probe { unsigned frames; };
_Unwind_Reason_Code count_frame(_Unwind_Context* context, void* raw) {
    auto& probe = *static_cast<unwind_probe*>(raw);
    if (_Unwind_GetIP(context) != 0) { ++probe.frames; }
    return probe.frames >= 8 ? _URC_END_OF_STACK : _URC_NO_REASON;
}
__attribute__((noinline)) unsigned unwind_nested(unsigned depth) {
    if (depth != 0) {
        const unsigned result = unwind_nested(depth - 1);
        asm volatile("" : : : "memory");
        return result;
    }
    unwind_probe probe{};
    (void)_Unwind_Backtrace(count_frame, &probe);
    return probe.frames;
}

int fail(char id, const char* reason) {
    print_id("[cpp_runtime] FAIL id=", id, " reason=");
    xos::sdk::print(reason);
    xos::sdk::print("\n");
    return 40;
}

bool tls_is_unchanged(xos::u64 initialized_value, xos::u64 zero_value,
                      xos::u8 edge_value) {
    return tls_initialized == initialized_value && tls_zero == zero_value &&
           tls_large[0] == edge_value && tls_large[4095] == edge_value + 1 &&
           tls_large[4096] == edge_value + 2 && tls_large[8192] == edge_value + 3;
}
}

int main(int argc, char** argv) {
    if (argc != 3 || argv[1] == nullptr || argv[1][0] == '\0' || argv[1][1] != '\0') {
        return fail('?', "arguments");
    }
    const char id = argv[1][0];
    current_worker_id = id;
    xos::u64 hold_ticks = 0;
    if (!parse_number(argv[2], hold_ticks) || hold_ticks < 100 || hold_ticks > 1000) {
        return fail(id, "hold-ticks");
    }

    if (unwind_nested(3) < 4) { return fail(id, "registered-unwind-frames"); }
    print_id("[cpp_runtime] unwind id=", id, " ok\n");
    if (tls_initialized != 0x584f53544c53494eull || tls_zero != 0) {
        return fail(id, "tls-initial-state");
    }
    // GCC gcc.cc/collect2.cc find their tools with access(X_OK).
    if (access(argv[0], R_OK | X_OK) != 0 || access("/tmp", X_OK) != 0) {
        return fail(id, "executable-access");
    }
    char plain_path[] = "/tmp/access_A";
    plain_path[12] = id;
    int plain = open(plain_path, O_CREAT | O_EXCL | O_WRONLY, 0644);
    if (plain < 0 || write(plain, "x", 1) != 1 || close(plain)) { return fail(id, "access-fixture"); }
    errno = 0;
    if (access(plain_path, X_OK) != -1 || errno != EACCES || unlink(plain_path)) {
        return fail(id, "non-executable-access");
    }
    errno = 0;
    if (access(plain_path, X_OK) != -1 || errno != ENOENT) { return fail(id, "missing-access"); }
    print_id("[cpp_runtime] exec-access id=", id, " ok\n");
    const xos::u64 initialized_value = tls_initialized ^ static_cast<xos::u8>(id);
    const xos::u64 zero_value = (xos::sdk::pid() << 8) | static_cast<xos::u8>(id);
    const xos::u8 edge_value = static_cast<xos::u8>(id);
    if ((reinterpret_cast<xos::u64>(const_cast<const xos::u8*>(tls_large)) & 63u) != 0) {
        return fail(id, "tls-alignment");
    }
    tls_initialized = initialized_value;
    tls_zero = zero_value;
    tls_large[0] = edge_value;
    tls_large[4095] = edge_value + 1;
    tls_large[4096] = edge_value + 2;
    tls_large[8192] = edge_value + 3;
    if (!tls_is_unchanged(initialized_value, zero_value, edge_value)) {
        return fail(id, "tls-write");
    }

    xos::sdk::print("[cpp_runtime] ready id=");
    char id_text[2] = {id, '\0'};
    xos::sdk::print(id_text);
    xos::sdk::print(" pid=");
    xos::sdk::decimal(xos::sdk::pid());
    xos::sdk::print(" tls=ok\n");

    const xos::u64 start = xos::sdk::ticks();
    while (xos::sdk::ticks() - start < hold_ticks) {
        xos::sdk::yield();
        if (!tls_is_unchanged(initialized_value, zero_value, edge_value)) {
            return fail(id, "tls-after-yield");
        }
    }
    if (!tls_is_unchanged(initialized_value, zero_value, edge_value)) {
        return fail(id, "tls-after-pit");
    }
    print_id("[cpp_runtime] done id=", id, "\n");
    return 0;
}
