// SPDX-License-Identifier: Apache-2.0
#include "native_ipc.hpp"
#if XOS_PUMPKIN_DURABLE_PROBE
#include "files_slot_client.hpp"
#endif
#if XOS_PUMPKIN_ANCHORED_PROBE
#include "generation_guest.hpp"
#endif
#if XOS_PUMPKIN_NATIVE_LOGIN
#include "login_resource.hpp"
#endif

namespace {
using namespace xos;
using namespace xos::user::pumpkin;

// Test-only store. Every invocation has a freshly generated install realm.
struct volatile_store {
    u8 bytes[snapshot_capacity]{};
    usize length = 0;
    u64 revision = 0;

    static load_result load(void* context, u8* output, usize capacity, usize& length) {
        const auto& store = *static_cast<volatile_store*>(context);
        if (store.length == 0) {
            return load_result::absent;
        }
        if (store.length > capacity) {
            return load_result::io_error;
        }
        __builtin_memcpy(output, store.bytes, store.length);
        length = store.length;
        return load_result::loaded;
    }

    static replace_result replace(void* context, u64 previous, const u8* bytes, usize length) {
        auto& store = *static_cast<volatile_store*>(context);
        if (previous != store.revision) {
            return replace_result::conflict;
        }
        if (length == 0 || length > sizeof(store.bytes) || previous == ~u64{0}) {
            return replace_result::unchanged;
        }
        __builtin_memcpy(store.bytes, bytes, length);
        store.length = length;
        ++store.revision;
        return replace_result::committed;
    }
};

bool kernel_entropy(void*, u8* output, usize length) {
    return sdk::syscall(sys_random_bytes, reinterpret_cast<u64>(output), length) == 0;
}

bool introduce_control(const char* name, u64 parent, const ipc_channel& control, const nonce& realm) {
    ipc_channel rendezvous{};
    if (sdk::ipc_name_connect(name, rendezvous) != 0) {
        return false;
    }
    bool consumed = false;
    const control_message offer{wire_version, 0, sdk::ipc_channel_for_peer(control), realm};
    const i64 opened = monotonic_now();
    if (opened >= 0 && authenticated_peer(rendezvous) == parent &&
        sdk::ipc_send(rendezvous.send, &offer, sizeof(offer)) == 0) {
        const auto deadline = static_cast<u64>(opened) + max_request_ns;
        for (;;) {
            const auto ready = sdk::ipc_wait(rendezvous.send, ipc_wait_mode::try_send);
            if (ready == 0) {
                consumed = true;
                break;
            }
            const auto now = monotonic_now();
            if (ready != process_error_would_block || now < 0 ||
                static_cast<u64>(now) >= deadline || !sleep_tick(static_cast<u64>(now))) {
                break;
            }
        }
    }
    close_ipc(rendezvous);
    return consumed;
}

int serve_with_parent(const store_api& store, const nonce& realm, const entropy_api& entropy,
                      const char* rendezvous, const char* service_name, backing_liveness backing = {},
                      login_resource* resource = nullptr) {
    // Zero binds to the real parent. The discovery name supplies no authority.
    ipc_channel control{};
    if (sdk::ipc_channel_create(0, control) != 0) {
        return 11;
    }
    const u64 controller = authenticated_peer(control);
    if (controller == 0 || !introduce_control(rendezvous, controller, control, realm)) {
        close_ipc(control);
        return 11;
    }
    return serve_native(store, realm, entropy, control, controller, service_name, backing, resource);
}

}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    if (startup == nullptr || startup->magic != startup_magic || startup->argc != 3) {
        return 10;
    }
    const auto* args = reinterpret_cast<const char* const*>(startup->argv);
    const entropy_api entropy{nullptr, kernel_entropy};
#if XOS_PUMPKIN_ANCHORED_PROBE
    const bool anchor_initialize = sdk::equal(args[1], "--anchored-init-test");
    if (anchor_initialize || sdk::equal(args[1], "--anchored-test")) {
        files_slot_client slots;
        anchor_guest::client generation;
        if (!slots.bind_bootstrap() || !generation.bind_bootstrap()) {
            return 11;
        }
        anchored_files_store storage(slots.io(), generation.io(), disk_test_realm);
        const auto store = storage.api();
        if (anchor_initialize && provision_store(store, disk_test_realm) != status::ok) {
            return 11;
        }
        struct live_backends { files_slot_client& slots; anchor_guest::client& generation; } live{slots, generation};
#if XOS_PUMPKIN_NATIVE_LOGIN
        login_resource approved_resource;
        auto* resource = &approved_resource;
#else
        login_resource* resource = nullptr;
#endif
        return serve_with_parent(store, disk_test_realm, entropy, args[2], disk_test_service,
                                  {&live, [](void* context) {
                                       const auto& state = *static_cast<live_backends*>(context);
                                       return state.slots.live() && state.generation.live();
                                   }}, resource);
    }
#endif
#if XOS_PUMPKIN_DURABLE_PROBE
    const bool initialize = sdk::equal(args[1], "--durable-init-test");
    if (initialize || sdk::equal(args[1], "--durable-test")) {
        files_slot_client slots;
        if (!slots.bind_bootstrap()) {
            return 11;
        }
        disk_test_store storage(slots.io());
        const auto store = storage.api();
        if (initialize && provision_store(store, disk_test_realm) != status::ok) {
            return 11;
        }
        return serve_with_parent(store, disk_test_realm, entropy, args[2], disk_test_service,
                                  {&slots, [](void* context) {
                                       return static_cast<files_slot_client*>(context)->live();
                                   }});
    }
#endif
    if (!sdk::equal(args[1], "--volatile-test")) {
        return 10;
    }

    nonce realm{};
    volatile_store memory;
    const store_api store{&memory, volatile_store::load, volatile_store::replace};
    if (!kernel_entropy(nullptr, realm.bytes, sizeof(realm.bytes)) ||
        provision_store(store, realm) != status::ok) {
        return 11;
    }

    return serve_with_parent(store, realm, entropy, args[2], test_service_name);
}
