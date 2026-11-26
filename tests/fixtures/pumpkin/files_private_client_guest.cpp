// SPDX-License-Identifier: Apache-2.0
#include "../../../src/user/services/files_private_broker.hpp"
#include "../../../src/user/pumpkin/account_store.hpp"

namespace {
using namespace xos;
using namespace xos::user::files_private_storage;
namespace pumpkin = xos::user::pumpkin;

constexpr pumpkin::nonce test_realm{{0x53, 0x4c, 0x54, 0x31}};
u8 slot[slot_bytes]{};

[[noreturn]] void fail(const char* where) {
    sdk::print("PUMPKIN_FILES_LEASE_FAIL ");
    sdk::print(where);
    sdk::print("\n");
    sdk::exit(91);
}

void require(bool condition, const char* where) {
    if (!condition) {
        fail(where);
    }
}

grant_reply read_offer() {
    grant_reply offer;
    auto* bytes = reinterpret_cast<u8*>(&offer);
    usize offset = 0;
    const auto deadline = exchange_deadline();
    require(deadline >= 0, "clock");
    while (offset < sizeof(offer)) {
        const auto size = sdk::read(0, bytes + offset, sizeof(offer) - offset);
        if (size > 0) {
            offset += static_cast<usize>(size);
        } else {
            require(size == process_error_would_block && wait_tick(deadline), "bootstrap-pipe");
        }
    }
    require(offer.magic == grant_magic && offer.version == protocol_version && offer.child == sdk::pid() &&
            offer.status == result::ok && offer.reserved == 0 && peer_matches(offer.channel, offer.files),
            "authenticated-files-endpoint");
    return offer;
}

class client {
public:
    explicit client(ipc_channel channel) : channel_(channel) {}

    response exchange(operation op, u32 offset = 0) {
        request message;
        message.op = op;
        message.sequence = ++sequence_;
        message.offset = offset;
        if (op == operation::read || op == operation::chunk) {
            message.length = payload_bytes;
        }
        if (op == operation::chunk) {
            __builtin_memcpy(message.data, slot + offset, sizeof(message.data));
        }
        const auto deadline = exchange_deadline();
        require(deadline >= 0 && sdk::ipc_send(channel_.send, &message, sizeof(message)) == 0, "request-not-sent");
        response reply;
        i64 received = 0;
        while ((received = sdk::ipc_recv(channel_.receive, &reply, sizeof(reply))) == process_error_would_block) {
            require(wait_tick(deadline), "outcome-unknown-timeout");
        }
        require(received == sizeof(reply) && reply.version == protocol_version && reply.op == op &&
                reply.sequence == sequence_ && reply.status <= result::outcome_unknown,
                "outcome-unknown-reply");
        const u32 expected = reply.status == result::ok && op == operation::read ? payload_bytes : 0;
        require(reply.length == expected, "malformed-reply-length");
        return reply;
    }

private:
    ipc_channel channel_;
    u64 sequence_ = 0;
};

void read_snapshot(client& reader) {
    for (u32 offset = 0; offset < slot_bytes; offset += payload_bytes) {
        const auto reply = reader.exchange(operation::read, offset);
        require(reply.status == result::ok, "read-slot");
        __builtin_memcpy(slot + offset, reply.data, reply.length);
    }
}

void verify_snapshot() {
    constexpr usize snapshot_length = 48 + 68 + 32;
    pumpkin::account_snapshot snapshot;
    require(pumpkin::decode_snapshot(slot, snapshot_length, test_realm, snapshot) &&
            snapshot.revision == 2 && snapshot.count == 1 && snapshot.accounts[0].disabled &&
            snapshot.accounts[0].name_length == 4 &&
            !__builtin_memcmp(snapshot.accounts[0].name, "test", 4), "retained-synthetic-account");
    require(!pumpkin::has_bytes(slot + snapshot_length, sizeof(slot) - snapshot_length), "slot-padding");
}

void seed(client& writer) {
    read_snapshot(writer);
    require(!pumpkin::has_bytes(slot, sizeof(slot)), "require-blank-test-slot");
    pumpkin::account_snapshot snapshot{};
    snapshot.realm = test_realm;
    snapshot.revision = 2;
    snapshot.count = 1;
    auto& record = snapshot.accounts[0];
    record.name_length = 4;
    __builtin_memcpy(record.name, "test", 4);
    record.disabled = true;
    u8 bytes[pumpkin::snapshot_capacity];
    const auto length = pumpkin::encode_snapshot(snapshot, bytes);
    require(length != 0 && length <= sizeof(slot), "encode-synthetic-account");
    __builtin_memcpy(slot, bytes, length);
    require(writer.exchange(operation::begin).status == result::ok, "begin-slot-write");
    for (u32 offset = 0; offset < slot_bytes; offset += payload_bytes) {
        require(writer.exchange(operation::chunk, offset).status == result::ok, "stage-slot-chunk");
    }
    require(writer.exchange(operation::commit).status == result::ok, "sync-and-readback");
    read_snapshot(writer);
    verify_snapshot();
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    if (sdk::syscall(sys_process_stdio, 0, 0, 0) != 0) {
        sdk::print("PUMPKIN_FILES_LEASE no-bootstrap-pipe\n");
        return 14;
    }
    require(startup != nullptr && startup->magic == startup_magic && startup->argc == 2, "startup");
    const auto* args = reinterpret_cast<const char* const*>(startup->argv);
    const auto offer = read_offer();
    client storage(offer.channel);
    if (sdk::equal(args[1], "seed")) {
        seed(storage);
        sdk::print("PUMPKIN_FILES_LEASE synchronized-readback\n");
    } else if (sdk::equal(args[1], "partial")) {
        require(storage.exchange(operation::begin).status == result::ok, "begin-partial");
        require(storage.exchange(operation::chunk).status == result::ok, "stage-partial");
        sdk::print("PUMPKIN_FILES_LEASE exit-with-uncommitted-stage\n");
    } else if (sdk::equal(args[1], "check")) {
        require(storage.exchange(operation::begin).status == result::denied, "reader-cannot-write");
        read_snapshot(storage);
        verify_snapshot();
        sdk::print("PUMPKIN_FILES_LEASE reader-verified-retention\n");
    } else {
        fail("mode");
    }
    // Exit deliberately leaves the pair to native endpoint reclamation.
    return 0;
}
