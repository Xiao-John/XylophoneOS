// SPDX-License-Identifier: Apache-2.0
#include <xos/file_client.hpp>
#include <xos/sdk.hpp>
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace xos;
namespace {
file::request request;
u64 now = 100, observed_deadline = 0;
u32 sends = 0, waits = 0, receives = 0, sleeps = 0;
const char* scenario;
bool mode(const char* value) { return std::strcmp(scenario, value) == 0; }
}
namespace xos::sdk {
i64 syscall(u64 number, u64 a, u64 b, u64 c) {
    if (number == 6) return 77;
    if (number == 22) { auto* handles = reinterpret_cast<u32*>(a); handles[0] = 100; handles[1] = 101; return 0; }
    if (number == 46) return static_cast<i64>(now++);
    if (number == 47) { ++sleeps; now = a; return 0; }
    if (number == 4) {
        assert(a == 100 && c == sizeof(request));
        request = *reinterpret_cast<const file::request*>(b);
        assert(request.request_id == ++sends);
        return mode("send_failure") ? -1 : 0;
    }
    if (number == 5) {
        assert(a == 101 && c == sizeof(file::response));
        ++receives;
        if (mode("timeout") || mode("legacy_timeout") || ((mode("ready") || mode("at_deadline")) && !waits)) return -3;
        if (mode("closed")) return -1;
        auto& response = *reinterpret_cast<file::response*>(b);
        response = {};
        response.magic = file::response_magic;
        response.version = file::abi_version;
        response.request_id = request.request_id;
        if (mode("bad_magic")) response.magic = 0;
        if (mode("bad_sequence")) ++response.request_id;
        if (mode("bad_size")) return 1;
        if (mode("bad_status")) response.status_code = -17;
        if (mode("bad_length")) response.length = sizeof(response.data) + 1;
        return sizeof(response);
    }
    if (number == sys_ipc_wait) {
        assert(a == 101 && b == 4);
        ++waits;
        if (observed_deadline) assert(observed_deadline == c); else observed_deadline = c;
        if (mode("timeout")) return -13;
        if (mode("legacy_timeout")) return -2;
        if (mode("at_deadline")) now = c;
        return 0;
    }
    std::printf("unexpected syscall %llu\n", static_cast<unsigned long long>(number));
    assert(false); return -1;
}
}
int main(int argc, char** argv) {
    assert(argc == 2); scenario = argv[1];
    file::client first, second;
    assert(first.init() && second.init());
    assert(!first.set_deadline(1ULL << 63));
    const bool expired = mode("expired"), ready = mode("ready"), ordinary = mode("ordinary");
    assert(first.set_deadline(expired ? 1 : 1000000));
    const auto result = first.ping();
    const bool timeout = expired || mode("timeout") || mode("legacy_timeout") || mode("at_deadline");
    assert(result == (timeout ? file::transport_timeout : ready || ordinary ? 0 : -7));
    if (expired) {
        assert(!sends && first.set_deadline(2000000));
        assert(first.ping() == 0 && second.ping() == 0 && sends == 2);
    } else if (ready || ordinary) {
        assert(second.ping() == 0 && sends == 2);
        assert(waits == (ready ? 1U : 0U));
    } else {
        assert(sends == 1 && first.init() && second.init());
        assert(first.set_deadline(0));
        assert(first.ping() == -7 && second.ping() == -7 && sends == 1);
    }
    if (mode("legacy_timeout")) assert(sleeps && waits && observed_deadline == 1000000);
    std::printf("PASS native_file_deadline %s\n", scenario);
}
