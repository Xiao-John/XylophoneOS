// SPDX-License-Identifier: Apache-2.0
#include "sealed_blob.hpp"

namespace xos::user::pumpkin {

sealed_blob::~sealed_blob() {
    if (handle_ != 0) {
        (void)files_.close(handle_);
    }
}

status sealed_blob::publish(const resource_key& key, const nonce& authority_incarnation,
                           const identity_id& owner,
                           const u8* bytes, u32 length) {
    if (handle_ != 0) {
        return status::conflict;
    }
    if (key.number == 0 || key.generation == 0 || key.registry == nonce{} || authority_incarnation == nonce{} ||
        owner.number == 0 || owner.realm == nonce{} || bytes == nullptr ||
        length == 0 || length > sealed_blob_capacity) {
        return status::invalid;
    }
    if (files_.anonymous(handle_) != 0 || handle_ == 0 ||
        files_.write(handle_, bytes, length) != length || files_.seal_anonymous(handle_) != 0) {
        // Leave any opened handle exclusively with this unavailable object
        // until the broker destroys it or exits its files session.
        return status::io_error;
    }
    ownership_ = {key, owner, resource_read};
    authority_incarnation_ = authority_incarnation;
    length_ = length;
    return status::ok;
}

status sealed_blob::read(service_core& core, const blob_peer& peer, u64 now,
                         const resource_request& request, sealed_blob_reply& reply) {
    reply = {};
    struct dispatch_context {
        sealed_blob& blob;
        const blob_peer& peer;
        sealed_blob_reply& reply;
    } call{*this, peer, reply};
    const resource_dispatch_io io{
        &call,
        [](void* context, const connection_id& caller, u64 object, resolved_resource& resolved) {
            auto& access = *static_cast<dispatch_context*>(context);
            const auto& blob = access.blob;
            if (blob.length_ == 0 || object != blob.ownership_.object.number ||
                caller != access.peer.connection || caller.incarnation != blob.authority_incarnation_ ||
                !access.peer.may_read) {
                return false;
            }
            resolved = {{caller, blob.ownership_.object, resource_read},
                        blob.ownership_, blob.handle_};
            return true;
        },
        [](void* context, const resource_key& key, u64 handle, u32 operation) {
            auto& access = *static_cast<dispatch_context*>(context);
            auto& blob = access.blob;
            if (key != blob.ownership_.object || handle != blob.handle_ || operation != resource_read) {
                return status::denied;
            }
            return blob.read_pinned(access.reply);
        }
    };
    return dispatch_resource(core, peer.connection, now, request, io);
}

status sealed_blob::read_associated(u64 object, const blob_read_check& check, sealed_blob_reply& reply) {
    reply = {};
    if (length_ == 0 || object != ownership_.object.number || check.authorize == nullptr) {
        return status::denied;
    }
    const auto allowed = check.authorize(check.context, authority_incarnation_, ownership_);
    return allowed == status::ok ? read_pinned(reply) : allowed;
}

status sealed_blob::read_pinned(sealed_blob_reply& reply) {
    sealed_blob_reply received{};
    if (files_.read_at(handle_, received.bytes, length_, 0) != length_) { return status::io_error; }
    received.length = length_;
    reply = received;
    return status::ok;
}

}
