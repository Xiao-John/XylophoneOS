// SPDX-License-Identifier: Apache-2.0
#include "files_private_lease.hpp"

namespace xos::user::files_private_storage {
namespace {
void clear(u8* bytes, usize length) {
    auto* data = static_cast<volatile u8*>(bytes);
    for (usize index = 0; index < length; ++index) {
        data[index] = 0;
    }
}
}

bool slot_lease::acquire(u32 binding, access rights) {
    if (occupied() || binding == 0 || (rights != access::reader && rights != access::writer) ||
        io_.read == nullptr || (rights == access::writer && io_.write_and_sync == nullptr)) {
        return false;
    }
    binding_ = binding;
    rights_ = rights;
    return true;
}

void slot_lease::release(u32 binding) {
    if (binding == 0 || binding != binding_) {
        return;
    }
    clear_stage();
    clear(scratch_, sizeof(scratch_));
    binding_ = 0;
    sequence_ = 0;
    rights_ = {};
}

void slot_lease::clear_stage() {
    clear(stage_, sizeof(stage_));
    staged_slot_ = slot_count;
    staged_bytes_ = 0;
}

bool slot_lease::dispatch(u32 binding, const request& request, response& response) {
    response = {};
    if (binding == 0 || binding != binding_ || request.version != protocol_version ||
        request.reserved != 0 || request.op < operation::read || request.op > operation::abort ||
        request.sequence == 0 || request.sequence != sequence_ + 1 ||
        request.slot >= slot_count || request.length > payload_bytes) {
        return false;
    }
    const bool carries_bytes = request.op == operation::chunk;
    for (usize index = carries_bytes ? request.length : 0; index < sizeof(request.data); ++index) {
        if (request.data[index] != 0) {
            return false;
        }
    }
    sequence_ = request.sequence;
    response.op = request.op;
    response.sequence = request.sequence;
    response.status = execute(request, response);
    return true;
}

result slot_lease::execute(const request& request, response& response) {
    const auto op = request.op;
    if (op == operation::read || op == operation::chunk) {
        if (request.length == 0 || request.offset > slot_bytes - request.length) {
            return result::invalid;
        }
    } else if (request.offset != 0 || request.length != 0) {
        return result::invalid;
    }
    if (op != operation::read && rights_ != access::writer) {
        return result::denied;
    }
    switch (op) {
    case operation::read:
        if (staged_slot_ != slot_count) {
            return result::busy;
        }
        if (!io_.read(io_.context, request.slot, scratch_)) {
            clear(scratch_, sizeof(scratch_));
            return result::io_error;
        }
        for (u32 index = 0; index < request.length; ++index) {
            response.data[index] = scratch_[request.offset + index];
        }
        clear(scratch_, sizeof(scratch_));
        response.length = request.length;
        return result::ok;
    case operation::begin:
        if (staged_slot_ != slot_count) {
            return result::busy;
        }
        staged_slot_ = request.slot;
        return result::ok;
    case operation::chunk:
        if (staged_slot_ != request.slot || request.offset != staged_bytes_) {
            return result::invalid;
        }
        for (u32 index = 0; index < request.length; ++index) {
            stage_[staged_bytes_ + index] = request.data[index];
        }
        staged_bytes_ += request.length;
        return result::ok;
    case operation::abort:
        if (staged_slot_ != request.slot) {
            return result::invalid;
        }
        clear_stage();
        return result::ok;
    case operation::commit: {
        if (staged_slot_ != request.slot || staged_bytes_ != slot_bytes) {
            return result::invalid;
        }
        bool matched = io_.write_and_sync(io_.context, staged_slot_, stage_) &&
            io_.read(io_.context, staged_slot_, scratch_);
        for (u32 index = 0; matched && index < slot_bytes; ++index) {
            matched = stage_[index] == scratch_[index];
        }
        clear_stage();
        clear(scratch_, sizeof(scratch_));
        return matched ? result::ok : result::outcome_unknown;
    }
    }
    return result::invalid;
}
}
