// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "files_private_storage.hpp"

namespace xos::user::files_private_storage {

// Only used by the two processes in the opt-in storage client profile.
inline constexpr u32 protocol_version = region_version;
inline constexpr u32 grant_magic = 0x31504b50;
inline constexpr u32 payload_bytes = 2304;

enum class access : u32 { reader = 1, writer = 2 };
enum class operation : u32 { read = 1, begin, chunk, commit, abort };
enum class result : u32 { ok, invalid, denied, busy, io_error, outcome_unknown };

struct grant_request {
    u32 magic = grant_magic;
    u32 version = protocol_version;
    u64 child = 0;
    access rights{};
    u32 reserved = 0;
};
struct grant_reply {
    u32 magic = grant_magic;
    u32 version = protocol_version;
    u64 child = 0;
    u64 files = 0;
    ipc_channel channel{};
    result status = result::invalid;
    u32 reserved = 0;
};
struct request {
    u32 version = protocol_version;
    operation op{};
    u64 sequence = 0;
    u32 slot = 0;
    u32 offset = 0;
    u32 length = 0;
    u32 reserved = 0;
    u8 data[payload_bytes]{};
};
struct response {
    u32 version = protocol_version;
    operation op{};
    u64 sequence = 0;
    result status = result::invalid;
    u32 length = 0;
    u8 data[payload_bytes]{};
};
static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__);
static_assert(sizeof(grant_request) == 24 && sizeof(grant_reply) == 40);
static_assert(sizeof(request) == 2336 && sizeof(response) == 2328);

struct slot_io {
    void* context = nullptr;
    bool (*read)(void*, u32, u8 (&)[slot_bytes]) = nullptr;
    bool (*write_and_sync)(void*, u32, const u8 (&)[slot_bytes]) = nullptr;
};

class slot_lease {
public:
    explicit slot_lease(slot_io io) : io_(io) {}
    bool acquire(u32 binding, access rights);
    void release(u32 binding);
    bool occupied() const { return binding_ != 0; }

    // Binding comes from the service-owned pair. It is never in the request.
    // Wire framing or replay errors cause the transport to close the pair.
    bool dispatch(u32 binding, const request& request, response& response);

private:
    void clear_stage();
    result execute(const request& request, response& response);

    slot_io io_;
    u32 binding_ = 0;
    access rights_{};
    u64 sequence_ = 0;
    u32 staged_slot_ = slot_count;
    u32 staged_bytes_ = 0;
    u8 stage_[slot_bytes]{};
    u8 scratch_[slot_bytes]{};
};
}
