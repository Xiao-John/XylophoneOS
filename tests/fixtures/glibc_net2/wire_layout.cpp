// SPDX-License-Identifier: Apache-2.0
#include <netinet/tcp.h>
#include <xos/net_service_abi.hpp>
#include "xos_net2_wire.h"

using xos::net2::message;
using xos::net2::operation;
static_assert(sizeof(tcphdr) == 20 && __builtin_offsetof(tcphdr, th_flags) == 13);
static_assert(TCP_NODELAY == 1 && TCP_MAXSEG == 2);
static_assert(sizeof(xos_net2_message) == sizeof(message));
static_assert(alignof(xos_net2_message) == alignof(message));
#define CHECK_FIELD(field) \
    static_assert(__builtin_offsetof(xos_net2_message, field) == __builtin_offsetof(message, field))
CHECK_FIELD(version);
CHECK_FIELD(action);
CHECK_FIELD(sequence);
CHECK_FIELD(object);
CHECK_FIELD(deadline);
CHECK_FIELD(result);
CHECK_FIELD(address);
CHECK_FIELD(port);
CHECK_FIELD(transport);
CHECK_FIELD(length);
CHECK_FIELD(flags);
CHECK_FIELD(reserved);
CHECK_FIELD(data);
#undef CHECK_FIELD
static_assert(xos_net2_version == xos::net2::version);
static_assert(xos_net2_header_bytes == xos::net2::header_bytes);
static_assert(xos_net2_payload_bytes == xos::net2::payload_bytes);
static_assert(xos_net2_tcp == static_cast<unsigned>(xos::net2::protocol::tcp));
static_assert(xos_net2_open == static_cast<unsigned>(operation::open));
static_assert(xos_net2_status == static_cast<unsigned>(operation::status));
static_assert(xos_net2_send == static_cast<unsigned>(operation::send));
static_assert(xos_net2_receive == static_cast<unsigned>(operation::receive));
static_assert(xos_net2_close == static_cast<unsigned>(operation::close));
static_assert(xos_net2_cancel == static_cast<unsigned>(operation::cancel));
static_assert(xos_net2_connecting == xos::net2::connecting && xos_net2_connected == xos::net2::connected);
static_assert(xos_net2_eof == xos::net2::eof && xos_net2_failed == xos::net2::failed);
static_assert(xos_net2_invalid == xos::net2::invalid && xos_net2_denied == xos::net2::denied);
static_assert(xos_net2_resources == xos::net2::resources && xos_net2_again == xos::net2::would_block);
static_assert(xos_net2_timeout == xos::net2::timeout && xos_net2_closed == xos::net2::closed);
static_assert(xos_net2_io == xos::net2::io && xos_net2_unsupported == xos::net2::unsupported);
static_assert(xos_net2_buffer == xos::net2::buffer_too_small && xos_net2_reset == xos::net2::reset);

static_assert(xos_net2_capabilities == static_cast<unsigned>(operation::capabilities));
static_assert(xos_net2_readiness == static_cast<unsigned>(operation::readiness));
static_assert(xos_net2_shutdown_write == static_cast<unsigned>(operation::shutdown_write));
static_assert(sizeof(xos_net2_capability_snapshot) == sizeof(xos::net2::capability_snapshot));
static_assert(sizeof(xos_net2_readiness_snapshot) == sizeof(xos::net2::readiness_snapshot));
static_assert(__builtin_offsetof(xos_net2_readiness_snapshot, error) == __builtin_offsetof(xos::net2::readiness_snapshot, error));
static_assert(xos_net2_ready_read == xos::net2::ready_read && xos_net2_ready_write == xos::net2::ready_write);
static_assert(xos_net2_ready_eof == xos::net2::ready_eof && xos_net2_ready_error == xos::net2::ready_error);
static_assert(xos_net2_ready_write_closed == xos::net2::ready_write_closed);

static_assert(sizeof(xos_net2_readiness_binding) == sizeof(xos::net2::readiness_binding));
static_assert(sizeof(xos_net2_readiness_page) == sizeof(xos::net2::readiness_page));
static_assert(xos_net2_readiness_bind == static_cast<unsigned>(xos::net2::operation::readiness_bind));
static_assert(xos_net2_shutdown_read == static_cast<unsigned>(xos::net2::operation::shutdown_read));
static_assert(xos_net2_cap_readiness_page == xos::net2::capability_readiness_page);
static_assert(xos_net2_ready_read_closed == xos::net2::ready_read_closed);
