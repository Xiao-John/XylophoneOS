// SPDX-License-Identifier: Apache-2.0
// Exercise the locked upstream resolver through real Ethernet/IP/UDP parsing.
// Test-only DNS enablement; production DNS/DHCP remain disabled.
#include "network/lwip_stack.hpp"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <set>
#include <vector>
extern "C" {
#include "lwip/dns.h"
#include "lwip/udp.h"
}

namespace {
using namespace xos;
using namespace xos::user::network;
using bytes = std::vector<u8>;
constexpr u32 local_address = 0x0a00020f, server_address = 0x0a000202;
constexpr std::array<u8, 6> local_mac{0x52, 0x54, 0x00, 0x12, 0x34, 0x56};
constexpr std::array<u8, 6> peer_mac{0x52, 0x54, 0x00, 0x65, 0x43, 0x21};
void check(bool value, const char* reason) {
    if (!value) { std::fprintf(stderr, "DNS hardening fixture: %s\n", reason); std::abort(); }
}
u16 read16(const u8* value) { return static_cast<u16>((value[0] << 8) | value[1]); }
u32 read32(const u8* value) {
    return (static_cast<u32>(value[0]) << 24) | (static_cast<u32>(value[1]) << 16)
        | (static_cast<u32>(value[2]) << 8) | value[3];
}
void write16(u8* value, u16 number) { value[0] = number >> 8; value[1] = number; }
void write32(u8* value, u32 number) {
    value[0] = number >> 24; value[1] = number >> 16; value[2] = number >> 8; value[3] = number;
}
u16 checksum(const u8* data, usize length, u32 sum = 0) {
    for (usize i = 0; i + 1 < length; i += 2) sum += read16(data + i);
    if (length & 1) sum += static_cast<u32>(data[length - 1]) << 8;
    while (sum >> 16) sum = (sum & 65535) + (sum >> 16);
    return static_cast<u16>(~sum);
}
u32 pseudo_sum(u32 from, u32 to, u16 length) {
    return (from >> 16) + (from & 65535) + (to >> 16) + (to & 65535) + 17 + length;
}
struct packet_peer {
    struct query { u16 port; bytes payload; };
    std::deque<bytes> incoming;
    std::vector<query> queries;
    std::deque<u32> random_script;
    u64 now = 1'000'000'000ull;
    u32 random_state = 0x9712ab41, failed_draws = 0, random_draws = 0, transmitted = 0;
    i32 entropy_successes_left = -1;
    bool constant_random = false;
    u32 random_constant = 0;
    bytes ethernet(u16 type, usize body_length) {
        bytes frame(14 + body_length);
        std::copy(local_mac.begin(), local_mac.end(), frame.begin());
        std::copy(peer_mac.begin(), peer_mac.end(), frame.begin() + 6);
        write16(frame.data() + 12, type);
        return frame;
    }
    void observe(const u8* frame, u32 length) {
        ++transmitted;
        check(length >= 14, "Ethernet header");
        if (read16(frame + 12) == 0x0806) {
            check(length >= 42, "ARP header");
            if (read16(frame + 20) != 1) return;
            auto reply = ethernet(0x0806, 28);
            auto* arp = reply.data() + 14;
            write16(arp, 1); write16(arp + 2, 0x0800); arp[4] = 6; arp[5] = 4;
            write16(arp + 6, 2);
            std::copy(peer_mac.begin(), peer_mac.end(), arp + 8);
            write32(arp + 14, read32(frame + 38));
            std::copy(local_mac.begin(), local_mac.end(), arp + 18);
            write32(arp + 24, local_address);
            incoming.push_back(std::move(reply));
            return;
        }
        if (read16(frame + 12) != 0x0800) return;
        check(length >= 34, "IPv4 header");
        const auto* ip = frame + 14;
        const u32 header = (ip[0] & 15) * 4, total = read16(ip + 2);
        check(header >= 20 && total >= header && length >= 14 + total, "IPv4 bounds");
        check(checksum(ip, header) == 0, "IPv4 checksum");
        if (ip[9] != 17) return;
        const auto* udp = ip + header;
        const auto size = static_cast<u16>(total - header);
        check(size >= 8 && read16(udp + 4) == size, "UDP bounds");
        check(checksum(udp, size, pseudo_sum(read32(ip + 12), read32(ip + 16), size)) == 0,
              "UDP checksum");
        check(read16(udp + 2) == 53, "resolver destination port");
        queries.push_back({read16(udp), bytes(udp + 8, udp + size)});
    }
    void answer(const query& question, const bytes& payload, u16 source_port = 53,
                u16 destination_port = 0, u32 source_address = server_address,
                u32 destination_address = local_address) {
        auto frame = ethernet(0x0800, 28 + payload.size());
        auto* ip = frame.data() + 14;
        ip[0] = 0x45; write16(ip + 2, static_cast<u16>(28 + payload.size()));
        ip[8] = 64; ip[9] = 17;
        write32(ip + 12, source_address); write32(ip + 16, destination_address);
        write16(ip + 10, checksum(ip, 20));
        auto* udp = ip + 20;
        const auto size = static_cast<u16>(8 + payload.size());
        write16(udp, source_port); write16(udp + 2, destination_port ? destination_port : question.port);
        write16(udp + 4, size);
        std::copy(payload.begin(), payload.end(), udp + 8);
        const u16 sum = checksum(udp, size, pseudo_sum(source_address, destination_address, size));
        write16(udp + 6, sum ? sum : 65535);
        incoming.push_back(std::move(frame));
    }
    frame_io callbacks() {
        return {this,
            [](void* context, u8* data, u32 capacity) -> i64 {
                auto& self = *static_cast<packet_peer*>(context);
                if (self.incoming.empty()) return 0;
                auto frame = std::move(self.incoming.front()); self.incoming.pop_front();
                check(frame.size() <= capacity, "fixture frame capacity");
                std::copy(frame.begin(), frame.end(), data);
                return static_cast<i64>(frame.size());
            },
            [](void* context, const u8* data, u32 size) -> i64 {
                static_cast<packet_peer*>(context)->observe(data, size); return 0;
            },
            [](void* context) -> i64 { return static_cast<i64>(static_cast<packet_peer*>(context)->now); },
            [](void* context, u32& value) -> i64 {
                auto& self = *static_cast<packet_peer*>(context);
                check(++self.random_draws < 1024, "finite entropy work budget");
                if (self.entropy_successes_left == 0) {
                    ++self.failed_draws;
                    return net2::io;
                }
                if (self.entropy_successes_left > 0) --self.entropy_successes_left;
                if (!self.random_script.empty()) {
                    value = self.random_script.front(); self.random_script.pop_front();
                    return 0;
                }
                if (self.constant_random) { value = self.random_constant; return 0; }
                self.random_state ^= self.random_state << 13;
                self.random_state ^= self.random_state >> 17;
                self.random_state ^= self.random_state << 5;
                value = self.random_state;
                return 0;
            }};
    }
};
struct resolution { u32 calls = 0, address = 0; };
void found(const char*, const ip_addr_t* address, void* context) {
    auto& result = *static_cast<resolution*>(context);
    ++result.calls;
    if (address) result.address = lwip_ntohl(ip4_addr_get_u32(ip_2_ip4(address)));
}
bytes encoded_name(const char* name) {
    bytes result;
    while (*name) {
        const char* end = std::strchr(name, '.');
        const usize length = end ? static_cast<usize>(end - name) : std::strlen(name);
        check(length > 0 && length <= 63, "fixture DNS label length");
        result.push_back(static_cast<u8>(length));
        result.insert(result.end(), name, name + length);
        name += length;
        if (*name) ++name;
    }
    result.push_back(0);
    return result;
}
void address_record(bytes& data, const bytes& owner, u32 address = server_address) {
    data.insert(data.end(), owner.begin(), owner.end());
    const auto offset = data.size(); data.resize(offset + 14);
    write16(data.data() + offset, 1); write16(data.data() + offset + 2, 1);
    write32(data.data() + offset + 4, 30); write16(data.data() + offset + 8, 4);
    write32(data.data() + offset + 10, address);
}
bytes response(const packet_peer::query& query, const bytes& owner = {0xc0, 0x0c}) {
    auto data = query.payload;
    check(data.size() > 16 && read16(data.data() + 4) == 1, "one DNS question");
    data[2] = 0x81; data[3] = 0x80; write16(data.data() + 6, 1);
    address_record(data, owner);
    return data;
}
void check_pool(usize expected) {
    std::vector<udp_pcb*> pcbs;
    while (auto* pcb = udp_new_ip_type(IPADDR_TYPE_V4)) pcbs.push_back(pcb);
    check(pcbs.size() == expected, "actual UDP PCB pool ownership");
    for (auto* pcb : pcbs) udp_remove(pcb);
}
packet_peer::query begin(packet_peer& peer, lwip_stack& stack, const char* name, resolution& result) {
    ip_addr_t immediate{};
    const auto previous = peer.queries.size();
    check(dns_gethostbyname(name, &immediate, found, &result) == ERR_INPROGRESS, "query admitted");
    check(stack.poll() == 0 && peer.queries.size() == previous + 1, "real outbound query");
    return peer.queries.back();
}
void complete(packet_peer& peer, lwip_stack& stack, const packet_peer::query& query, resolution& result) {
    peer.answer(query, response(query));
    check(stack.poll() == 0 && result.calls == 1 && result.address == server_address,
          "subsequent valid response completes the original query once");
}
void reply_case(const char* scenario, packet_peer& peer, lwip_stack& stack) {
    resolution first{}, second{};
    const auto question = begin(peer, stack, "first.n4.test", first);
    packet_peer::query other{};
    const bool other_port = !std::strcmp(scenario, "other_query_port");
    if (other_port) {
        other = begin(peer, stack, "second.n4.test", second);
        check(other.port != question.port, "independent receive endpoints");
    }
    auto answer = response(question);
    const auto owner_offset = question.payload.size();
    const auto record_offset = owner_offset + 2;
    const auto is = [scenario](const char* name) { return !std::strcmp(scenario, name); };
    bool positive = is("valid") || is("uncompressed_mixed_case") || is("partial_compression") ||
        is("multiple_direct_answers") || is("compression_depth_16");
    if (is("uncompressed_mixed_case")) answer = response(question, encoded_name("FiRsT.N4.TeSt"));
    if (is("partial_compression")) answer = response(question, {5,'f','i','r','s','t',0xc0,0x12});
    if (is("multiple_direct_answers")) {
        write16(answer.data() + 6, 2); address_record(answer, {0xc0,0x0c}, 0x0a000203);
    }
    if (is("compression_depth_16") || is("compression_depth_17")) {
        const u16 count = is("compression_depth_16") ? 16 : 17;
        write16(answer.data() + 6, count);
        usize previous = owner_offset;
        for (u16 index = 1; index < count; ++index) {
            const usize next = answer.size();
            address_record(answer, {static_cast<u8>(0xc0 | (previous >> 8)), static_cast<u8>(previous)});
            previous = next;
        }
    }
    if (is("unrelated_owner")) answer = response(question, encoded_name("other.n4.test"));
    if (is("truncated")) answer[2] |= 2;
    if (is("other_opcode")) answer[2] |= 8;
    if (is("other_opcode_high")) answer[2] |= 0x40;
    if (is("not_response")) answer[2] &= 0x7f;
    if (is("wrong_id")) answer[1] ^= 1;
    if (is("wrong_question")) answer[13] = 'x';
    if (is("wrong_question_count")) write16(answer.data() + 4, 2);
    if (is("wrong_class")) write16(answer.data() + record_offset + 2, 3);
    if (is("wrong_type")) write16(answer.data() + record_offset, 28);
    if (is("bad_rdata_length")) write16(answer.data() + record_offset + 8, 3);
    if (is("short_rdata")) answer.pop_back();
    if (is("incomplete_answer_section")) write16(answer.data() + 6, 2);
    if (is("reserved_owner_label")) answer[owner_offset] = 0x40;
    if (is("pointer_self")) answer[owner_offset + 1] = static_cast<u8>(owner_offset);
    if (is("pointer_forward")) answer[owner_offset + 1] = static_cast<u8>(owner_offset + 2);
    if (is("pointer_out_of_bounds")) { answer[owner_offset] = 0xff; answer[owner_offset + 1] = 0xff; }
    if (is("pointer_header")) answer[owner_offset + 1] = 0;
    if (is("question_prefix") || is("question_suffix") || is("question_label_boundary")) {
        auto malformed = question;
        malformed.payload.resize(12);
        bytes name = encoded_name(is("question_prefix") ? "first.n4" : "first.n4.test.extra");
        if (is("question_label_boundary")) name = {13,'f','i','r','s','t','.','n','4','.','t','e','s','t',0};
        malformed.payload.insert(malformed.payload.end(), name.begin(), name.end());
        malformed.payload.insert(malformed.payload.end(), {0,1,0,1});
        answer = response(malformed);
    }
    if (is("cname_chain")) {
        answer = question.payload; answer[2] = 0x81; answer[3] = 0x80;
        write16(answer.data() + 6, 2);
        const auto alias = encoded_name("alias.n4.test");
        answer.insert(answer.end(), {0xc0,0x0c,0,5,0,1,0,0,0,30,0,static_cast<u8>(alias.size())});
        answer.insert(answer.end(), alias.begin(), alias.end());
        address_record(answer, alias);
    }
    peer.answer(question, answer, is("wrong_source_port") ? 5353 : 53,
                other_port ? other.port : 0, is("wrong_source_address") ? 0x0a000263 : server_address,
                is("destination_broadcast") ? 0xffffffff : is("destination_subnet_broadcast") ? 0x0a0002ff :
                is("destination_multicast") ? 0xe0000001 : is("destination_other_unicast") ? 0x0a000210 : local_address);
    check(stack.poll() == 0, "real IPv4/UDP receive");
    if (positive) {
        check(first.calls == 1 && first.address == server_address, "valid direct answer accepted once");
    } else {
        check(first.calls == 0 && second.calls == 0, "invalid frame cannot complete either query");
        complete(peer, stack, question, first);
    }
    if (other_port) complete(peer, stack, other, second);
    check_pool(MEMP_NUM_UDP_PCB);
}
void random_case(const char* scenario, packet_peer& peer, lwip_stack& stack) {
    const auto is = [scenario](const char* name) { return !std::strcmp(scenario, name); };
    resolution first{}, second{};
    ip_addr_t immediate{};
    const u32 draws = peer.random_draws, frames = peer.transmitted;
    if (is("entropy_port_failure") || is("entropy_id_failure")) {
        peer.entropy_successes_left = is("entropy_id_failure") ? 1 : 0;
        peer.random_script = {41000};
        check(dns_gethostbyname("first.n4.test", &immediate, found, &first) == ERR_IF,
              "entropy error returned before asynchronous admission");
        check(first.calls == 0 && peer.failed_draws == 1 && peer.queries.empty() && peer.transmitted == frames,
              "failed entropy cannot emit a packet or callback");
        check(peer.random_draws - draws == (is("entropy_id_failure") ? 2u : 1u), "entropy work stops at failure");
        check_pool(MEMP_NUM_UDP_PCB);
        peer.entropy_successes_left = -1;
        check(dns_gethostbyname("second.n4.test", &immediate, found, &second) == ERR_IF,
              "failed stack cannot silently recover from new entropy");
        check(peer.failed_draws == 1 && stack.poll() == net2::io && second.calls == 0,
              "fatal fault is latched without repeated provider calls");
        check_pool(MEMP_NUM_UDP_PCB);
        return;
    }
    if (is("zero_id_valid")) {
        peer.random_script = {41000, 0};
        const auto query = begin(peer, stack, "first.n4.test", first);
        check(read16(query.payload.data()) == 0, "zero is a valid unpredictable ID value");
        complete(peer, stack, query, first); check_pool(MEMP_NUM_UDP_PCB); return;
    }
    if (is("invalid_ports_budget")) {
        peer.constant_random = true; peer.random_constant = 1;
        check(dns_gethostbyname("first.n4.test", &immediate, found, &first) == ERR_USE,
              "invalid source ports exhaust a bounded budget");
        check(peer.random_draws - draws == 32 && peer.transmitted == frames && first.calls == 0,
              "32 failed draws do not send or publish a callback");
        check_pool(MEMP_NUM_UDP_PCB);
        peer.constant_random = false;
        const auto query = begin(peer, stack, "first.n4.test", first);
        complete(peer, stack, query, first); check_pool(MEMP_NUM_UDP_PCB); return;
    }
    peer.random_script = {41000, 0x1234};
    const auto first_query = begin(peer, stack, "first.n4.test", first);
    const u32 previous_draws = peer.random_draws, previous_frames = peer.transmitted;
    peer.constant_random = true;
    peer.random_constant = is("port_collision_budget") ? 41000 : 0x1234;
    if (is("id_collision_budget")) peer.random_script = {41001};
    check(dns_gethostbyname("second.n4.test", &immediate, found, &second) == ERR_USE,
          "collision budget returns an admission error");
    check(peer.random_draws - previous_draws == (is("id_collision_budget") ? 33u : 32u),
          "collision budget has a precise upper bound");
    check(peer.transmitted == previous_frames && first.calls == 0 && second.calls == 0,
          "collision cannot share or invalidate the first query endpoint");
    check_pool(MEMP_NUM_UDP_PCB - 1);
    peer.constant_random = false; peer.random_script = {41001, 0x1235};
    const auto second_query = begin(peer, stack, "second.n4.test", second);
    check(second_query.port == 41001, "failed admission returned its bound UDP port");
    complete(peer, stack, first_query, first); complete(peer, stack, second_query, second);
    check_pool(MEMP_NUM_UDP_PCB);
}
void query_capacity(packet_peer& peer, lwip_stack& stack) {
    resolution results[5]{}; packet_peer::query queries[4];
    const char* names[]{"one.n4.test", "two.n4.test", "three.n4.test", "four.n4.test", "five.n4.test"};
    std::set<u16> ports, ids;
    for (usize i = 0; i < 4; ++i) {
        queries[i] = begin(peer, stack, names[i], results[i]);
        ports.insert(queries[i].port); ids.insert(read16(queries[i].payload.data()));
    }
    check(ports.size() == 4 && ids.size() == 4, "four distinct IDs and endpoints");
    check_pool(MEMP_NUM_UDP_PCB - 4);
    ip_addr_t immediate{};
    const auto draws = peer.random_draws, frames = peer.transmitted;
    check(dns_gethostbyname(names[4], &immediate, found, &results[4]) == ERR_MEM,
          "fifth query rejected at table limit");
    check(results[4].calls == 0 && peer.random_draws == draws && peer.transmitted == frames,
          "capacity refusal has no callback, entropy read, or packet");
    for (usize i = 0; i < 4; ++i) complete(peer, stack, queries[i], results[i]);
    const auto last = begin(peer, stack, names[4], results[4]);
    complete(peer, stack, last, results[4]); check_pool(MEMP_NUM_UDP_PCB);
}
void udp_capacity(packet_peer& peer, lwip_stack& stack) {
    resolution first{}, second{};
    const auto query = begin(peer, stack, "first.n4.test", first);
    std::vector<udp_pcb*> held;
    while (auto* pcb = udp_new_ip_type(IPADDR_TYPE_V4)) held.push_back(pcb);
    check(held.size() == MEMP_NUM_UDP_PCB - 1, "ordinary UDP exhausts the remaining real PCB pool");
    ip_addr_t immediate{};
    const auto draws = peer.random_draws, frames = peer.transmitted;
    check(dns_gethostbyname("second.n4.test", &immediate, found, &second) == ERR_MEM,
          "PCB exhaustion refuses a query without endpoint reuse");
    check(second.calls == 0 && peer.random_draws == draws && peer.transmitted == frames,
          "PCB refusal preserves other query and sends nothing");
    complete(peer, stack, query, first);
    for (auto* pcb : held) udp_remove(pcb);
    const auto next = begin(peer, stack, "second.n4.test", second);
    complete(peer, stack, next, second); check_pool(MEMP_NUM_UDP_PCB);
}
const char* reply_cases[]{"valid", "uncompressed_mixed_case", "partial_compression", "multiple_direct_answers",
    "compression_depth_16", "wrong_id", "wrong_question", "wrong_question_count", "wrong_source_address",
    "wrong_source_port", "other_query_port", "unrelated_owner", "truncated", "other_opcode", "other_opcode_high",
    "not_response", "wrong_class", "wrong_type", "bad_rdata_length", "short_rdata", "incomplete_answer_section",
    "reserved_owner_label", "pointer_self", "pointer_forward", "pointer_out_of_bounds", "pointer_header",
    "question_prefix", "question_suffix", "question_label_boundary", "cname_chain", "compression_depth_17",
    "destination_broadcast", "destination_subnet_broadcast", "destination_multicast", "destination_other_unicast"};
const char* random_cases[]{"entropy_port_failure", "entropy_id_failure", "zero_id_valid", "invalid_ports_budget",
    "port_collision_budget", "id_collision_budget"};
}

