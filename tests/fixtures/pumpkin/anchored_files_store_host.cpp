// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/anchored_files_store.hpp"
#include "pumpkin/service_core.hpp"

namespace {
using namespace xos;
using namespace xos::user::pumpkin;
using disk_slot_frame::slot_bytes;

constexpr nonce realm{{0x51, 0x70, 0x44, 0x32}};
constexpr account_name name{"fixture-account", 15};
enum class action : u32 { load, provision, enroll, authenticate, revoke };

struct host_io {
    bool (*read_slot)(u32, u8*, usize);
    bool (*write_slot)(u32, const u8*, usize);
    u32 (*read_mark)(generation_mark*);
    u32 (*publish_mark)(const generation_mark*, const generation_mark*);
};
static_assert(sizeof(generation_mark) == 64); // host fixture ctypes layout

test_slot_io slots(host_io& io) {
    return {
        &io,
        [](void* context, u32 slot, u8 (&frame)[slot_bytes]) {
            return static_cast<host_io*>(context)->read_slot(slot, frame, sizeof(frame));
        },
        [](void* context, u32 slot, const u8 (&frame)[slot_bytes]) {
            return static_cast<host_io*>(context)->write_slot(slot, frame, sizeof(frame));
        },
    };
}

generation_record_io authority(host_io& io) {
    return {
        &io,
        [](void* context, generation_mark& mark) {
            return static_cast<load_result>(static_cast<host_io*>(context)->read_mark(&mark));
        },
        [](void* context, const generation_mark& expected, const generation_mark& next) {
            return static_cast<replace_result>(static_cast<host_io*>(context)->publish_mark(&expected, &next));
        },
    };
}

bool synthetic_entropy(void*, u8* bytes, usize length) {
    for (usize i = 0; i < length; ++i) {
        bytes[i] = static_cast<u8>(0x53 + i);
    }
    return true;
}

status run(host_io& io, action operation) {
    anchored_files_store adapter(slots(io), authority(io), realm);
    const auto store = adapter.api();
    if (operation == action::provision) {
        return provision_store(store, realm);
    }

    service_core core;
    const auto started = core.start(store, realm, {nullptr, synthetic_entropy});
    if (started != status::ok || operation == action::load) {
        return started;
    }

    connection_id registrar;
    if (core.attach(admission_role::registrar, 0, registrar) != status::ok) {
        return status::invalid;
    }
    credential key{};
    if (operation == action::enroll) {
        identity_id identity;
        const auto result = core.create_account(registrar, 0, name, identity, key);
        wipe_bytes(key.bytes, sizeof(key.bytes));
        return result;
    }

    connection_id client;
    if (core.attach(admission_role::client, 0, client) != status::ok) {
        return status::invalid;
    }
    session_id session;
    synthetic_entropy(nullptr, key.bytes, sizeof(key.bytes));
    const auto logged_in = core.authenticate(client, 0, name, key, session);
    wipe_bytes(key.bytes, sizeof(key.bytes));
    if (logged_in != status::ok || operation == action::authenticate) {
        return logged_in;
    }

    identity_id identity;
    if (operation != action::revoke || core.session_identity(client, 0, session, identity) != status::ok) {
        return status::invalid;
    }
    const auto revoked = core.revoke_account(registrar, 0, identity);
    const bool still_active = core.session_identity(client, 0, session, identity) == status::ok;
    if (still_active != (revoked == status::io_error)) {
        return status::invalid;
    }
    return revoked;
}

}

extern "C" xos::u32 pumpkin_anchored_store_fixture(host_io* io, xos::u32 operation) {
    return static_cast<xos::u32>(run(*io, static_cast<action>(operation)));
}
