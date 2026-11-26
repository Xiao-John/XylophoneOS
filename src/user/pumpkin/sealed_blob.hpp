// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "resource_dispatch.hpp"
#include <xos/file_client.hpp>

namespace xos::user::pumpkin {

inline constexpr u32 sealed_blob_capacity = 256;
struct sealed_blob_reply {
    u32 length = 0;
    u8 bytes[sealed_blob_capacity]{};
};

// The trusted ingress supplies its authenticated connection and the read right
// it admitted for this object. Neither comes from the application's request.
struct blob_peer {
    connection_id connection;
    bool may_read;
};
struct blob_read_check {
    void* context;
    status (*authorize)(void*, const nonce&, const owner_record&);
};

// One sealed anonymous file owned by the broker's own files session. The
// broker never transfers its native handle or exports an authorization result.
class sealed_blob {
public:
    explicit sealed_blob(file::client& files) : files_(files) {}
    ~sealed_blob();
    sealed_blob(const sealed_blob&) = delete;
    sealed_blob& operator=(const sealed_blob&) = delete;

    // Called by the trusted publisher while the broker has exclusive use of
    // its file client. The object and label become visible together.
    status publish(const resource_key& key, const nonce& authority_incarnation,
                   const identity_id& owner, const u8* bytes, u32 length);
    status read(service_core& core, const blob_peer& peer, u64 now,
                const resource_request& request, sealed_blob_reply& reply);
    // A separate trusted broker retains the file and resolves the object
    // before consulting the authority. The callback also checks its local
    // client endpoint after the authorization exchange.
    status read_associated(u64 object, const blob_read_check& check, sealed_blob_reply& reply);

private:
    status read_pinned(sealed_blob_reply& reply);
    file::client& files_;
    owner_record ownership_{};
    nonce authority_incarnation_{};
    u32 handle_ = 0;
    u32 length_ = 0;
};

}
