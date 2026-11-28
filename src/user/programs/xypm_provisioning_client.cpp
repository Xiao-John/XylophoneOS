// SPDX-License-Identifier: Apache-2.0
#include "xypm_provisioning_client.hpp"
#include "xypm_distribution_stage.hpp"
#include "pumpkin/native_ipc.hpp"
#include "pumpkin/provisioning_protocol.hpp"
#include <ctime>

namespace xypm_distribution {
namespace {
namespace service = xos::user::pumpkin;
using namespace xypm_native;
using xos::u8;
using xos::u32;
using xos::u64;
using xos::i64;
service::ipc_client broker;
staging_context staging;
plan prepared;
xos::ipc_channel parental{}, rendezvous{};
bool publication_unknown = false;
bool publication_confirmed = false;

uint64_t seconds_now() {
    timespec now{};
    require(::clock_gettime(CLOCK_REALTIME, &now) == 0 && now.tv_sec > 0 &&
            now.tv_nsec >= 0 && now.tv_nsec < 1000000000L, "trusted repository time is unavailable");
    return static_cast<uint64_t>(now.tv_sec);
}
u64 deadline_after(u64 delta) {
    const i64 now = service::monotonic_now();
    require(now >= 0 && static_cast<u64>(now) <= 0x7fffffffffffffffULL - delta,
            "repository monotonic deadline unavailable");
    return static_cast<u64>(now) + delta;
}
bool receive(xos::ipc_channel channel, publisher_startup& message, u64 deadline) {
    for (;;) {
        const i64 got = xos::sdk::ipc_recv(channel.receive, &message, sizeof(message));
        if (got != xos::process_error_would_block)
            return got == sizeof(message) && message.magic == publisher_startup_magic && !message.reserved;
        const i64 now = service::monotonic_now();
        if (now < 0 || static_cast<u64>(now) >= deadline || !service::sleep_tick(static_cast<u64>(now))) return false;
    }
}
void connect_publisher(const char* parent_name) {
    require(parent_name && *parent_name && std::strlen(parent_name) < 64,
            "authenticated publisher bootstrap is required");
    require(xos::sdk::ipc_channel_create(0, parental) == 0,
            "cannot create kernel-authenticated parent channel");
    const u64 parent = service::authenticated_peer(parental);
    require(parent && xos::sdk::ipc_name_connect(parent_name, rendezvous) == 0 &&
            service::authenticated_peer(rendezvous) == parent,
            "publisher rendezvous is not the actual parent");
    publisher_startup offer{};
    offer.phase = publisher_phase::offer;
    offer.channel = xos::sdk::ipc_channel_for_peer(parental);
    require(xos::sdk::ipc_send(rendezvous.send, &offer, sizeof(offer)) == 0,
            "cannot deliver publisher bootstrap offer");
    publisher_startup welcome{};
    require(receive(parental, welcome, deadline_after(service::max_request_ns)) &&
            welcome.phase == publisher_phase::broker && welcome.broker_pid &&
            welcome.broker_name[0] && std::memchr(welcome.broker_name, 0, sizeof(welcome.broker_name)),
            "publisher bootstrap was not authorized");
    service::close_ipc(rendezvous);
    xos::ipc_channel channel{};
    require(xos::sdk::ipc_name_connect(welcome.broker_name, channel) == 0 &&
            broker.bind(channel, welcome.broker_pid), "publisher connected to a different broker");
    // Establish the real daemon transport session without claiming authority.
    service::provisioning_request knock{};
    service::provisioning_reply answer{};
    knock.operation = service::provisioning_operation::checkpoint;
    require(broker.call(knock, answer) == service::exchange::received,
            "publisher session admission is unknown");
    publisher_startup connected{};
    connected.phase = publisher_phase::connected;
    connected.channel = broker.peer_channel();
    require(xos::sdk::ipc_send(parental.send, &connected, sizeof(connected)) == 0,
            "cannot request explicit catalog publisher delegation");
    publisher_startup granted{};
    require(receive(parental, granted, deadline_after(service::max_request_ns)) &&
            granted.phase == publisher_phase::delegated, "catalog publisher delegation was not confirmed");
    service::close_ipc(parental);
    // Explicit read-only role proof from the actual daemon session. Neither
    // the parent's ACK nor the public checkpoint grants publication authority.
    service::provisioning_request probe{};
    service::provisioning_reply proved{};
    probe.operation = service::provisioning_operation::publisher_checkpoint;
    const auto exchanged = broker.call(probe, proved);
    if (exchanged == service::exchange::outcome_unknown ||
        (exchanged == service::exchange::received && proved.result == service::status::outcome_unknown))
        publication_unknown = true;
    require(exchanged == service::exchange::received && proved.result == service::status::ok,
            "daemon did not grant catalog publisher authority");
}
void raw_digest(const char* text, u8 output[32]) {
    require(hash_text(text), "invalid prepared checkpoint hash");
    for (unsigned i = 0; i < 32; ++i) {
        auto n = [](char c) { return c <= '9' ? c - '0' : c - 'a' + 10; };
        output[i] = static_cast<u8>((n(text[i * 2]) << 4) | n(text[i * 2 + 1]));
    }
}
void exchange(service::provisioning_request& request, service::provisioning_reply& reply) {
    const auto result = broker.call(request, reply);
    if (result == service::exchange::outcome_unknown ||
        (result == service::exchange::received && reply.result == service::status::outcome_unknown))
        publication_unknown = true;
    require(result != service::exchange::not_sent, "catalog request was not delivered");
    require(result == service::exchange::received, "catalog request outcome is unknown; do not retry");
    require(reply.result == service::status::ok, "protected catalog rejected the request");
}
void next_catalog(const service::provisioning_reply& current,
                  const xypm_repository_auth::bootstrap& trust, const u8 (&sdk_identity)[32],
                  service::catalog_candidate& candidate) {
    candidate = current.candidate;
    require(candidate.catalog.count <= service::catalog_root_limit &&
            candidate.catalog.epoch != ~u64{0}, "protected catalog capacity/epoch rejected");
    require(prepared.authenticated.sequence > current.candidate.checkpoint.sequence,
            "repository sequence is already installed");
    if (candidate.catalog.count)
        require(!std::memcmp(candidate.catalog.sdk_sha256, sdk_identity, 32), "protected catalog SDK differs from publisher");
    else std::memcpy(candidate.catalog.sdk_sha256, sdk_identity, 32);
    unsigned index = 0;
    u8 root_hash[32];
    raw_digest(prepared.authenticated.generation_sha256, root_hash);
    for (; index < candidate.catalog.count; ++index) {
        const auto& root = candidate.catalog.roots[index];
        if (root.generation == prepared.authenticated.generation_id) {
            require(!std::memcmp(root.manifest_sha256, root_hash, 32) &&
                    !std::strcmp(root.manifest, prepared.manifest_path), "generation identity rebind rejected");
            break;
        }
    }
    require(!(candidate.catalog.revoked & (1u << index)), "revoked generation cannot be selected");
    if (index == candidate.catalog.count) {
        require(index < service::catalog_root_limit, "protected catalog is full");
        auto& root = candidate.catalog.roots[index];
        root.generation = prepared.authenticated.generation_id;
        std::memcpy(root.manifest_sha256, root_hash, 32);
        std::memcpy(root.manifest, prepared.manifest_path, sizeof(root.manifest));
        ++candidate.catalog.count;
    }
    candidate.catalog.active = index;
    ++candidate.catalog.epoch;
    sha256 repository;
    repository.update(trust.repository_id, std::strlen(trust.repository_id));
    repository.finish(candidate.checkpoint.repository_id);
    candidate.checkpoint.key_epoch = prepared.next_checkpoint.key_epoch;
    candidate.checkpoint.sequence = prepared.next_checkpoint.sequence;
    candidate.checkpoint.trusted_unix_seconds = prepared.next_checkpoint.last_trusted_unix_seconds;
    raw_digest(prepared.next_checkpoint.metadata_sha256, candidate.checkpoint.metadata_sha256);
}
}

int command(const char* directory, const char* lock, const char* parent_name,
            bool install, const xypm_repository_auth::bootstrap& trust,
            const u8 (&sdk_identity)[32], bool (*canonical_path)(const char*)) {
    jmp_buf rejected;
    error_target = &rejected;
    if (setjmp(rejected)) {
        error_target = nullptr;
        cleanup();
        service::close_ipc(parental);
        service::close_ipc(rendezvous);
        std::fprintf(stderr, "xypm: authenticated distribution stopped: %s%s%s\n", last_error,
                     publication_confirmed ? "; catalog commit was confirmed" : "",
                     publication_unknown || staging.quarantined ? "; outcome unknown, controller quarantined" : "");
        return publication_unknown || staging.quarantined ? 75 : 3;
    }
    require(!publication_unknown && !staging.quarantined, "distribution controller is quarantined");
    connect_publisher(parent_name);
    service::provisioning_request snapshot{};
    snapshot.operation = service::provisioning_operation::checkpoint;
    service::provisioning_reply current{};
    exchange(snapshot, current);
    const auto& stored = current.candidate.checkpoint;
    u8 repository_digest[32];
    sha256 repository_hash;
    repository_hash.update(trust.repository_id, std::strlen(trust.repository_id));
    repository_hash.finish(repository_digest);
    require(!stored.sequence || !std::memcmp(stored.repository_id, repository_digest, 32),
            "protected checkpoint belongs to another repository");
    xypm_repository_auth::checkpoint previous{};
    previous.key_epoch = stored.key_epoch;
    previous.sequence = stored.sequence;
    previous.last_trusted_unix_seconds = stored.trusted_unix_seconds;
    if (stored.sequence) hex_digest(stored.metadata_sha256, previous.metadata_sha256);
    verify(directory, lock, trust, previous, seconds_now(), sdk_identity, canonical_path, prepared);
    if (install) {
        service::provisioning_request publish{};
        publish.operation = service::provisioning_operation::stage_catalog;
        publish.expected = current.current;
        next_catalog(current, trust, sdk_identity, publish.candidate);
        stage(staging, directory, prepared, deadline_after(120ULL * 1000000000), canonical_path);
        prepared.next_checkpoint = xypm_repository_auth::accept_freshness(
            trust, prepared.authenticated, previous, seconds_now());
        next_catalog(current, trust, sdk_identity, publish.candidate);
        service::provisioning_reply published{};
        exchange(publish, published);
        publication_confirmed = true;
        release_staging(staging);
        std::printf("Authenticated generation installed: %llu sequence=%llu catalog_epoch=%llu\n",
            static_cast<unsigned long long>(prepared.authenticated.generation_id),
            static_cast<unsigned long long>(prepared.authenticated.sequence),
            static_cast<unsigned long long>(published.current.catalog_epoch));
    } else {
        std::printf("Authenticated generation verified: %llu sequence=%llu packages=%u\n",
            static_cast<unsigned long long>(prepared.authenticated.generation_id),
            static_cast<unsigned long long>(prepared.authenticated.sequence),
            static_cast<unsigned>(prepared.package_count));
    }
    error_target = nullptr;
    cleanup();
    return 0;
}
}
