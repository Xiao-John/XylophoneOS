// SPDX-License-Identifier: Apache-2.0
#include "account_store.hpp"
#include <xos/fault_sha256.hpp>

namespace xos::user::pumpkin {
namespace {

constexpr u8 magic[] = {'P', 'U', 'M', 'P', 'K', 'I', 'N', 0};
constexpr u32 version = 1;
constexpr usize header_bytes = 48;
constexpr usize record_bytes = 68;

void write_integer(u8* output, u64 value, usize width) {
    for (usize index = 0; index < width; ++index) {
        output[index] = static_cast<u8>(value >> (index * 8));
    }
}

u64 read_integer(const u8* input, usize width) {
    u64 value = 0;
    for (usize index = 0; index < width; ++index) {
        value |= static_cast<u64>(input[index]) << (index * 8);
    }
    return value;
}

void digest(const u8* bytes, usize length, u8* output) {
    sha256 hash;
    hash.update(bytes, length);
    hash.finish(output);
}

bool alphanumeric(char value) {
    return (value >= 'a' && value <= 'z') || (value >= '0' && value <= '9');
}

bool same_name(const account_record& left, const account_record& right) {
    if (left.name_length != right.name_length) {
        return false;
    }
    for (usize index = 0; index < left.name_length; ++index) {
        if (left.name[index] != right.name[index]) {
            return false;
        }
    }
    return true;
}

bool decode_record(const u8* bytes, account_record& account) {
    if (bytes[1] > 1 || bytes[2] != 0 || bytes[3] != 0) {
        return false;
    }
    account.name_length = bytes[0];
    account.disabled = bytes[1] == 1;
    for (usize i = 0; i < name_limit; ++i) {
        const auto value = bytes[4 + i];
        if (i >= account.name_length && value != 0) {
            return false;
        }
        account.name[i] = static_cast<char>(value);
    }
    for (usize i = 0; i < secret_bytes; ++i) {
        account.verifier[i] = bytes[4 + name_limit + i];
    }
    return valid_name({account.name, account.name_length}) &&
        has_bytes(account.verifier, secret_bytes) != account.disabled;
}

}

bool valid_name(account_name name) {
    if (name.data == nullptr || name.length == 0 || name.length > name_limit ||
        !alphanumeric(name.data[0])) {
        return false;
    }
    for (usize index = 1; index < name.length; ++index) {
        const char value = name.data[index];
        if (!alphanumeric(value) && value != '.' && value != '_' && value != '-') {
            return false;
        }
    }
    return true;
}

bool has_bytes(const u8* bytes, usize length) {
    u8 bits = 0;
    for (usize index = 0; index < length; ++index) {
        bits |= bytes[index];
    }
    return bits != 0;
}

void wipe_bytes(void* bytes, usize length) {
    auto* volatile_bytes = static_cast<volatile u8*>(bytes);
    for (usize index = 0; index < length; ++index) {
        volatile_bytes[index] = 0;
    }
}

void credential_verifier(const identity_id& id, const credential& key, u8 (&output)[secret_bytes]) {
    constexpr char domain[] = "xos.pumpkin.enrollment.v1";
    u8 number[sizeof(id.number)]{};
    write_integer(number, id.number, sizeof(number));
    sha256 hash;
    hash.update(domain, sizeof(domain));
    hash.update(id.realm.bytes, sizeof(id.realm.bytes));
    hash.update(number, sizeof(number));
    hash.update(key.bytes, sizeof(key.bytes));
    hash.finish(output);
    wipe_bytes(&hash, sizeof(hash));
}

usize encode_snapshot(const account_snapshot& snapshot, u8 (&output)[snapshot_capacity]) {
    if (snapshot.count > account_limit) {
        return 0;
    }
    const usize length = header_bytes + snapshot.count * record_bytes + secret_bytes;
    for (usize index = 0; index < sizeof(magic); ++index) {
        output[index] = magic[index];
    }
    write_integer(output + 8, version, 4);
    write_integer(output + 12, length, 4);
    for (usize index = 0; index < sizeof(snapshot.realm.bytes); ++index) {
        output[16 + index] = snapshot.realm.bytes[index];
    }
    write_integer(output + 32, snapshot.revision, 8);
    write_integer(output + 40, snapshot.count, 4);
    write_integer(output + 44, 0, 4);
    for (u32 index = 0; index < snapshot.count; ++index) {
        const auto& account = snapshot.accounts[index];
        auto* record = output + header_bytes + index * record_bytes;
        record[0] = account.name_length;
        record[1] = account.disabled ? 1 : 0;
        record[2] = record[3] = 0;
        for (usize i = 0; i < name_limit; ++i) {
            record[4 + i] = static_cast<u8>(account.name[i]);
        }
        for (usize i = 0; i < secret_bytes; ++i) {
            record[4 + name_limit + i] = account.verifier[i];
        }
    }
    digest(output, length - secret_bytes, output + length - secret_bytes);
    return length;
}

bool decode_snapshot(const u8* bytes, usize length, const nonce& expected_realm,
                     account_snapshot& output) {
    // Output is private startup scratch and is only usable after true.
    if (bytes == nullptr || length < header_bytes + secret_bytes || length > snapshot_capacity ||
        read_integer(bytes + 8, 4) != version || read_integer(bytes + 12, 4) != length ||
        read_integer(bytes + 44, 4) != 0) {
        return false;
    }
    for (usize index = 0; index < sizeof(magic); ++index) {
        if (bytes[index] != magic[index]) {
            return false;
        }
    }
    for (usize index = 0; index < sizeof(expected_realm.bytes); ++index) {
        if (bytes[16 + index] != expected_realm.bytes[index]) {
            return false;
        }
    }
    const auto count = read_integer(bytes + 40, 4);
    const auto revision = read_integer(bytes + 32, 8);
    if (count > account_limit || revision <= count ||
        length != header_bytes + count * record_bytes + secret_bytes) {
        return false;
    }
    u8 expected_digest[secret_bytes];
    digest(bytes, length - secret_bytes, expected_digest);
    for (usize index = 0; index < secret_bytes; ++index) {
        if (expected_digest[index] != bytes[length - secret_bytes + index]) {
            return false;
        }
    }
    output.realm = expected_realm;
    output.revision = revision;
    output.count = static_cast<u32>(count);
    for (u32 index = 0; index < output.count; ++index) {
        auto& account = output.accounts[index];
        if (!decode_record(bytes + header_bytes + index * record_bytes, account)) {
            return false;
        }
        for (u32 previous = 0; previous < index; ++previous) {
            if (same_name(account, output.accounts[previous])) {
                return false;
            }
        }
    }
    return true;
}

status provision_store(const store_api& store, const nonce& realm) {
    if (store.replace == nullptr || !has_bytes(realm.bytes, sizeof(realm.bytes))) {
        return status::invalid;
    }
    account_snapshot snapshot{};
    snapshot.realm = realm;
    snapshot.revision = 1;
    u8 bytes[snapshot_capacity];
    const usize length = encode_snapshot(snapshot, bytes);
    switch (store.replace(store.context, 0, bytes, length)) {
    case replace_result::committed: return status::ok;
    case replace_result::conflict: return status::conflict;
    case replace_result::unchanged: return status::io_error;
    default: return status::outcome_unknown;
    }
}

}
