// SPDX-License-Identifier: Apache-2.0
#include "lwip_stack.hpp"
extern "C" {
#include "lwip/init.h"
#include "lwip/dns.h"
#include "lwip/dhcp.h"
#include "lwip/etharp.h"
#include "lwip/timeouts.h"
#include "netif/ethernet.h"
}

namespace {
xos::user::network::lwip_stack* active_stack;
xos::i64 map_error(err_t error) {
    using namespace xos::net2;
    switch (error) {
    case ERR_OK: return 0;
    case ERR_MEM: case ERR_BUF: return would_block;
    case ERR_TIMEOUT: return timeout;
    case ERR_RST: case ERR_ABRT: return reset;
    case ERR_CLSD: return closed;
    case ERR_VAL: case ERR_ARG: return invalid;
    case ERR_USE: return resources;
    default: return io;
    }
}
}
extern "C" u32_t sys_now() { return active_stack ? active_stack->milliseconds() : 0; }
extern "C" uint32_t xos_lwip_rand() { return active_stack ? active_stack->random_word() : 0; }
extern "C" int xos_lwip_dns_random(uint16_t* value) {
    if (!value) return ERR_ARG;
    xos::u32 word;
    if (!active_stack || active_stack->random_checked(word)) return ERR_IF;
    *value = static_cast<uint16_t>(word);
    return ERR_OK;
}
#ifdef XOS_LWIP_DNS_LIFETIME
extern "C" int xos_lwip_dns_clock(uint64_t* value) {
    if (!value || !active_stack) return ERR_ARG;
    const auto now = active_stack->monotonic_time();
    if (now < 0) return ERR_IF;
    *value = static_cast<uint64_t>(now);
    return ERR_OK;
}
#endif
#ifdef XOS_LWIP_DHCP_AUTHORITY
extern "C" int xos_lwip_dhcp_xid(u32_t* value) {
    return value && active_stack ? active_stack->dhcp_xid(*value) : ERR_ARG;
}
#endif
extern "C" void xos_lwip_diag(const char*, ...) { if (active_stack) active_stack->fault(); }

