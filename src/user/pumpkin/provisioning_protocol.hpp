// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "daemon_protocol.hpp"
#include "provisioning_store.hpp"

namespace xos::user::pumpkin {
inline constexpr u32 provisioning_magic = 0x31525050; // PPR1
inline constexpr u32 provisioning_protocol_version = 1;
enum class provisioning_operation : u32 {
    checkpoint = 1, create_application, revoke_application, read_application,
    write_application, stage_catalog, revoke_generation, admit_generation, inspect_application, delegate_publisher,
    install_application, publisher_checkpoint, activate_generation
};
enum class provisioning_role { client, registrar, catalog_publisher };
struct publisher_binding {
    u64 peer = 0;
    u32 send = 0;
    u32 receive = 0;
};
struct application_input {
    u64 application = 0;
    u64 authorization_epoch = 0;
    u64 data_revision = 0;
    identity_id owner{};
    char name[name_limit]{};
    u32 name_length = 0;
    u32 rights = 0;
    credential key{};
    u64 installation_generation = 0;
    u8 installation_sha256[32]{};
    u32 data_length = 0;
    u32 reserved = 0;
    u8 data[application_data_bytes]{};
};
struct provisioning_request {
    u32 magic = provisioning_magic;
    u32 version = provisioning_protocol_version;
    provisioning_operation operation{};
    u32 reserved = 0;
    u64 sequence = 0;
    u64 deadline = 0;
    wire_id session{};
    provisioning_version expected{};
    application_input app{};
    catalog_candidate candidate{};
    publisher_binding publisher{};
};
struct provisioning_reply {
    u32 magic = provisioning_magic;
    u32 version = provisioning_protocol_version;
    provisioning_operation operation{};
    status result = status::invalid;
    u64 sequence = 0;
    provisioning_version current{};
    application_record app{};
    credential key{};
    catalog_candidate candidate{};
};
static_assert(sizeof(application_input) == 680);
static_assert(sizeof(provisioning_request) == 1592 && sizeof(provisioning_reply) == 1560);

// registrar is supplied exclusively by the authenticated server transport;
// no wire field selects the role. The ordinary path requires a live account
// session AND a separate application credential minted by the registrar.
struct publisher_admission {
    void* context = nullptr;
    status (*delegate)(void*, const publisher_binding&) = nullptr;
};
bool dispatch_provisioning(provisioning_store& store, service_core& core, const connection_id& connection,
                           provisioning_role role, u64& last_sequence, const provisioning_request& request,
                           u64 now, const entropy_api& entropy, provisioning_reply& reply,
                           publisher_admission admission = {});
}
