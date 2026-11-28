// SPDX-License-Identifier: Apache-2.0
#include <xos/net_service_client.hpp>
#include <xos/ipc_v1.hpp>

namespace {
using namespace xos;
u64 now() { return static_cast<u64>(sdk::syscall(sys_clock_monotonic)); }
void require(bool value, const char* label) {
    if (!value) { sdk::print("NET_READINESS_PAGE_FAIL "); sdk::print(label); sdk::print("\n"); sdk::exit(91); }
}
u64 decimal(const char* text) {
    u64 value = 0;
    require(text && *text, "argument");
    while (*text) { require(*text >= '0' && *text <= '9', "decimal"); value = value * 10 + (*text++ - '0'); }
    return value;
}
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos; using namespace xos::net2;
    require(startup && startup->argc >= 3, "startup");
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    require(startup->argc == 3 || (startup->argc == 4 && sdk::equal(argv[2], "socket_foreign")) ||
            (startup->argc == 5 && sdk::equal(argv[2], "socket_owner")), "argument-count");
    ipc_v1_feature_query features{};
    require(!ipc_v1::query_features(features) && features.known_features == 0x1f &&
            features.supported_features == 0x1f, "legacy-feature-mask");
    require(!ipc_v1::query_features(features, true) && features.known_features == 0x1f &&
            features.supported_features == 0x1f, "legacy-counter-feature-mask");
    require(!ipc_v1::query_features(features, false, true) && features.known_features == 0x3f &&
            features.supported_features == 0x3f, "release-opt-in-feature-mask");
    require(!ipc_v1::query_features(features, true, true) && features.known_features == 0x3f &&
            features.supported_features == 0x3f, "release-counter-feature-mask");
    if (sdk::equal(argv[2], "foreign")) {
        u64 map = 0, length = 0;
        require(ipc_v1::grant_map(decimal(argv[1]), 0x100000d00000ull,
            ipc_v1_grant_access::read, map, length) == static_cast<i64>(ipc_v1_error::invalid_handle),
            "foreign-process-grant-denied");
        sdk::print("NET_READINESS_FOREIGN_PASS\n"); return 0;
    }
    session_client client;
    require(client.connect(decimal(argv[1])) == 0, "authenticated-service");
    capability_snapshot capabilities{};
    require(client.capabilities(now() + 2'000'000'000ull, capabilities, true) == 0 &&
            capabilities.revision == 2 && capabilities.flags == 15, "extended-capability");
    if (sdk::equal(argv[2], "socket_foreign")) {
        const auto handle = decimal(argv[3]);
        require(client.shutdown_read(handle, now() + 2'000'000'000ull) == denied, "foreign-read-shutdown-denied");
        require(client.shutdown_write(handle, now() + 2'000'000'000ull) == denied, "foreign-write-shutdown-denied");
        readiness_snapshot state{};
        require(client.readiness(handle, now() + 2'000'000'000ull, state) == denied, "foreign-readiness-denied");
        message request{}, reply{}; request.action = operation::open; request.transport = protocol::udp;
        request.address = permitted_address; request.port = 9; request.deadline = now() + 2'000'000'000ull;
        require(!client.request(request, reply) && reply.object, "owned-udp-open");
        const auto udp = reply.object;
        require(client.shutdown_read(udp, now() + 2'000'000'000ull) == unsupported, "read-shutdown-TCP-only");
        request = {}; request.action = operation::close; request.object = udp; request.deadline = now() + 2'000'000'000ull;
        require(!client.request(request, reply), "udp-close");
        sdk::print("NET_SHUTDOWN_FOREIGN_PASS\n"); return 0;
    }
    if (sdk::equal(argv[2], "socket_owner")) {
        require(sdk::length(argv[4]) == 32, "owner-nonce"); const auto port = decimal(argv[3]);
        require(port && port <= 65535, "owner-port");
        message request{}, reply{}; request.action = operation::open; request.transport = protocol::tcp;
        request.address = permitted_address; request.port = static_cast<u16>(port); request.deadline = now() + 5'000'000'000ull;
        require(!client.request(request, reply) && reply.object, "owned-tcp-open"); const auto handle = reply.object;
        const auto until = now() + 5'000'000'000ull;
        for (;;) {
            request = {}; request.action = operation::status; request.object = handle; request.deadline = now() + 2'000'000'000ull;
            require(!client.request(request, reply), "owner-status"); if (reply.flags & connected) break;
            require(now() < until && !sdk::syscall(sys_sleep_until, now() + 5'000'000), "owner-connect-wait");
        }
        sdk::print("NET_SHUTDOWN_OWNER handle="); sdk::decimal(handle); sdk::print("\n");
        require(!sdk::syscall(sys_sleep_until, now() + 2'000'000'000ull), "foreign-attempt-interval");
        request = {}; request.action = operation::send; request.object = handle; request.length = 32;
        request.deadline = now() + 2'000'000'000ull; __builtin_memcpy(request.data, argv[4], 32);
        require(client.request(request, reply) == 32, "owner-surviving-write");
        u8 data[32]{}; u32 count = 0; const auto expiry = now() + 5'000'000'000ull;
        while (count < 32) {
            request = {}; request.action = operation::receive; request.object = handle; request.flags = 32 - count;
            request.deadline = now() + 2'000'000'000ull; const auto result = client.request(request, reply);
            if (result == would_block) { require(now() < expiry && !sdk::syscall(sys_sleep_until, now() + 5'000'000), "owner-read-wait"); continue; }
            require(!result && reply.length && reply.length <= 32 - count, "owner-surviving-read");
            __builtin_memcpy(data + count, reply.data, reply.length); count += reply.length;
        }
        char text[65]{}; const char digits[] = "0123456789abcdef";
        for (u32 i = 0; i < 32; ++i) { text[i * 2] = digits[data[i] >> 4]; text[i * 2 + 1] = digits[data[i] & 15]; }
        sdk::print("NET_SHUTDOWN_DATA data="); sdk::print(text); sdk::print("\n");
        require(!client.shutdown_read(handle, now() + 2'000'000'000ull), "owner-read-shutdown");
        request = {}; request.action = operation::send; request.object = handle; request.length = 2;
        request.data[0] = 'o'; request.data[1] = 'k'; request.deadline = now() + 2'000'000'000ull;
        require(client.request(request, reply) == 2, "write-survives-read-shutdown");
        require(!client.shutdown_write(handle, now() + 2'000'000'000ull), "owner-write-shutdown");
        request = {}; request.action = operation::receive; request.object = handle; request.flags = 1;
        request.deadline = now() + 2'000'000'000ull;
        require(!client.request(request, reply) && !reply.length && (reply.flags & eof), "owned-read-EOF");
        request = {}; request.action = operation::close; request.object = handle; request.deadline = now() + 2'000'000'000ull;
        require(!client.request(request, reply), "owner-close"); sdk::print("NET_SHUTDOWN_OWNER_PASS\n"); return 0;
    }
    readiness_binding binding{}, repeated{};
    u64 held[ipc_v1_max_handles_per_process]{};
    if (sdk::equal(argv[2], "quota")) {
        u64 length = 0, refused = 0;
        for (auto& handle : held)
            require(!ipc_v1::grant_create(0, 4096, 1, handle, length) && length == 4096,
                    "fill-own-grant-quota");
        require(ipc_v1::grant_create(0, 4096, 1, refused, length) == static_cast<i64>(ipc_v1_error::resources),
                "per-process-grant-quota");
        require(client.readiness_bind(now() + 2'000'000'000ull, binding) == resources && !binding.grant,
                "delegation-quota-fails-atomically");
        require(!ipc_v1::grant_release(held[0]), "free-one-grant-credit"); held[0] = 0;
    }
    require(client.readiness_bind(now() + 2'000'000'000ull, binding) == 0, "bind");
    require(client.readiness_bind(now() + 2'000'000'000ull, repeated) == 0 &&
            repeated.grant == binding.grant && repeated.session_generation == binding.session_generation,
            "one-page-per-session");
    u64 map = 0, length = 0, other = 0;
    require(ipc_v1::grant_map(binding.grant, 0x100000d00000ull, ipc_v1_grant_access::read_write, map, length) ==
            static_cast<i64>(ipc_v1_error::denied), "write-grant-denied");
    require(ipc_v1::grant_delegate(binding.grant, sdk::pid(), 1, other) == static_cast<i64>(ipc_v1_error::denied),
            "redelegation-denied");
    require(ipc_v1::grant_map(binding.grant, 0x100000d00000ull, ipc_v1_grant_access::read, map, length) == 0 &&
            length == readiness_page_bytes, "read-grant-map");
    auto* page = reinterpret_cast<volatile readiness_page*>(0x100000d00000ull);
    const u64 limit = now() + 2'000'000'000ull;
    bool sampled = false;
    while (now() < limit) {
        const auto sequence = __atomic_load_n(&page->sequence, __ATOMIC_ACQUIRE);
        if (sequence && !(sequence & 1) && page->revision == 1 && page->count == 0 &&
            page->session_generation == binding.session_generation) { sampled = true; break; }
        require(!sdk::syscall(sys_sleep_until, now() + 1'000'000), "sample-wait");
    }
    require(sampled, "scoped-empty-page");
    if (sdk::equal(argv[2], "hold")) {
        sdk::print("NET_READINESS_PAGE_HOLD grant="); sdk::decimal(binding.grant); sdk::print("\n");
        require(!sdk::syscall(sys_sleep_until, now() + 5'000'000'000ull), "holder-wait");
        sdk::print("NET_READINESS_OWNER_EXIT_PASS\n"); sdk::exit(0);
    } else if (sdk::equal(argv[2], "service_exit")) {
        sdk::print("NET_READINESS_PAGE_WAITING_FOR_SERVICE_EXIT\n");
        const auto expiry = now() + 10'000'000'000ull;
        config_snapshot config{};
        while (now() < expiry) {
            const auto result = client.configuration(now() + 500'000'000ull, config);
            if (result == closed || result == timeout) break;
            require(result == 0 || result == unsupported, "service-progress");
            require(!sdk::syscall(sys_sleep_until, now() + 10'000'000), "exit-wait");
        }
        require(now() < expiry, "actual-service-exit");
    } else {
        require(sdk::equal(argv[2], "detach") || sdk::equal(argv[2], "quota"), "mode");
        client.close();
        require(!sdk::syscall(sys_sleep_until, now() + 100'000'000), "detach-wait");
    }
    // The grant deliberately lacks manage rights. Retirement/exit cannot turn
    // this concurrently readable mapping into an unmapped user fault.
    const auto retired_sequence = __atomic_load_n(&page->sequence, __ATOMIC_ACQUIRE);
    require(retired_sequence != 0, "retained-mapping-after-peer-loss");
    require(ipc_v1::grant_close(binding.grant) == static_cast<i64>(ipc_v1_error::denied), "global-revoke-denied");
    require(ipc_v1::grant_release(binding.grant) == 0, "client-map-close");
    require(ipc_v1::grant_release(binding.grant) == static_cast<i64>(ipc_v1_error::invalid_handle), "released-handle-stale");
    for (const auto handle : held) if (handle) require(!ipc_v1::grant_release(handle), "quota-credit-recovery");
    sdk::print("NET_READINESS_PAGE_PASS\n");
    return 0;
}
