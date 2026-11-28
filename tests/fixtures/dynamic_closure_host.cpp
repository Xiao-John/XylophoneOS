// SPDX-License-Identifier: Apache-2.0
// Production closure, digest/generation and both ELF parsers. Files are modeled
// immutable OFD snapshots; this does not substitute for native integration.
#include <xos/dynamic_launch.hpp>
#include <xos/fault_sha256.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace model {
using namespace xos;
using namespace xos::dynamic;
u64 clock_value = 1'000'000, read_advance = 0;
u32 next_token = 10, next_inode = 1, opens = 0, closes = 0, reads = 0;
u32 fail_close = 0, unknown_open = 0, unknown_read = 0;
bool poisoned = false;
struct object { std::vector<u8> bytes; u32 inode; };
std::map<std::string, std::shared_ptr<object>> names;
std::map<u32, std::shared_ptr<object>> handles;
generation generations[2]{};
launch_policy initial{};
closure selected;
void require(bool good, const char* label) {
    if (!good) { std::fprintf(stderr, "FAIL %s (opens=%u closes=%u reads=%u live=%zu)\n", label, opens, closes, reads, handles.size()); std::abort(); }
}
void text(char (&target)[128], const char* input) {
    require(std::strlen(input) < sizeof(target), "test path bound"); std::strcpy(target, input);
}
void hash(const void* bytes, u32 length, u8 (&output)[32]) { sha256 value; value.update(bytes, length); value.finish(output); }
u64 integer(const std::vector<u8>& bytes, u64 at, u32 count) {
    require(at <= bytes.size() && count <= bytes.size() - at, "fixture bounds");
    u64 value = 0; for (u32 i = 0; i < count; ++i) value |= u64{bytes[at + i]} << (8 * i); return value;
}
void put(std::vector<u8>& bytes, u64 at, u64 value, u32 count) {
    require(at <= bytes.size() && count <= bytes.size() - at, "mutation bounds");
    for (u32 i = 0; i < count; ++i) bytes[at + i] = static_cast<u8>(value >> (8 * i));
}
u64 program_header(const std::vector<u8>& bytes, u32 type, bool writable = false) {
    const u64 phoff = integer(bytes, 32, 8), count = integer(bytes, 56, 2);
    for (u64 i = 0; i < count; ++i) {
        const u64 at = phoff + 56 * i;
        if (integer(bytes, at, 4) == type && (!writable || (integer(bytes, at + 4, 4) & 2))) return at;
    }
    require(false, "mutation PHDR exists"); return 0;
}
u64 file_offset(const std::vector<u8>& bytes, u64 address) {
    const u64 phoff = integer(bytes, 32, 8), count = integer(bytes, 56, 2);
    for (u64 i = 0; i < count; ++i) {
        const u64 at = phoff + 56 * i;
        const u64 start = integer(bytes, at + 16, 8), size = integer(bytes, at + 32, 8);
        if (integer(bytes, at, 4) == 1 && address >= start && address - start < size)
            return integer(bytes, at + 8, 8) + address - start;
    }
    require(false, "mutation virtual address file backed"); return 0;
}
u64 dynamic_tag(const std::vector<u8>& bytes, u64 tag) {
    const u64 phdr = program_header(bytes, 2), offset = integer(bytes, phdr + 8, 8), size = integer(bytes, phdr + 32, 8);
    for (u64 at = offset; at < offset + size; at += 16)
        if (integer(bytes, at, 8) == tag) return integer(bytes, at + 8, 8);
    require(false, "mutation dynamic tag exists"); return 0;
}
std::shared_ptr<object> load(const std::string& path) {
    std::ifstream stream(path, std::ios::binary);
    require(bool(stream), "fixture file");
    std::vector<u8> bytes((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
    return std::make_shared<object>(object{bytes, next_inode++});
}
void install_manifest(u32 index) {
    auto& value = generations[index];
    const auto* begin = reinterpret_cast<const u8*>(&value);
    auto bytes = std::make_shared<object>(object{{begin, begin + value.header.size}, next_inode++});
    names[index ? "/generations/two.bin" : "/generations/one.bin"] = bytes;
    initial.roots[index].root.id = value.header.id;
    hash(begin, value.header.size, initial.roots[index].root.sha256);
}
void setup(const std::string& directory) {
    const char* paths[]{"/app/bootstrap", interpreter_path, "/app/main", "/lib/libstdc++.so.6"};
    const char* leaves[]{"bootstrap.elf", "interpreter.so", "main.elf", "library.so"};
    for (u32 i = 0; i < 4; ++i) names[paths[i]] = load(directory + '/' + leaves[i]);
    for (u32 n = 0; n < 2; ++n) {
        auto& g = generations[n];
        g.header = {generation_magic, generation_version, sizeof(generation_header) + 4 * sizeof(generation_object),
                    101 + n, 4, 0, {0xb1}, {0xa1}, 0, 0, 5'000'000'000, 0};
        for (u32 i = 0; i < 4; ++i) {
            auto& expected = g.objects[i]; const auto& bytes = names[paths[i]]->bytes;
            expected.file_bytes = bytes.size(); g.header.total_file_bytes += bytes.size();
            hash(bytes.data(), static_cast<u32>(bytes.size()), expected.sha256);
            expected.identity = {identity_magic, identity_version, sizeof(object_identity), static_cast<object_role>(i + 1),
                62, 1, 1, 1, 1, 2, profile_glibc_v1, cpu_x86_64_baseline, {0xa1}, {}};
            text(expected.path, paths[i]);
            if (i) {
                expected.bias = 0x140000000000ULL + i * 0x200000;
                const u64 phoff = integer(bytes, 32, 8), count = integer(bytes, 56, 2);
                for (u64 p = 0; p < count; ++p) if (integer(bytes, phoff + p * 56, 4) == 1) {
                    const u64 end = integer(bytes, phoff + p * 56 + 16, 8) + integer(bytes, phoff + p * 56 + 40, 8);
                    if (end > expected.span) expected.span = (end + 4095) & ~u64{4095};
                }
                g.header.mapping_budget += expected.span;
            }
        }
        text(g.objects[1].soname, "ld_xos_x86_64.so.1");
        text(g.objects[3].soname, "libstdc++.so.6");
        g.objects[2].needed_count = 1; g.objects[2].needed[0] = 3;
        install_manifest(n);
    }
    initial.count = 2; initial.active = 0; initial.sequence = 1; initial.sdk_sha256[0] = 0xb1;
    text(initial.roots[0].manifest, "/generations/one.bin"); text(initial.roots[1].manifest, "/generations/two.bin");
}
u64 deadline() { return clock_value + 10'000'000'000; }
void configure_ok() {
    const auto result = configure(initial, deadline());
    if (result != error::none) std::fprintf(stderr, "configure error=%u\n", static_cast<u32>(result));
    require(result == error::none && configured() && handles.empty(), "full configure preflight");
}
launch::artifact artifact(u32 index) {
    launch::artifact result{}; result.id = initial.roots[index].root.id;
    std::memcpy(result.sha256, initial.roots[index].root.sha256, 32); return result;
}
void negative_bootstrap(const std::string& name) {
    auto& bytes = names["/app/bootstrap"]->bytes;
    const u64 target = name == "bootstrap_thread_arena" ? 0x70000000 : 0x71000000;
    const u64 first_load = program_header(bytes, 1);
    const u64 base = integer(bytes, first_load + 16, 8);
    require(base < target, "bootstrap fixture can be shifted upward");
    const u64 delta = target - base;
    put(bytes, 24, integer(bytes, 24, 8) + delta, 8);
    const u64 phoff = integer(bytes, 32, 8), count = integer(bytes, 56, 2);
    for (u64 i = 0; i < count; ++i) {
        const u64 at = phoff + 56 * i;
        for (const u32 field : {16U, 24U}) {
            const u64 address = integer(bytes, at + field, 8);
            if (address) put(bytes, at + field, address + delta, 8);
        }
    }
    // Retain the actual read-only identity NOTE in its original LOAD and move
    // every virtual address consistently. Legacy static admission accepts this
    // ELF; only dynamic bootstrap admission reserves workers and the capsule.
    elf::load_plan ordinary{};
    require(elf::inspect(bytes.data(), bytes.size(), elf::machine_x86_64, ordinary) == elf::error::none
            && ordinary.count && ordinary.segments[0].address == target,
            "ordinary static inspector accepts shifted real bootstrap");
    for (u32 i = 0; i < 2; ++i) {
        hash(bytes.data(), static_cast<u32>(bytes.size()), generations[i].objects[0].sha256);
        install_manifest(i);
    }
    require(configure(initial, deadline()) == error::bounds && !configured() && handles.empty(),
            "approved dynamic bootstrap cannot overlap worker or capsule storage");
}
void negative_elf(const std::string& name) {
    const u32 index = name == "elf_soname" || name == "elf_tls" ? 3 : 2;
    const char* path = index == 3 ? "/lib/libstdc++.so.6" : "/app/main";
    auto& bytes = names[path]->bytes;
    if (name == "elf_needed" || name == "elf_soname") {
        constexpr char soname[] = "libstdc++.so.6";
        bool found = false;
        for (u64 i = 0; i + sizeof(soname) <= bytes.size(); ++i)
            if (!std::memcmp(bytes.data() + i, soname, sizeof(soname))) { bytes[i] = 'X'; found = true; break; }
        require(found, "actual dynamic dependency string");
    } else if (name == "elf_wx") {
        const u64 phdr = program_header(bytes, 1, true); put(bytes, phdr + 4, 7, 4);
    } else if (name == "elf_relro") {
        put(bytes, program_header(bytes, 0x6474e552), 0, 4);
    } else if (name == "elf_relocation") {
        put(bytes, file_offset(bytes, dynamic_tag(bytes, 23)), 0x30000000, 8);
    } else if (name == "elf_tls") {
        put(bytes, program_header(bytes, 7) + 48, 8192, 8);
    } else if (name == "elf_version") {
        const u64 need = file_offset(bytes, dynamic_tag(bytes, 0x6ffffffe));
        const u64 auxiliary = need + integer(bytes, need + 8, 4);
        put(bytes, auxiliary, integer(bytes, auxiliary, 4) ^ 1, 4);
    } else require(false, "negative ELF case");
    for (u32 i = 0; i < 2; ++i) {
        hash(bytes.data(), static_cast<u32>(bytes.size()), generations[i].objects[index].sha256);
        install_manifest(i);
    }
    const auto result = configure(initial, deadline());
    require(result == (name == "elf_needed" || name == "elf_soname" ? error::dependency : error::header)
            && !configured() && handles.empty(), "approved digest cannot bypass ELF metadata rejection");
}
}

namespace xos::sdk {
i64 syscall(u64 number, u64, u64, u64) {
    if (number == 6) return 100;
    if (number == sys_clock_monotonic) return static_cast<i64>(model::clock_value);
    model::require(false, "unexpected syscall"); return -999;
}
}
namespace xos::file {
bool client::init() { return deadline_ && !model::poisoned; }
i64 client::open(const char* path, u32 flags, u32& handle, u32& size, u32& version) {
    using namespace model; ++opens;
    require(deadline_ && flags == (read_only | open_pin), "explicit readonly pin with deadline");
    if (poisoned) return static_cast<i64>(status::io);
    if (clock_value >= deadline_) return transport_timeout;
    const auto found = names.find(path);
    if (found == names.end()) return static_cast<i64>(status::not_found);
    const u32 token = next_token++; handles[token] = found->second;
    if (unknown_open == opens) { poisoned = true; return transport_timeout; }
    handle = token; size = static_cast<u32>(found->second->bytes.size()); version = 1; return 0;
}
i64 client::fstat(u32 handle, u32& size, u32& attributes, u32& identity) {
    using namespace model;
    const auto found = handles.find(handle); if (found == handles.end()) return static_cast<i64>(status::bad_handle);
    require(deadline_ && clock_value < deadline_, "fstat deadline");
    size = static_cast<u32>(found->second->bytes.size()); attributes = 0; identity = found->second->inode; return 0;
}
i64 client::read_at(u32 handle, void* data, u32 length, u64 offset) {
    using namespace model; ++reads;
    if (poisoned) return static_cast<i64>(status::io);
    if (clock_value >= deadline_ || unknown_read == reads) { poisoned = true; return transport_timeout; }
    const auto found = handles.find(handle); if (found == handles.end()) return static_cast<i64>(status::bad_handle);
    const auto& bytes = found->second->bytes;
    require(offset <= bytes.size(), "read offset");
    const u64 remaining = bytes.size() - offset;
    const u32 amount = remaining < length ? static_cast<u32>(remaining) : length;
    std::memcpy(data, bytes.data() + offset, amount); clock_value += read_advance; return amount;
}
i64 client::close(u32 handle) {
    using namespace model; ++closes;
    if (poisoned) return static_cast<i64>(status::io);
    if (clock_value >= deadline_) return transport_timeout;
    const auto found = handles.find(handle); if (found == handles.end()) return static_cast<i64>(status::bad_handle);
    handles.erase(found);
    if (fail_close == closes) { poisoned = true; return transport_timeout; }
    return 0;
}
}

int main(int argc, char** argv) {
    using namespace model;
    require(argc == 3, "case and fixtures arguments"); setup(argv[2]); const std::string name = argv[1];
    if (name == "policy_validation") {
        auto bad = initial; bad.reserved = 1;
        require(configure(bad, deadline()) == error::state && !opens && !configured(), "reserved policy no IO");
        bad = initial; bad.roots[1].root = bad.roots[0].root;
        require(configure(bad, deadline()) == error::duplicate && !opens, "duplicate root no IO");
        bad = initial; bad.revoked = 1;
        require(configure(bad, deadline()) == error::state && !opens, "revoked active no IO");
        bad = initial; text(bad.roots[0].manifest, "/generations/../one.bin");
        require(configure(bad, deadline()) == error::path && !opens, "noncanonical approved path no IO");
        require(configure(initial, 0) == error::budget && !opens, "finite deadline required before IO");
        configure_ok(); require(configure(initial, deadline()) == error::state, "one-time policy installation");
    } else if (name == "wrong_sdk") {
        initial.sdk_sha256[0] ^= 1;
        require(configure(initial, deadline()) == error::sdk && !configured() && handles.empty(), "trusted SDK identity mismatch");
    } else if (name.starts_with("bootstrap_")) {
        negative_bootstrap(name);
    } else if (name.starts_with("elf_")) {
        negative_elf(name);
    } else if (name == "configure_close_unknown") {
        fail_close = 5;
        require(configure(initial, deadline()) == error::io && !configured(), "close before publication");
        const u32 before = opens;
        require(configure(initial, deadline()) == error::state && opens == before, "unknown close cannot retry config");
    } else if (name == "configure_open_unknown") {
        unknown_open = 1;
        require(configure(initial, deadline()) == error::io && !configured() && handles.size() == 1, "unknown open not published");
        const u32 before = opens;
        require(configure(initial, deadline()) == error::state && opens == before, "unknown open cannot replay");
    } else {
        configure_ok();
        if (name == "acquire_pins") {
            require(acquire("/app/main", deadline(), selected) == error::none && selected.live && handles.size() == 4, "whole real ELF closure");
            const auto old = names["/app/main"];
            names["/app/main"] = std::make_shared<object>(object{{1, 2, 3}, next_inode++});
            u8 bytes[4]{}; require(pin_read(&selected.pins[2], 0, bytes, 4) && bytes[0] == 0x7f, "rename keeps same pin");
            const auto root_id = selected.value.header.id;
            require(!release(selected) && !selected.live && handles.empty() && selected.value.header.id == root_id, "acknowledged release keeps metadata");
            const u32 before = closes; require(!release(selected) && closes == before, "release idempotent");
            names["/app/main"] = old;
            require(acquire("/different", deadline(), selected) == error::not_selected && handles.empty(), "exact path fallback only");
        } else if (name == "activation_rollback") {
            require(activate(1, 1, deadline()) == error::none && handles.empty(), "activate fully verified candidate");
            launch_policy snapshot{}; require(export_policy(snapshot) == error::none && snapshot.active == 1 && snapshot.sequence == 2, "active committed");
            const u32 before = opens;
            require(activate(0, 1, deadline()) == error::stale && opens == before, "stale no IO");
            require(activate(0, 2, deadline()) == error::none && export_policy(snapshot) == error::none && snapshot.active == 0 && snapshot.sequence == 3, "explicit rollback");
            require(!admission(nullptr, 200, {}, artifact(1), deadline()), "approved inactive root admission");
            require(revoke(1, 3) == error::none && admission(nullptr, 200, {}, artifact(1), deadline()) == process_error_denied, "current revoked root denied");
            require(activate(1, 4, deadline()) == error::revoked && export_policy(snapshot) == error::none && snapshot.active == 0 && snapshot.sequence == 4, "revoked rollback cannot restore");
        } else if (name == "failed_activation") {
            const auto bytes = names[interpreter_path];
            names.erase(interpreter_path);
            require(activate(1, 1, deadline()) == error::io && handles.empty(), "missing library cleans pins");
            launch_policy snapshot{}; require(export_policy(snapshot) == error::none && snapshot.active == 0 && snapshot.sequence == 1, "failure keeps old generation");
            names[interpreter_path] = bytes;
            require(activate(1, 1, deadline()) == error::none, "clean failure can try corrected bytes");
        } else if (name == "digest_failure") {
            auto corrupted = std::make_shared<object>(*names["/app/main"]); corrupted->bytes.back() ^= 1; names["/app/main"] = corrupted;
            require(acquire("/app/main", deadline(), selected) == error::digest && !selected.live && handles.empty(), "whole pin digest checked");
        } else if (name == "sdk_failure") {
            generations[1].header.sdk_sha256[0] ^= 1; install_manifest(1);
            // Existing controller roots remain immutable; replacing a manifest
            // must fail digest even if the adjacent bytes claim a new SDK.
            require(activate(1, 1, deadline()) == error::digest && handles.empty(), "root immutable after config");
        } else if (name == "release_unknown") {
            require(acquire("/app/main", deadline(), selected) == error::none, "acquire before uncertain close");
            const u32 token = selected.pins[0].handle; fail_close = closes + 1;
            require(release(selected) == file::transport_timeout && selected.quarantined && selected.pins[0].handle == token, "unknown close retains token");
            const u32 before = closes;
            require(release(selected) == file::transport_timeout && closes == before, "unknown close never replayed");
            require(acquire("/app/main", deadline(), selected) == error::state && selected.pins[0].handle == token, "quarantined storage cannot be reused");
        } else if (name == "read_unknown") {
            unknown_read = reads + 1;
            require(acquire("/app/main", deadline(), selected) == error::io && selected.quarantined && selected.manifest_pin.handle, "read timeout retains manifest pin");
            const u32 before = opens;
            closure another{};
            require(acquire("/app/main", deadline(), another) == error::state && opens == before, "poisoned session blocks new acquisition");
        } else if (name == "absolute_deadline") {
            const u64 expires = clock_value + 100;
            read_advance = 200;
            require(acquire("/app/main", expires, selected) != error::none && selected.quarantined && selected.deadline == expires, "one deadline cannot renew");
        } else if (name == "restore_and_heap") {
            activation_catalog restored;
            generation_root roots[]{initial.roots[0].root, initial.roots[1].root};
            require(restored.restore(roots, 2, 0, 12, 2) == error::none && restored.sequence() == 12, "restore epoch");
            activation_ticket ticket{};
            require(restored.capture(ticket) == error::none && ticket.sequence == 12 && restored.activate(1, 12) == error::revoked, "restore revocation");
            auto invalid = generations[0]; invalid.objects[2].bias = 0x1fff00000000ULL;
            require(validate_generation(invalid) == error::budget, "early heap collision rejected");
        } else if (name == "revoke_active") {
            require(revoke(0, 1) == error::none, "revoke active");
            launch_policy snapshot{};
            require(export_policy(snapshot) == error::none && snapshot.active == activation_max_generations && snapshot.sequence == 2, "no active after revocation");
            require(acquire("/app/main", deadline(), selected) == error::state, "no capture from revoked active");
            require(admission(nullptr, 200, {}, artifact(0), deadline()) == process_error_denied, "revoked admission blocked");
            require(!admission(nullptr, 200, artifact(0), artifact(1), deadline()), "old image may migrate to approved root");
            require(activate(1, 2, deadline()) == error::none, "restore service with approved root");
        } else require(false, "unknown case");
    }
    std::printf("PASS dynamic-closure host %s\n", name.c_str());
}