int main(int argc, char** argv) {
    check(argc == 2, "one scenario argument");
    if (!std::strcmp(argv[1], "--list")) {
        for (const char* name : reply_cases) std::puts(name);
        for (const char* name : random_cases) std::puts(name);
        std::puts("query_capacity"); std::puts("udp_capacity"); return 0;
    }
    packet_peer peer; lwip_stack stack;
    check(stack.initialize(peer.callbacks(), local_mac.data()) == 0, "production stack initialize");
    ip_addr_t server; IP_ADDR4(&server, 10, 0, 2, 2); dns_setserver(0, &server);
    bool matched = false;
    for (const char* name : reply_cases) if (!std::strcmp(argv[1], name)) {
        reply_case(name, peer, stack); matched = true; break;
    }
    for (const char* name : random_cases) if (!std::strcmp(argv[1], name)) {
        random_case(name, peer, stack); matched = true; break;
    }
    if (!std::strcmp(argv[1], "query_capacity")) { query_capacity(peer, stack); matched = true; }
    if (!std::strcmp(argv[1], "udp_capacity")) { udp_capacity(peer, stack); matched = true; }
    check(matched, "known scenario");
    stack.shutdown();
    std::printf("DNS_HARDENING_CASE_PASS=%s\n", argv[1]);
    return 0;
}
