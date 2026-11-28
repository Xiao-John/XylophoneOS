// SPDX-License-Identifier: Apache-2.0
// Production reader/admission with modeled kernel transport. Native IPC is
// separately exercised by the guest gate; this model cannot attest peer UIDs.
#include "../../../src/user/loader/dynamic/authority.hpp"
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

namespace model {
using namespace xos;
std::string mode;
u64 now = 1'000'000;
u32 connections = 0, sends = 0, closes = 0;
ipc_channel current{};
catalog::query_reply response{};
catalog::authority binding() {
    catalog::authority value{catalog::authority_version, sizeof(catalog::authority), 42, {1}, "catalog.test"};
    return value;
}
void initialize() {
    response.sequence = 1; response.status = catalog::query_status::ok;
    response.revision = 1; response.authorization_epoch = 1; response.realm[0] = 1;
    response.catalog.count = 2; response.catalog.epoch = 1; response.catalog.sdk_sha256[0] = 3;
    for (u32 i = 0; i < 2; ++i) {
        response.catalog.roots[i].generation = i + 1;
        response.catalog.roots[i].manifest_sha256[0] = static_cast<u8>(i + 1);
        std::snprintf(response.catalog.roots[i].manifest, 128, "/generation/%u/manifest", i + 1);
    }
}
}
namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    using namespace model;
    if (number == sys_clock_monotonic) return static_cast<i64>(now);
    if (number == sys_sleep_until) { assert(first >= now); now = first; return 0; }
    if (number == sys_ipc_name) {
        assert(first == static_cast<u64>(ipc_name_action::connect));
        assert(!std::strcmp(reinterpret_cast<const char*>(second), "catalog.test"));
        current = {10u + connections * 2u, 11u + connections * 2u};
        ++connections; *reinterpret_cast<ipc_channel*>(third) = current; return 0;
    }
    if (number == sys_ipc_endpoint) {
        if (first == static_cast<u64>(ipc_endpoint_action::close)) {
            assert(second == current.send || second == current.receive); ++closes; return 0;
        }
        assert(first == static_cast<u64>(ipc_endpoint_action::query_peer));
        const bool wrong = (mode == "wrong_send_peer" && second == current.send) ||
            (mode == "wrong_receive_peer" && second == current.receive);
        *reinterpret_cast<u64*>(third) = wrong ? 43 : 42; return 0;
    }
    if (number == 4) {
        assert(first == current.send && third == sizeof(catalog::query_request));
        const auto& request = *reinterpret_cast<const catalog::query_request*>(second);
        assert(request.magic == catalog::query_magic && request.version == 1 && request.sequence == 1);
        assert(request.realm[0] == 1 && request.deadline > now && request.deadline - now <= 5'000'000'000);
        ++sends; return 0;
    }
    if (number == 5) {
        assert(first == current.receive && third == sizeof(catalog::query_reply));
        if (mode == "timeout") return process_error_would_block;
        auto answer = response;
        if (mode == "wrong_realm") answer.realm[0] = 2;
        if (mode == "wrong_version") answer.version = 2;
        if (mode == "wrong_sequence") answer.sequence = 2;
        if (mode == "unavailable") answer.status = catalog::query_status::unavailable;
        std::memcpy(reinterpret_cast<void*>(second), &answer, sizeof(answer));
        return sizeof(answer);
    }
    assert(false); return process_error_invalid;
}
}
int main(int argc, char** argv) {
    using namespace xos; using namespace xos::dynamic; using namespace model;
    assert(argc == 2); mode = argv[1]; initialize();
    auto authority = binding();
    const launch::artifact root_one{1, {1}}, root_two{2, {2}}, native{};
    const auto owner = mode == "native" ? native : root_one;
    assert(restore_authority(authority, owner) == error::none);
    assert(restore_authority(authority, owner) == error::none);
    assert(restore_authority(authority, root_two) == error::state);
    authority.daemon = 44;
    assert(restore_authority(authority, owner) == error::state);
    const auto initial = authority_admission({}, root_one, now + 6'000'000'000);
    if (mode == "owner" || mode == "native") {
        assert(initial == 0);
        response.catalog.active = 1; response.catalog.revoked = 1; ++response.catalog.epoch;
        assert(authority_admission({}, root_two, now + 6'000'000'000) ==
               (mode == "native" ? 0 : process_error_denied));
        assert(authority_admission({}, root_one, now + 6'000'000'000) == process_error_denied);
        assert(authority_admission(root_one, root_two, now + 6'000'000'000) == process_error_denied);
        assert(connections == 4 && sends == 4 && closes == 8);
    } else {
        assert(initial < 0 && connections == 1 && closes == 2);
        assert(sends == ((mode == "wrong_send_peer" || mode == "wrong_receive_peer") ? 0u : 1u));
        if (mode == "timeout") assert(initial == thread_error_timeout);
    }
    std::printf("PASS catalog authority %s\n", mode.c_str());
}
