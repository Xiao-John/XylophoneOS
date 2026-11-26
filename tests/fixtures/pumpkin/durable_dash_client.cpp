// SPDX-License-Identifier: Apache-2.0
#include "durable_probe.hpp"
#include "../../../src/user/services/files_private_broker.hpp"

namespace {
using namespace xos;
using namespace xos::user::pumpkin;
using namespace xos::user::pumpkin::durable_probe;

bool read_credential(dash_offer& offer) {
    const auto deadline = user::files_private_storage::exchange_deadline();
    auto* bytes = reinterpret_cast<u8*>(&offer);
    usize offset = 0;
    if (deadline < 0 || sdk::syscall(sys_process_stdio, 0, 0, 0) != 0) {
        return false;
    }
    while (offset < sizeof(offer)) {
        const auto got = sdk::read(0, bytes + offset, sizeof(offer) - offset);
        if (got > 0) {
            offset += static_cast<usize>(got);
        } else if (got != process_error_would_block || !user::files_private_storage::wait_tick(deadline)) {
            return false;
        }
    }
    return true;
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    dash_offer offer;
    ipc_client connection;
    wire_reply reply;
    const bool logged_in = read_credential(offer) &&
        bind_ordinary(connection, offer.daemon) && login(connection, offer.key, reply, wire_status::ok);
    wipe_bytes(&offer, sizeof(offer));
    if (!logged_in) {
        sdk::print("PUMPKIN_DURABLE dash-auth-failed\n");
        return 90;
    }
    auto logout = operation_request(wire_operation::logout);
    logout.token = reply.token;
    if (!expect(connection, logout, reply, wire_status::ok)) {
        sdk::print("PUMPKIN_DURABLE dash-logout-failed\n");
        return 91;
    }
    sdk::print("PUMPKIN_DURABLE dash-auth-pass\n");
    return 0;
}
