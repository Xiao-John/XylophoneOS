// SPDX-License-Identifier: Apache-2.0
#include "named_resource_store.hpp"
#include <xos/fault_sha256.hpp>

namespace xos::user::pumpkin {
namespace {
constexpr char magic[] = "PUMNAME1";
constexpr usize header_bytes = 24, record_bytes = 88;
constexpr usize record_name = 24, record_payload = record_name + name_limit;
static_assert(header_bytes + record_bytes + secret_bytes == named_envelope_overhead);
static_assert(record_payload + named_resource_bytes == record_bytes);

u64 read_le(const u8* bytes, usize width) {
    u64 value = 0;
    for (usize i = 0; i < width; ++i) { value |= static_cast<u64>(bytes[i]) << (i * 8); }
    return value;
}

void write_le(u8* out, u64 value, usize width) {
    for (usize i = 0; i < width; ++i) { out[i] = static_cast<u8>(value >> (i * 8)); }
}

void hash_bytes(const u8* bytes, usize length, u8* output) {
    sha256 hash;
    hash.update(bytes, length);
    hash.finish(output);
}

bool name_is(const named_resource_record& resource, account_name name) {
    return valid_name(name) && name.length == resource.name_length &&
        __builtin_memcmp(resource.name, name.data, name.length) == 0;
}

bool decode(const nonce& realm, const u8* bytes, usize length, generation_mark& mark,
            account_snapshot& accounts, named_resource_record& object) {
    if (!bytes || length < named_envelope_overhead || length > named_envelope_capacity ||
        __builtin_memcmp(bytes, magic, sizeof(magic) - 1) != 0 || has_bytes(bytes + 20, 4)) {
        return false;
    }
    const auto revision = read_le(bytes + 8, 8);
    const auto account_length = length - named_envelope_overhead;
    if (!revision || read_le(bytes + 16, 4) != account_length ||
        !decode_snapshot(bytes + header_bytes, account_length, realm, accounts) ||
        accounts.revision > revision) { return false; }

    const auto* record = bytes + header_bytes + account_length;
    object = {};
    if (has_bytes(record, record_bytes)) {
        const auto generation = read_le(record, 8);
        const auto owner = read_le(record + 8, 8);
        const auto name_length = record[16], data_length = record[17];
        const char* name = reinterpret_cast<const char*>(record + record_name);
        if (!generation || generation > revision || !owner || owner > accounts.count ||
            !valid_name({name, name_length}) || !data_length || data_length > named_resource_bytes ||
            has_bytes(record + 18, 6) ||
            has_bytes(record + record_name + name_length, name_limit - name_length) ||
            has_bytes(record + record_payload + data_length, named_resource_bytes - data_length)) {
            return false;
        }
        object.key = {realm, generation, generation};
        object.owner = {realm, owner};
        object.name_length = name_length;
        object.length = data_length;
        __builtin_memcpy(object.name, name, name_length);
        __builtin_memcpy(object.bytes, record + record_payload, data_length);
    }
    mark = {realm, revision, length, {}};
    hash_bytes(bytes, length - secret_bytes, mark.checksum);
    return __builtin_memcmp(mark.checksum, bytes + length - secret_bytes, secret_bytes) == 0;
}

void encode(u8* out, u64 revision, const u8* accounts, usize length, const named_resource_record& object) {
    const usize total = length + named_envelope_overhead;
    wipe_bytes(out, total);
    __builtin_memcpy(out, magic, sizeof(magic) - 1);
    write_le(out + 8, revision, 8);
    write_le(out + 16, length, 4);
    __builtin_memcpy(out + header_bytes, accounts, length);
    auto* record = out + header_bytes + length;
    if (object.key.number) {
        write_le(record, object.key.generation, 8);
        write_le(record + 8, object.owner.number, 8);
        record[16] = static_cast<u8>(object.name_length);
        record[17] = static_cast<u8>(object.length);
        __builtin_memcpy(record + record_name, object.name, object.name_length);
        __builtin_memcpy(record + record_payload, object.bytes, object.length);
    }
    hash_bytes(out, total - secret_bytes, out + total - secret_bytes);
}

status outcome(replace_result result) {
    switch (result) {
    case replace_result::committed: return status::ok;
    case replace_result::unchanged: return status::io_error;
    case replace_result::conflict: return status::conflict;
    case replace_result::outcome_unknown: return status::outcome_unknown;
    }
    return status::unavailable;
}
}

publication_codec named_resource_codec() {
    return {nullptr, [](void*, const nonce& realm, const u8* bytes, usize length, generation_mark& mark) {
        account_snapshot accounts{};
        named_resource_record record{};
        return decode(realm, bytes, length, mark, accounts, record);
    }, named_envelope_capacity};
}

store_api named_resource_store::accounts() {
    if (!backing_.load || !backing_.replace) { return {}; }
    return {this,
        [](void* context, u8* bytes, usize capacity, usize& length) {
            return static_cast<named_resource_store*>(context)->load_accounts(bytes, capacity, length);
        },
        [](void* context, u64 previous, const u8* bytes, usize length) {
            return static_cast<named_resource_store*>(context)->replace_accounts(previous, bytes, length);
        }};
}

load_result named_resource_store::load_accounts(u8* out, usize capacity, usize& length) {
    length = 0;
    if (failed_ || !out) { return load_result::io_error; }
    if (!revision_) {
        usize used = 0;
        const auto result = backing_.load(backing_.context, envelope_, sizeof(envelope_), used);
        if (result == load_result::absent) { return result; }
        generation_mark mark{};
        if (result != load_result::loaded || !decode(realm_, envelope_, used, mark, decoded_, resource_)) {
            failed_ = true;
            return load_result::io_error;
        }
        revision_ = mark.revision;
        account_revision_ = decoded_.revision;
        account_length_ = used - named_envelope_overhead;
        __builtin_memcpy(account_data_, envelope_ + header_bytes, account_length_);
    }
    if (account_length_ > capacity) { return load_result::io_error; }
    __builtin_memcpy(out, account_data_, account_length_);
    length = account_length_;
    return load_result::loaded;
}

replace_result named_resource_store::replace_accounts(u64 previous, const u8* bytes, usize length) {
    if (failed_) { return replace_result::outcome_unknown; }
    if (previous != account_revision_) { return replace_result::conflict; }
    if (previous == ~u64{0} || !decode_snapshot(bytes, length, realm_, decoded_) ||
        decoded_.revision != previous + 1 || resource_.owner.number > decoded_.count) {
        return replace_result::unchanged;
    }
    return commit(bytes, length, resource_);
}

replace_result named_resource_store::commit(const u8* accounts, usize length, const named_resource_record& next) {
    if (revision_ == ~u64{0}) { return replace_result::unchanged; }
    encode(envelope_, revision_ + 1, accounts, length, next);
    const auto result = backing_.replace(backing_.context, revision_, envelope_, length + named_envelope_overhead);
    if (result == replace_result::committed) {
        ++revision_;
        if (accounts != account_data_) {
            __builtin_memcpy(account_data_, accounts, length);
            account_length_ = length;
            account_revision_ = decoded_.revision;
        }
        resource_ = next;
    } else if (result == replace_result::conflict || result == replace_result::outcome_unknown) {
        failed_ = true;
    }
    return result;
}

status named_resource_store::lookup(account_name name, named_resource_record& output) const {
    output = {};
    if (failed_ || !revision_) { return status::unavailable; }
    if (!name_is(resource_, name)) { return status::not_found; }
    output = resource_;
    return status::ok;
}

status named_resource_store::put(account_name name, const resource_key& expected, const identity_id& owner,
                                 const u8* bytes, usize length) {
    if (failed_ || !revision_) { return status::unavailable; }
    if (!valid_name(name) || !bytes || !length || length > named_resource_bytes || owner.realm != realm_ ||
        !owner.number) { return status::invalid; }
    if (resource_.key != expected || (resource_.key.number && !name_is(resource_, name))) {
        return status::conflict;
    }
    if (!decode_snapshot(account_data_, account_length_, realm_, decoded_)) { return status::corrupt; }
    if (owner.number > decoded_.count || decoded_.accounts[owner.number - 1].disabled) { return status::denied; }
    if (revision_ == ~u64{0}) { return status::exhausted; }
    named_resource_record next{{realm_, revision_ + 1, revision_ + 1}, owner,
        static_cast<u32>(name.length), static_cast<u32>(length)};
    __builtin_memcpy(next.name, name.data, name.length);
    __builtin_memcpy(next.bytes, bytes, length);
    return outcome(commit(account_data_, account_length_, next));
}

status named_resource_store::erase(account_name name, const resource_key& expected) {
    if (failed_ || !revision_) { return status::unavailable; }
    if (!name_is(resource_, name) || resource_.key != expected) { return status::conflict; }
    if (revision_ == ~u64{0}) { return status::exhausted; }
    return outcome(commit(account_data_, account_length_, {}));
}
}
