// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/account_store.hpp"
#include <xos/file_client.hpp>
#include <xos/sdk.hpp>

namespace {
using namespace xos;
using namespace xos::user::pumpkin;

// Only synthetic disabled accounts on a disposable work disk.
constexpr nonce realm{{0x70, 0x31, 0xa7}};
constexpr char directory[] = "/var/lib/pumpkin-test";
constexpr char path[] = "/var/lib/pumpkin-test/snapshot";
constexpr u64 initial_revision = account_limit + 1;
constexpr u64 changed_revision = initial_revision + 1;
constexpr char public_path[] = "/pumpkin-private";
constexpr char public_marker[] = "ordinary file on the public volume";
file::client files;
u8 bytes[snapshot_capacity]{};

[[noreturn]] void fail(const char* check) {
    sdk::print("PUMPKIN_STORAGE_FAIL ");
    sdk::print(check);
    sdk::print("\n");
    sdk::exit(91);
}

void require(bool condition, const char* check) {
    if (!condition) {
        fail(check);
    }
}

void marker(const char* state) {
    sdk::print("PUMPKIN_STORAGE ");
    sdk::print(state);
    sdk::print(" pid=");
    sdk::decimal(sdk::pid());
    sdk::print("\n");
}

void configure_snapshot(u64 revision) {
    account_snapshot snapshot{};
    snapshot.realm = realm;
    snapshot.revision = revision;
    snapshot.count = account_limit;
    for (u32 index = 0; index < account_limit; ++index) {
        auto& account = snapshot.accounts[index];
        account.name[0] = 'u';
        account.name[1] = static_cast<char>('0' + index / 10);
        account.name[2] = static_cast<char>('0' + index % 10);
        account.name_length = 3;
        account.disabled = true;
    }
    require(encode_snapshot(snapshot, bytes) == sizeof(bytes), "encode-full-snapshot");
}

void read_snapshot(u64 revision) {
    u32 length = 0;
    account_snapshot loaded{};
    require(files.read_all(path, bytes, sizeof(bytes), length) == 0 && length == sizeof(bytes),
            "read-snapshot");
    require(decode_snapshot(bytes, length, realm, loaded) && loaded.revision == revision &&
            loaded.count == account_limit && loaded.accounts[account_limit - 1].disabled,
            "readback-valid-and-same-revision");
}

void write_snapshot(u64 revision) {
    configure_snapshot(revision);
    require(files.replace(path, bytes, sizeof(bytes)) == 0, "replace-snapshot");
    require(files.sync() == 0, "synchronize-snapshot");
}

void create() {
    u64 sectors = 0;
    require(sdk::syscall(sys_block_info, reinterpret_cast<u64>(&sectors)) == block_error_denied,
            "ordinary-raw-block-denied");
    require(files.maintenance_acquire() == static_cast<i64>(file::status::busy),
            "ordinary-maintenance-denied");
    require(files.mkdir("/var") == 0 && files.mkdir("/var/lib") == 0 && files.mkdir(directory) == 0,
            "create-disposable-path");
    write_snapshot(initial_revision);
    read_snapshot(initial_revision);
    marker("initial-synchronized");
}

void interrupt() {
    configure_snapshot(changed_revision);
    require(files.begin_replace(path, sizeof(bytes)) == 0, "stage-replacement");
    require(files.chunk_replace(0, bytes, 512) == 0, "stage-first-sector");
    require(files.sync() == 0, "synchronize-staged-prefix");
    marker("staged-prefix-exit");
    // Actual process exit while a staged replacement is incomplete. A later
    // independent file session must still see the prior committed version.
    sdk::exit(70);
}

void check_private_region_policy(bool first) {
    // The runner gives this profile a 512 MiB public prefix. These are
    // ordinary, nonprivileged process calls on the disposable test disk.
    alignas(8) u8 sector[512]{};
    constexpr u64 first_private_slot = (512ull << 20) / sizeof(sector) + 1;
    require(sdk::syscall(sys_block_read, first_private_slot, reinterpret_cast<u64>(sector), 1) ==
                block_error_denied &&
            sdk::syscall(sys_block_write, first_private_slot, reinterpret_cast<u64>(sector), 1) ==
                block_error_denied, "ordinary-private-sector-denied");
    require(files.ping() == 0, "files-and-private-startup-healthy");
    if (first) {
        file::entry entries[8]{};
        u32 count = 0, cursor = 0;
        do {
            require(files.list("/", entries, 8, count, cursor) == 0, "public-root-list");
            for (u32 index = 0; index < count; ++index) {
                require(!sdk::equal(entries[index].name, public_path + 1), "synthetic-object-not-listed");
            }
        } while (cursor != 0);

        u32 handle = 0, size = 0, version = 0;
        require(files.open(public_path, file::read_only, handle, size, version) ==
            static_cast<i64>(file::status::not_found), "synthetic-object-not-openable");
        require(files.replace(public_path, public_marker, sizeof(public_marker)) == 0, "ordinary-path-usable");
    }
    char observed[sizeof(public_marker)]{};
    u32 length = 0;
    require(files.read_all(public_path, observed, sizeof(observed), length) == 0 &&
            length == sizeof(observed) && sdk::equal(observed, public_marker), "ordinary-path-roundtrip");
    require(files.block_bench(8 * 1024 * 1024) == 8 * 1024 * 1024, "public-block-bench");
    require(files.sync() == 0, "public-sync");
    marker(first ? "private-band-public-create" : "private-band-public-retained");
}

}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    require(startup != nullptr && startup->magic == startup_magic && startup->argc == 2,
            "probe-startup");
    const auto* args = reinterpret_cast<const char* const*>(startup->argv);
    require(files.init(), "file-session");
    if (sdk::equal(args[1], "create")) {
        create();
    } else if (sdk::equal(args[1], "interrupt")) {
        interrupt();
    } else if (sdk::equal(args[1], "check-initial")) {
        read_snapshot(initial_revision);
        marker("initial-retained");
    } else if (sdk::equal(args[1], "other-writer")) {
        read_snapshot(initial_revision);
        write_snapshot(changed_revision);
        marker("ordinary-session-read-and-replaced");
    } else if (sdk::equal(args[1], "check-changed")) {
        read_snapshot(changed_revision);
        marker("changed-retained");
    } else if (sdk::equal(args[1], "private-create")) {
        check_private_region_policy(true);
    } else if (sdk::equal(args[1], "private-check")) {
        check_private_region_policy(false);
    } else {
        fail("unknown-probe-mode");
    }
    return 0;
}
