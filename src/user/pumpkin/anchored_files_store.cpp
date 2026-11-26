// SPDX-License-Identifier: Apache-2.0
#include "anchored_files_store.hpp"

namespace xos::user::pumpkin {
static_assert(disk_slot_frame::header_bytes + publication_payload_capacity <= disk_slot_frame::slot_bytes);

anchored_files_store::anchored_files_store(test_slot_io slots, generation_record_io generation,
                                           const nonce& realm, publication_codec codec)
    : slots_(slots), generation_(generation), capacity_(codec.capacity), publication_({
          this,
          [](void* context, generation_mark& selected) {
              auto& provider = static_cast<anchored_files_store*>(context)->generation_;
              return provider.read(provider.context, selected);
          },
          [](void* context, u32 slot, u8* bytes, usize capacity, usize& length) {
              return static_cast<anchored_files_store*>(context)->read_slot(slot, bytes, capacity, length);
          },
          [](void* context, u32 slot, const u8* bytes, usize length) {
              return static_cast<anchored_files_store*>(context)->write_slot(slot, bytes, length);
          },
          [](void* context, const generation_mark& expected, const generation_mark& next) {
              auto& provider = static_cast<anchored_files_store*>(context)->generation_;
              return provider.publish(provider.context, expected, next);
          },
      }, realm, codec) {}

store_api anchored_files_store::api() {
    if (slots_.read == nullptr || slots_.write_and_verify == nullptr ||
        generation_.read == nullptr || generation_.publish == nullptr) {
        return {};
    }
    return publication_.store();
}

load_result anchored_files_store::read_slot(u32 slot, u8* output, usize capacity, usize& length) {
    length = 0;
    if (output == nullptr || !slots_.read(slots_.context, slot, frame_)) {
        return load_result::io_error;
    }
    usize size = 0;
    const auto result = disk_slot_frame::inspect(frame_, size, capacity_);
    if (result != load_result::loaded) {
        return result;
    }
    if (size > capacity) {
        return load_result::io_error;
    }
    __builtin_memcpy(output, frame_ + disk_slot_frame::header_bytes, size);
    length = size;
    return load_result::loaded;
}

bool anchored_files_store::write_slot(u32 slot, const u8* bytes, usize length) {
    return disk_slot_frame::encode(frame_, bytes, length, capacity_) &&
        slots_.write_and_verify(slots_.context, slot, frame_);
}

}
