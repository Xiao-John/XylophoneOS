// SPDX-License-Identifier: Apache-2.0
// Exercise the locked upstream resolver through real Ethernet/IP/UDP parsing.
// This is an audit of disabled functionality, not a production DNS profile.
#include "network/lwip_stack.hpp"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <vector>
extern "C" {
#include "lwip/dns.h"
}

namespace {
using namespace xos;
using namespace xos::user::network;
using bytes = std::vector<u8>;
constexpr u32 local_address = 0x0a00020f, server_address = 0x0a000202;
constexpr std::array<u8, 6> local_mac{0x52, 0x54, 0x00, 0x12, 0x34, 0x56};
constexpr std::array<u8, 6> peer_mac{0x52, 0x54, 0x00, 0x65, 0x43, 0x21};
void check(bool value, const char* reason) {
    if (!value) { std::fprintf(stderr, "audit fixture: %s\n", reason); std::abort(); }
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
    u64 now = 1'000'000'000ull;
    u32 random_state = 0x9712ab41, failed_draws = 0;
    bool entropy_failed = false;
    bytes ethernet(u16 type, usize body_length) {
        bytes frame(14 + body_length);
        std::copy(local_mac.begin(), local_mac.end(), frame.begin());
        std::copy(peer_mac.begin(), peer_mac.end(), frame.begin() + 6);
        write16(frame.data() + 12, type);
        return frame;
    }
    void observe(const u8* frame, u32 length) {
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
                u16 destination_port = 0, u32 source_address = server_address) {
        auto frame = ethernet(0x0800, 28 + payload.size());
        auto* ip = frame.data() + 14;
        ip[0] = 0x45; write16(ip + 2, static_cast<u16>(28 + payload.size()));
        ip[8] = 64; ip[9] = 17;
        write32(ip + 12, source_address); write32(ip + 16, local_address);
        write16(ip + 10, checksum(ip, 20));
        auto* udp = ip + 20;
        const auto size = static_cast<u16>(8 + payload.size());
        write16(udp, source_port); write16(udp + 2, destination_port ? destination_port : question.port);
        write16(udp + 4, size);
        std::copy(payload.begin(), payload.end(), udp + 8);
        const u16 sum = checksum(udp, size, pseudo_sum(source_address, local_address, size));
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
                if (self.entropy_failed) {
                    if (++self.failed_draws == 4096) {
                        std::puts("AUDIT entropy_failure repeated_draws=4096 operation_returned=0");
                        std::fflush(stdout);
                        std::_Exit(42); // Fixture work budget; production call has not returned.
                    }
                    return net2::io;
                }
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
bytes response(const packet_peer::query& query, bool other_owner = false, u32 ttl = 2) {
    auto data = query.payload;
    check(data.size() > 16 && read16(data.data() + 4) == 1, "one DNS question");
    data[2] = 0x81; data[3] = 0x80; write16(data.data() + 6, 1);
    if (other_owner) {
        const u8 name[]{5,'o','t','h','e','r',2,'n','4',4,'t','e','s','t',0};
        data.insert(data.end(), std::begin(name), std::end(name));
    } else { data.push_back(0xc0); data.push_back(0x0c); }
    const auto offset = data.size(); data.resize(offset + 14);
    write16(data.data() + offset, 1); write16(data.data() + offset + 2, 1);
    write32(data.data() + offset + 4, ttl); write16(data.data() + offset + 8, 4);
    write32(data.data() + offset + 10, server_address);
    return data;
}
}

int main(int argc, char** argv) {
    check(argc == 2, "one scenario argument");
    const char* scenario = argv[1];
    packet_peer peer;
    lwip_stack stack;
    check(stack.initialize(peer.callbacks(), local_mac.data()) == 0, "actual stack initialize");
    ip_addr_t server;
    IP_ADDR4(&server, 10, 0, 2, 2); dns_setserver(0, &server);
    resolution first{}, second{};
    ip_addr_t immediate{};
    if (!std::strcmp(scenario, "entropy_failure")) peer.entropy_failed = true;
    check(dns_gethostbyname("first.n4.test", &immediate, found, &first) == ERR_INPROGRESS,
          "query enqueued");
    check(stack.poll() == 0 && peer.queries.size() == 1, "real outbound DNS packet");
    const auto question = peer.queries[0];
    const bool other_port = !std::strcmp(scenario, "other_query_port");
    if (other_port) {
        check(dns_gethostbyname("second.n4.test", &immediate, found, &second) == ERR_INPROGRESS,
              "second query enqueued");
        check(stack.poll() == 0 && peer.queries.size() == 2, "second query packet");
        check(peer.queries[1].port != question.port, "independent query port");
    }
    auto answer = response(question, !std::strcmp(scenario, "unrelated_owner"));
    if (!std::strcmp(scenario, "truncated")) answer[2] |= 2;
    if (!std::strcmp(scenario, "other_opcode")) answer[2] |= 8;
    if (!std::strcmp(scenario, "wrong_id")) answer[1] ^= 1;
    if (!std::strcmp(scenario, "wrong_question")) answer[13] = 'x';
    peer.answer(question, answer, !std::strcmp(scenario, "wrong_source_port") ? 5353 : 53,
                other_port ? peer.queries[1].port : 0,
                !std::strcmp(scenario, "wrong_source_address") ? 0x0a000263 : server_address);
    check(stack.poll() == 0, "actual IPv4/UDP resolver receive");
    if (!std::strcmp(scenario, "ttl_pause")) {
        check(first.calls == 1, "initial TTL answer accepted");
        peer.now += 3'000'000'000ull; // Exceed the 2-second TTL without timer servicing.
        check(stack.poll() == 0, "poll after monotonic pause");
        const err_t result = dns_gethostbyname("first.n4.test", &immediate, found, &second);
        std::printf("AUDIT ttl_pause original_ttl_seconds=2 elapsed_seconds=3 cached=%u\n", result == ERR_OK);
    } else if (!std::strcmp(scenario, "server_change")) {
        check(first.calls == 1, "initial answer accepted");
        IP_ADDR4(&server, 10, 0, 2, 3); dns_setserver(0, &server);
        const err_t result = dns_gethostbyname("first.n4.test", &immediate, found, &second);
        std::printf("AUDIT server_change cached_previous_server=%u\n", result == ERR_OK);
    } else {
        std::printf("AUDIT %s accepted=%u callback_count=%u address=%08x\n", scenario,
                    first.address == server_address, first.calls, first.address);
    }
    stack.shutdown();
    return 0;
}