namespace xos::user::network {
using namespace net2;
i64 lwip_stack::monotonic_time() {
    const i64 value = io_.clock(io_.context);
    if (value < 0) failure_ = io;
    return value;
}
u32 lwip_stack::milliseconds() {
    const i64 value = monotonic_time();
    if (value < 0) return 0;
    return static_cast<u32>(static_cast<u64>(value) / 1'000'000ull);
}
u32 lwip_stack::random_word() {
    u32 result = 0;
    (void)random_checked(result);
    return result;
}
i64 lwip_stack::random_checked(u32& result) {
    if (failure_) return failure_;
    u32 word = 0;
    if (io_.random(io_.context, word)) { failure_ = io; return failure_; }
    result = word;
    return 0;
}
err_t lwip_stack::configure(netif* interface) {
    interface->name[0] = 'x'; interface->name[1] = 'n';
    interface->mtu = 1500; interface->hwaddr_len = 6;
    interface->flags = NETIF_FLAG_BROADCAST | NETIF_FLAG_ETHARP | NETIF_FLAG_LINK_UP;
    interface->output = etharp_output; interface->linkoutput = link_output;
    return ERR_OK;
}
i64 lwip_stack::initialize(const frame_io& callbacks, const u8* mac) {
    if (active_stack || active_ || !mac || !callbacks.clock || !callbacks.random ||
        !callbacks.receive || !callbacks.transmit) return invalid;
    io_ = callbacks; active_stack = this;
    (void)milliseconds(); (void)random_word();
    if (failure_) { active_stack = nullptr; return failure_; }
    lwip_init();
    ip4_addr_t address, mask, gateway;
#ifdef XOS_LWIP_DHCP_AUTHORITY
    ip4_addr_set_zero(&address); ip4_addr_set_zero(&mask); ip4_addr_set_zero(&gateway);
#else
    IP4_ADDR(&address, 10, 0, 2, 15); IP4_ADDR(&mask, 255, 255, 255, 0); IP4_ADDR(&gateway, 10, 0, 2, 2);
#endif
    for (u32 i = 0; i < 6; ++i) interface_.hwaddr[i] = mac[i];
    if (!netif_add(&interface_, &address, &mask, &gateway, this, configure, ethernet_input)) {
        active_stack = nullptr; return resources;
    }
    netif_set_default(&interface_); netif_set_up(&interface_); active_ = true;
    return failure_;
}
void lwip_stack::shutdown() {
    if (active_) {
#ifdef XOS_LWIP_DHCP_AUTHORITY
        gate_open_ = false;
        (void)lease_.invalidate(dhcp::reason::stopped);
        dhcp_enabled_ = false;
        stop_dhcp_client(); dhcp_cleanup(&interface_);
        etharp_cleanup_netif(&interface_);
#endif
#ifdef XOS_LWIP_DNS_LIFETIME
        configure_dns(0);
#endif
        for (u32 i = 0; i < connection_limit; ++i) (void)close(i, true);
        netif_set_down(&interface_); netif_remove(&interface_); active_ = false;
    }
    if (active_stack == this) active_stack = nullptr;
}
err_t lwip_stack::link_output(netif* interface, pbuf* packet) {
    auto& self = *static_cast<lwip_stack*>(interface->state);
    if (self.failure_) return ERR_IF;
    if (!packet || !packet->tot_len || packet->tot_len > 1514) return ERR_BUF;
    u8 frame[1514];
    const u16_t copied = pbuf_copy_partial(packet, frame, packet->tot_len, 0);
    if (copied != packet->tot_len) return ERR_BUF;
#ifdef XOS_LWIP_DHCP_AUTHORITY
    const auto clock = self.monotonic_time();
    if (clock < 0 || !self.dhcp_wire(frame, copied, static_cast<u64>(clock), false)) return ERR_RTE;
#endif
    const i64 result = self.io_.transmit(self.io_.context, frame, copied);
    // The frame transport uses native net2 backpressure at this boundary.
    if (result == would_block) return ERR_MEM;
    if (result) { self.failure_ = io; return ERR_IF; }
#ifdef XOS_LWIP_DHCP_AUTHORITY
    if (!self.dhcp_wire(frame, copied, static_cast<u64>(clock), true)) { self.failure_ = io; return ERR_IF; }
#endif
    return ERR_OK;
}
i64 lwip_stack::poll() {
    if (!active_ || failure_) return failure_ ? failure_ : closed;
#ifdef XOS_LWIP_DHCP_AUTHORITY
    if (advance_dhcp()) return failure_;
#endif
    const i64 began = io_.clock(io_.context);
    if (began < 0) { failure_ = io; return failure_; }
    // A queued SYN-ACK cannot revive a connection after its absolute deadline.
    expire_connects(static_cast<u64>(began));
    u8 frame[1514];
    for (u32 i = 0; i < 64; ++i) {
        const i64 size = io_.receive(io_.context, frame, sizeof(frame));
        if (size < 0) { failure_ = io; break; }
        if (!size) break;
#ifdef XOS_LWIP_DHCP_AUTHORITY
        if (advance_dhcp()) return failure_;
#endif
        if (size > static_cast<i64>(sizeof(frame))) { failure_ = io; break; }
        auto* packet = pbuf_alloc(PBUF_RAW, static_cast<u16_t>(size), PBUF_POOL);
        if (!packet) { if (dropped_ != ~u32{0}) ++dropped_; continue; }
        if (pbuf_take(packet, frame, static_cast<u16_t>(size)) != ERR_OK ||
            interface_.input(packet, &interface_) != ERR_OK) pbuf_free(packet);
    }
    // A CLOSING -> TIME_WAIT ACK has no receive/error callback. Detach before
    // timers can free such PCBs, including after an arbitrarily long pause.
    for (auto& item : connections_) if (item.tcp && item.tcp->state == TIME_WAIT) {
        tcp_arg(item.tcp, nullptr); tcp_recv(item.tcp, nullptr); tcp_err(item.tcp, nullptr);
        item.tcp = nullptr;
    }
#ifdef XOS_LWIP_DHCP_AUTHORITY
    if (advance_dhcp()) return failure_;
#endif
    sys_check_timeouts();
#ifdef XOS_LWIP_DHCP_AUTHORITY
    if (advance_dhcp()) return failure_;
#endif
    const i64 now = io_.clock(io_.context);
    if (now < 0) failure_ = io;
    else expire_connects(static_cast<u64>(now));
    return failure_;
}
void lwip_stack::expire_connects(u64 now) {
    for (u32 i = 0; i < connection_limit; ++i) {
        auto& item = connections_[i];
        if (item.tcp && !item.established && now >= item.deadline) {
            (void)close(i, true); item.error = timeout;
        }
    }
}
err_t lwip_stack::on_connected(void* context, tcp_pcb* pcb, err_t error) {
    auto& item = *static_cast<connection*>(context);
    const i64 now = active_stack ? active_stack->io_.clock(active_stack->io_.context) : -1;
    if (now < 0 || static_cast<u64>(now) >= item.deadline) {
        tcp_arg(pcb, nullptr); tcp_recv(pcb, nullptr); tcp_err(pcb, nullptr);
        tcp_abort(pcb); item.tcp = nullptr; item.ended = true;
        item.error = now < 0 ? io : timeout;
        if (now < 0 && active_stack) active_stack->failure_ = io;
        return ERR_ABRT;
    }
    item.established = error == ERR_OK; item.error = map_error(error); return ERR_OK;
}
void lwip_stack::on_error(void* context, err_t error) {
    auto& item = *static_cast<connection*>(context);
    item.tcp = nullptr;
    // lwIP reports ERR_CLSD when LAST_ACK completes after TX-only shutdown.
    // This is clean EOF, not a reset, and buffered input still belongs to us.
    item.error = error == ERR_CLSD && item.write_closed && item.ended ? 0 : map_error(error);
    item.ended = true;
}
err_t lwip_stack::on_receive(void* context, tcp_pcb* pcb, pbuf* packet, err_t error) {
    auto& item = *static_cast<connection*>(context);
    if (!packet) {
        item.ended = true;
        // An active half-close can enter TIME_WAIT before this callback. The
        // timer then owns the PCB and can free it without an error callback.
        if (pcb->state == TIME_WAIT) {
            tcp_arg(pcb, nullptr); tcp_recv(pcb, nullptr); tcp_err(pcb, nullptr);
            item.tcp = nullptr;
        }
        return ERR_OK;
    }
    if (error != ERR_OK) return error;
    if (item.read_closed) {
        tcp_recved(pcb, packet->tot_len); pbuf_free(packet); return ERR_OK;
    }
    if (packet->tot_len > tcp_receive_bytes - item.count) return ERR_MEM;
    const u32 tail = (item.head + item.count) % tcp_receive_bytes;
    const u32 first = packet->tot_len < tcp_receive_bytes - tail ? packet->tot_len : tcp_receive_bytes - tail;
    if (pbuf_copy_partial(packet, item.data + tail, static_cast<u16_t>(first), 0) != first ||
        (first < packet->tot_len && pbuf_copy_partial(packet, item.data,
          static_cast<u16_t>(packet->tot_len - first), static_cast<u16_t>(first)) != packet->tot_len - first)) {
        item.error = io; pbuf_free(packet); return ERR_OK;
    }
    item.count += packet->tot_len; pbuf_free(packet);
    // tcp_recved happens only after application consumption, preserving pressure.
    return ERR_OK;
}
void lwip_stack::on_datagram(void* context, udp_pcb*, pbuf* packet, const ip_addr_t*, u16_t) {
    auto& item = *static_cast<connection*>(context);
    if (!packet) return;
    if (item.count == udp_queue_limit || packet->tot_len > payload_bytes) {
        if (active_stack && active_stack->dropped_ != ~u32{0}) ++active_stack->dropped_;
    } else {
        const u32 tail = (item.head + item.count) % udp_queue_limit;
        const u16_t copied = pbuf_copy_partial(packet, item.data + tail * payload_bytes, packet->tot_len, 0);
        if (copied == packet->tot_len) { item.datagram_lengths[tail] = copied; ++item.count; }
    }
    pbuf_free(packet);
}
i64 lwip_stack::open(u32 slot, protocol transport, u32 address, u16 port, u64 deadline) {
#ifdef XOS_LWIP_DHCP_AUTHORITY
    if (advance_dhcp()) return failure_;
    if (!gate_open_) return closed;
#endif
    if (slot >= connection_limit || failure_) return io;
    auto& item = connections_[slot];
    if (item.tcp || item.udp) return resources;
    item = {}; item.deadline = deadline;
    ip_addr_t remote;
    IP_ADDR4(&remote, (address >> 24) & 255, (address >> 16) & 255, (address >> 8) & 255, address & 255);
    if (transport == protocol::tcp) {
        item.tcp = tcp_new_ip_type(IPADDR_TYPE_V4);
        if (!item.tcp) return resources;
        tcp_arg(item.tcp, &item); tcp_err(item.tcp, on_error); tcp_recv(item.tcp, on_receive);
        const err_t result = tcp_connect(item.tcp, &remote, port, on_connected);
        if (result != ERR_OK) { (void)close(slot, true); return map_error(result); }
    } else if (transport == protocol::udp) {
        item.udp = udp_new_ip_type(IPADDR_TYPE_V4);
        if (!item.udp) return resources;
        const err_t result = udp_connect(item.udp, &remote, port);
        if (result != ERR_OK) { (void)close(slot, true); return map_error(result); }
        udp_recv(item.udp, on_datagram, &item); item.established = true;
    } else return invalid;
    if (failure_) { (void)close(slot, true); return failure_; }
    return 0;
}
i64 lwip_stack::status(u32 slot, u32& flags) {
#ifdef XOS_LWIP_DHCP_AUTHORITY
    if (advance_dhcp()) return failure_;
    if (!gate_open_) return closed;
#endif
    auto& item = connections_[slot]; flags = 0;
    if (item.error) { flags = failed; return item.error; }
    if (!item.tcp && !item.udp && !(item.established && item.ended)) return closed;
    flags = item.established ? connected : connecting;
    if (item.ended) flags |= eof;
    return 0;
}
i64 lwip_stack::send(u32 slot, const u8* data, u32 length) {
#ifdef XOS_LWIP_DHCP_AUTHORITY
    if (advance_dhcp()) return failure_;
    if (!gate_open_) return closed;
#endif
    auto& item = connections_[slot];
    if (length > payload_bytes || (length && !data)) return invalid;
    if (item.error) return item.error;
    if (item.write_closed) return closed;
    if (item.udp) {
        auto* packet = pbuf_alloc(PBUF_TRANSPORT, static_cast<u16_t>(length), PBUF_RAM);
        if (!packet) return would_block;
        const err_t copied = pbuf_take(packet, data, static_cast<u16_t>(length));
        const err_t result = copied == ERR_OK ? udp_send(item.udp, packet) : copied;
        pbuf_free(packet); return result == ERR_OK ? length : map_error(result);
    }
    if (!item.tcp) return closed;
    if (!item.established) return would_block;
    if (!length) return 0;
    u32 count = tcp_sndbuf(item.tcp); if (count > length) count = length;
    if (!count) return would_block;
    const err_t result = tcp_write(item.tcp, data, static_cast<u16_t>(count), TCP_WRITE_FLAG_COPY);
    if (result != ERR_OK) return map_error(result);
    // Data is already admitted. A transient output failure must not invite replay.
    (void)tcp_output(item.tcp); return count;
}
i64 lwip_stack::receive(u32 slot, u8* data, u32 capacity, u32& length, u32& flags) {
#ifdef XOS_LWIP_DHCP_AUTHORITY
    if (advance_dhcp()) return failure_;
    if (!gate_open_) return closed;
#endif
    auto& item = connections_[slot]; length = flags = 0;
    if (!capacity || capacity > payload_bytes || !data) return invalid;
    if (item.udp) {
        if (!item.count) return would_block;
        const u16 count = item.datagram_lengths[item.head];
        if (capacity < count) { flags = count; return buffer_too_small; }
        for (u32 i = 0; i < count; ++i) data[i] = item.data[item.head * payload_bytes + i];
        item.head = (item.head + 1) % udp_queue_limit; --item.count; length = count; return 0;
    }
    if (item.read_closed) { flags = eof; return 0; }
    if (item.count) {
        const u32 count = item.count < capacity ? item.count : capacity;
        for (u32 i = 0; i < count; ++i) data[i] = item.data[(item.head + i) % tcp_receive_bytes];
        item.head = (item.head + count) % tcp_receive_bytes; item.count -= count;
        if (item.tcp) tcp_recved(item.tcp, static_cast<u16_t>(count));
        length = count; if (item.ended && !item.count && !item.error) flags = eof; return 0;
    }
    if (item.error) return item.error;
    if (item.ended) { flags = eof; return 0; }
    if (!item.tcp) return closed;
    return would_block;
}
i64 lwip_stack::readiness(u32 slot, readiness_snapshot& snapshot) {
#ifdef XOS_LWIP_DHCP_AUTHORITY
    if (advance_dhcp()) return failure_;
    if (!gate_open_) return closed;
#endif
    auto& item = connections_[slot];
    if (item.udp) return unsupported;
    readiness_snapshot current{};
    current.error = item.error;
    current.readable_bytes = item.count;
    if (item.count || item.read_closed || (item.ended && !item.error)) current.events |= ready_read;
    if ((item.ended || item.read_closed) && !item.error) current.events |= ready_eof;
    if (item.read_closed) current.events |= ready_read_closed;
    if (item.error) current.events |= ready_error;
    if (item.write_closed) current.events |= ready_write_closed;
    if (item.tcp && !item.established) current.events |= ready_connecting;
    if (item.tcp && item.established && !item.write_closed && !item.error &&
        tcp_sndqueuelen(item.tcp) < TCP_SND_QUEUELEN) {
        current.writable_bytes = tcp_sndbuf(item.tcp);
        if (current.writable_bytes) current.events |= ready_write;
    }
    const auto& old = item.ready;
    const bool changed = !old.generation || old.events != current.events || old.error != current.error ||
        old.readable_bytes != current.readable_bytes || old.writable_bytes != current.writable_bytes;
    if (changed && old.generation == ~u64{0}) return resources;
    current.generation = old.generation + (changed ? 1 : 0);
    item.ready = current;
    snapshot = current;
    return 0;
}
i64 lwip_stack::shutdown_read(u32 slot) {
#ifdef XOS_LWIP_DHCP_AUTHORITY
    if (advance_dhcp()) return failure_;
    if (!gate_open_) return closed;
#endif
    auto& item = connections_[slot];
    if (item.udp) return unsupported;
    if (item.error) return item.error;
    if (item.read_closed) return 0;
    if (!item.established) return item.tcp ? would_block : closed;
    if (!item.tcp && !item.ended) return closed;
    // SHUT_RD is local receive discard. A clean FIN can retire the PCB after
    // the write-half RPC but before SHUT_RDWR reaches this RPC; the owned
    // established description and buffered receive bytes remain valid.
    if (item.count && item.tcp) tcp_recved(item.tcp, static_cast<u16_t>(item.count));
    item.head = item.count = 0; item.read_closed = true;
    return 0;
}
i64 lwip_stack::shutdown_write(u32 slot) {
#ifdef XOS_LWIP_DHCP_AUTHORITY
    if (advance_dhcp()) return failure_;
    if (!gate_open_) return closed;
#endif
    auto& item = connections_[slot];
    if (item.udp) return unsupported;
    if (item.error) return item.error;
    if (item.write_closed) return 0;
    if (!item.tcp) return closed;
    if (!item.established) return would_block;
    const auto result = tcp_shutdown(item.tcp, 0, 1);
    if (result != ERR_OK) return map_error(result);
    item.write_closed = true;
    return 0;
}
i64 lwip_stack::close(u32 slot, bool aborting) {
    auto& item = connections_[slot];
    if (item.udp) udp_remove(item.udp);
    if (item.tcp) {
        auto* pcb = item.tcp;
        // tcp_close sends RST when data has not been acknowledged through
        // tcp_recved, discarding queued output as well. Keep ownership and
        // the complete receive path intact until the application drains it.
        if (!aborting && (item.count || pcb->refused_data || pcb->rcv_wnd != TCP_WND_MAX(pcb))) return would_block;
        tcp_arg(pcb, nullptr); tcp_recv(pcb, nullptr); tcp_err(pcb, nullptr);
        if (aborting) tcp_abort(pcb);
        else {
            const err_t result = tcp_close(pcb);
            if (result != ERR_OK) {
                tcp_arg(pcb, &item); tcp_recv(pcb, on_receive); tcp_err(pcb, on_error);
                return map_error(result);
            }
            // In pinned 2.2.1, FIN allocation pressure sets TF_CLOSEPEND and
            // returns ERR_OK: lwIP retries from its timer and owns the PCB.
            // No callback may retain the application slot after this point.
        }
    }
    item = {}; return 0;
}
stack_api lwip_stack::api() {
    return {this,
        [](void* self, u32 slot, protocol transport, u32 address, u16 port, u64 deadline) {
            return static_cast<lwip_stack*>(self)->open(slot, transport, address, port, deadline); },
        [](void* self, u32 slot, u32& flags) { return static_cast<lwip_stack*>(self)->status(slot, flags); },
        [](void* self, u32 slot, const u8* data, u32 length) { return static_cast<lwip_stack*>(self)->send(slot, data, length); },
        [](void* self, u32 slot, u8* data, u32 capacity, u32& length, u32& flags) {
            return static_cast<lwip_stack*>(self)->receive(slot, data, capacity, length, flags); },
        [](void* self, u32 slot, bool aborting) { return static_cast<lwip_stack*>(self)->close(slot, aborting); },
        [](void* self) { return static_cast<lwip_stack*>(self)->dropped_; },
        [](void* self, u32 slot, readiness_snapshot& snapshot) {
            return static_cast<lwip_stack*>(self)->readiness(slot, snapshot); },
        [](void* self, u32 slot) { return static_cast<lwip_stack*>(self)->shutdown_write(slot); },
#ifdef XOS_LWIP_DHCP_AUTHORITY
        [](void* self, lease_snapshot& value) { return static_cast<lwip_stack*>(self)->lease_status(value); }
#else
        nullptr
#endif
        , [](void* self, u32 slot) { return static_cast<lwip_stack*>(self)->shutdown_read(slot); }
    };
}

#ifdef XOS_LWIP_DNS_LIFETIME
void lwip_stack::configure_dns(u32 address) {
    dns_xos_reset();
    for (auto& subscription : subscriptions_) subscription = {};
    if (address) {
        ip_addr_t resolver{};
        IP_ADDR4(&resolver, address >> 24, (address >> 16) & 0xff,
                 (address >> 8) & 0xff, address & 0xff);
        dns_setserver(0, &resolver);
    }
}

void lwip_stack::on_dns_found(const char* name, const ip_addr_t* address, void* context) {
    if (!active_stack) return;
    const u64 token = reinterpret_cast<uintptr_t>(context);
    for (auto& subscription : active_stack->subscriptions_) {
        if (subscription.token != token) continue;
        const auto callback = subscription;
        subscription = {};
        uint64_t expiry = 0;
        i64 result = dns_failure;
        switch (dns_xos_callback_status(name, &expiry)) {
        case DNS_XOS_SUCCESS: result = address ? 0 : io; break;
        case DNS_XOS_TIMEOUT: result = timeout; break;
        case DNS_XOS_NOT_FOUND: result = name_not_found; break;
        case DNS_XOS_NO_DATA: result = name_no_data; break;
        case DNS_XOS_REFUSED: result = dns_refused; break;
        case DNS_XOS_TRUNCATED: result = dns_truncated; break;
        case DNS_XOS_FAILURE: break;
        }
        const auto now = active_stack->monotonic_time();
        callback.callback(callback.owner, token, now < 0 ? io : result,
                          address ? lwip_ntohl(ip4_addr_get_u32(ip_2_ip4(address))) : 0,
                          expiry, now < 0 ? 0 : static_cast<u64>(now));
        return;
    }
}

i64 lwip_stack::resolve_name(const char* name, u64 token, resolver_completion callback, void* owner) {
#ifdef XOS_LWIP_DHCP_AUTHORITY
    if (advance_dhcp()) return failure_;
    if (!gate_open_) return closed;
#endif
    if (!active_ || failure_) return failure_ ? failure_ : closed;
    for (auto& subscription : subscriptions_) {
        if (subscription.token) continue;
        subscription = {token, callback, owner};
        void* context = reinterpret_cast<void*>(static_cast<uintptr_t>(token));
        ip_addr_t cached{};
        const auto result = dns_gethostbyname(name, &cached, on_dns_found, context);
        if (result == ERR_INPROGRESS) return 0;
        subscription = {};
        if (result != ERR_OK) return result == ERR_MEM ? resources : map_error(result);
        uint64_t expiry = 0;
        const auto details = dns_xos_cache_expiry(name, &expiry);
        const i64 now = monotonic_time();
        if (now < 0 || details == ERR_IF) return io;
        if (details || expiry <= static_cast<u64>(now)) return dns_expired;
        callback(owner, token, 0, lwip_ntohl(ip4_addr_get_u32(ip_2_ip4(&cached))), expiry, static_cast<u64>(now));
        return 0;
    }
    return resources;
}

void lwip_stack::cancel_dns(u64 token) {
    for (auto& subscription : subscriptions_) {
        if (subscription.token != token) continue;
        (void)dns_xos_cancel(on_dns_found, reinterpret_cast<void*>(static_cast<uintptr_t>(token)));
        subscription = {};
        return;
    }
}
#endif

resolver_api lwip_stack::dns_api() {
#ifdef XOS_LWIP_DNS_LIFETIME
    return {this,
        [](void* self, u32 address) { static_cast<lwip_stack*>(self)->configure_dns(address); },
        [](void* self, const char* name, u64 token, resolver_completion callback, void* owner) {
            return static_cast<lwip_stack*>(self)->resolve_name(name, token, callback, owner); },
        [](void* self, u64 token) { static_cast<lwip_stack*>(self)->cancel_dns(token); }};
#else
    return {};
#endif
}
}
