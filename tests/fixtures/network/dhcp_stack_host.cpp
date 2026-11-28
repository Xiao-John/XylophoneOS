// SPDX-License-Identifier: Apache-2.0
// Production lwIP DHCP/ACD, strict parser, lease gate and service core. Only the
// Ethernet device, monotonic clock and kernel entropy boundary are fixtures.
#include "network/lwip_stack.hpp"
#include <array>
#include <vector>
#include <deque>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <algorithm>
extern "C" {
#include "lwip/dns.h"
}
namespace {
using namespace xos;
using namespace xos::net2;
using namespace xos::user::network;
using bytes = std::vector<u8>;
constexpr u32 server1 = 0x0a000202, server2 = 0x0a000203, address1 = 0x0a00020f, address2 = 0x0a000210;
constexpr u64 second = 1'000'000'000ull;
constexpr std::array<u8, 6> mac{0x52,0x54,0,0x12,0x34,0x56}, peer_mac{0x52,0x54,0,0x65,0x43,0x21};
void expect(bool value, const char* why, int line = __builtin_LINE()) {
    if (!value) { std::fprintf(stderr,"line %d: %s\n",line,why); std::abort(); }
}
u16 r16(const u8* p) { return (static_cast<u16>(p[0]) << 8) | p[1]; }
u32 r32(const u8* p) { return (static_cast<u32>(r16(p)) << 16) | r16(p+2); }
void w16(u8* p,u16 n) { p[0]=n>>8;p[1]=n; }
void w32(u8* p,u32 n) { w16(p,n>>16);w16(p+2,n); }
u16 checksum(const u8* p,usize n,u32 sum=0) {
    for (usize i=0;i+1<n;i+=2) sum+=r16(p+i);
    if (n&1) sum+=static_cast<u32>(p[n-1])<<8;
    while (sum>>16) sum=(sum&65535)+(sum>>16);
    return static_cast<u16>(~sum);
}
struct peer {
    std::deque<bytes> input;
    std::vector<bytes> requests;
    std::vector<u64> request_times;
    bytes last_request, last_discover;
    u64 now=second;
    u32 random=0x9712ab41, issuer=server1, offered=address1, lease=40, t1=16,t2=28;
    u32 declines=0, discovers=0, app_frames=0, probes=0;
    bool offer=true, ack=true, arp=true, conflict=false, blocked=false, fail_random=false;
    bool two_resolvers=false, reverse_resolvers=false;
    bool link_up=true;
    bytes ethernet(u16 type,usize n) {
        bytes frame(14+n);std::copy(mac.begin(),mac.end(),frame.begin());
        std::copy(peer_mac.begin(),peer_mac.end(),frame.begin()+6);w16(frame.data()+12,type);return frame;
    }
    void udp(u32 from,u16 source,u16 target,const bytes& payload,u32 destination=0xffffffff) {
        auto frame=ethernet(0x800,28+payload.size());auto* ip=frame.data()+14;
        ip[0]=0x45;w16(ip+2,28+payload.size());ip[8]=64;ip[9]=17;
        w32(ip+12,from);w32(ip+16,destination);w16(ip+10,checksum(ip,20));
        auto* packet=ip+20;w16(packet,source);w16(packet+2,target);w16(packet+4,8+payload.size());
        std::copy(payload.begin(),payload.end(),packet+8);
        const u32 sum=(from>>16)+(from&65535)+(destination>>16)+(destination&65535)+17+8+payload.size();
        w16(packet+6,checksum(packet,8+payload.size(),sum));input.push_back(std::move(frame));
    }
    void arp_reply(u32 from,u32 target) {
        auto frame=ethernet(0x806,28);auto* p=frame.data()+14;
        w16(p,1);w16(p+2,0x800);p[4]=6;p[5]=4;w16(p+6,2);
        std::copy(peer_mac.begin(),peer_mac.end(),p+8);w32(p+14,from);
        std::copy(mac.begin(),mac.end(),p+18);w32(p+24,target);input.push_back(std::move(frame));
    }
    bytes reply(const bytes& request,u8 type) {
        bytes value(240);value[0]=2;value[1]=1;value[2]=6;
        std::copy(request.begin()+4,request.begin()+8,value.begin()+4);
        if (type!=6) w32(value.data()+16,offered);
        std::copy(mac.begin(),mac.end(),value.begin()+28);w32(value.data()+236,0x63825363);
        value.insert(value.end(),{53,1,type});
        auto option=[&](u8 code,u32 number) {value.push_back(code);value.push_back(4);usize n=value.size();value.resize(n+4);w32(value.data()+n,number);};
        option(54,issuer);
        if(type!=6) {
            option(1,0xffffff00);option(3,server1);
            if(two_resolvers) {
                value.insert(value.end(),{6,8});const auto offset=value.size();value.resize(offset+8);
                w32(value.data()+offset,reverse_resolvers?server2:server1);
                w32(value.data()+offset+4,reverse_resolvers?server1:server2);
            } else option(6,server1);
            option(51,lease);option(58,t1);option(59,t2);
        }
        value.push_back(255);return value;
    }
    void answer(u8 type=5) {udp(issuer,67,68,reply(last_request,type));}
    void observe(const u8* frame,u32 size) {
        if(size<42) return;
        if(r16(frame+12)==0x806) {
            const auto* p=frame+14;
            if(r16(p+6)==1 && r32(p+14)==0 && r32(p+24)==offered) {
                ++probes;if(conflict) {conflict=false;arp_reply(offered,0);}
            } else if(r16(p+6)==1 && arp && (r32(p+24)==server1 || r32(p+24)==server2)) arp_reply(r32(p+24),r32(p+14));
            return;
        }
        if(r16(frame+12)!=0x800 || frame[23]!=17) {++app_frames;return;}
        const auto* ip=frame+14;const u32 ihl=(ip[0]&15)*4;const auto* u=ip+ihl;
        if(r16(u)!=68 || r16(u+2)!=67) {++app_frames;return;}
        const auto* p=u+8;const u32 length=r16(u+4)-8;
        expect(length>=241,"DHCP request body");u8 type=0;
        for(u32 i=240;i<length;) {u8 code=p[i++];if(code==255)break;if(!code)continue;u8 n=p[i++];if(code==53&&n==1)type=p[i];i+=n;}
        bytes request(p,p+length);
        if(type==1) {last_discover=request;++discovers;if(offer)udp(issuer,67,68,reply(request,2));}
        else if(type==3) {last_request=request;requests.push_back(request);request_times.push_back(now);if(ack)answer();}
        else if(type==4) ++declines;
    }
    frame_io io() {
        return {this,
            [](void* p,u8* out,u32 capacity)->i64 {auto& self=*static_cast<peer*>(p);if(self.input.empty())return 0;auto frame=std::move(self.input.front());self.input.pop_front();expect(frame.size()<=capacity,"RX capacity");std::memcpy(out,frame.data(),frame.size());return frame.size();},
            [](void* p,const u8* frame,u32 size)->i64 {auto& self=*static_cast<peer*>(p);if(self.blocked)return would_block;self.observe(frame,size);return 0;},
            [](void* p)->i64 {return static_cast<peer*>(p)->now;},
            [](void* p,u32& out)->i64 {auto& self=*static_cast<peer*>(p);if(self.fail_random)return xos::net2::io;self.random^=self.random<<13;self.random^=self.random>>17;self.random^=self.random<<5;out=self.random;return 0;},
            [](void* p)->i64 {return static_cast<peer*>(p)->link_up?1:0;}};
    }
};
struct environment {
    peer wire;lwip_stack stack;service_core core;u32 publications=0;
    udp_pcb* blockers[12]{};
    environment(bool initially_blocked=false, bool udp_pressure=false, bool initially_down=false) {
        wire.blocked=initially_blocked;
        wire.link_up=!initially_down;
        expect(!stack.initialize(wire.io(),mac.data()),"stack initialize");
        core.initialize(100,stack.api(),stack.dns_api());core.enable_dhcp();
        if(udp_pressure) for(auto& item:blockers) {item=udp_new();expect(item!=nullptr,"occupy real UDP PCB pool");}
        const dhcp::policy policy{0x0a000200,0xffffff00,address1,address2,{server1,server2},2,{server1,server2},2,{server1,server2},2,0xfffffffe};
        expect(!stack.start_dhcp(policy,60*second,[](void* context,u32 ip,u32 mask,u32 gateway,u32 dns,u32 secondary) {
            auto& self=*static_cast<environment*>(context);++self.publications;return self.core.publish_dhcp(ip,mask,gateway,dns,secondary);
        },this),"start DHCP");
    }
    void release_pressure(){for(auto& item:blockers) if(item){udp_remove(item);item=nullptr;}}
    ~environment(){release_pressure();core.shutdown();stack.shutdown();}
    void poll(){expect(!stack.poll(),"production poll");}
    void until(u64 target){while(wire.now<target){wire.now=std::min<u64>(target,wire.now+100'000'000ull);poll();}}
    lease_snapshot snapshot(){lease_snapshot out{};expect(!stack.lease_status(out),"lease status");return out;}
    void bound(){poll();until(11*second);expect(snapshot().address==wire.offered,"ACD published lease");}
};
void run(const std::string& scenario) {
    environment e(scenario=="initial_discover_backpressure" || scenario=="initial_discover_budget",
                  scenario=="initial_udp_pcb_pressure" || scenario=="initial_udp_pcb_budget",
                  scenario=="initial_link_down");
    e.wire.two_resolvers=scenario=="multiple_resolvers";
    if(scenario=="initial_link_down") {
        e.until(80*second);expect(!e.wire.discovers && !e.snapshot().address && e.snapshot().reason==3,
                                 "initial link down never publishes or spends an acquisition budget");
        e.wire.link_up=true;e.poll();e.until(e.wire.now+12*second);
        expect(e.snapshot().address==address1 && e.wire.probes>=3 && e.publications==1,
               "first link appearance starts fresh bounded DHCP and ACD");
    } else if(scenario=="initial_discover_backpressure" || scenario=="initial_udp_pcb_pressure") {
        const bool allocation=scenario=="initial_udp_pcb_pressure";
        expect(e.snapshot().start_attempts==1 && e.snapshot().start_failures==u32(allocation),"startup pressure classified correctly");
        e.until(1'400'000'000ull);expect(e.snapshot().start_attempts==1,"no busy restart loop");
        e.wire.blocked=false;e.release_pressure();e.until(14*second);
        expect(e.snapshot().address==address1 && e.snapshot().start_attempts==(allocation?2u:1u) &&
               e.snapshot().start_failures==u32(allocation),"bounded startup retry recovers");
    } else if(scenario=="initial_discover_budget" || scenario=="initial_udp_pcb_budget") {
        const bool allocation=scenario=="initial_udp_pcb_budget";
        e.until(62*second);auto value=e.snapshot();
        expect(!value.address && value.reason==6 && value.start_attempts<=120 &&
               value.start_failures==(allocation?value.start_attempts:0u),"permanent pressure consumes original budget only");
        e.wire.blocked=false;e.release_pressure();e.until(80*second);
        expect(e.snapshot().start_attempts==value.start_attempts && !e.snapshot().address,"no retry after absolute acquisition timeout");
    } else if(scenario=="no_static_fallback") {
        e.wire.input.clear();e.wire.offer=false;e.until(62*second);const auto value=e.snapshot();
        expect(!value.address && value.reason==6 && !e.publications,"acquisition timeout without fallback");
        const auto count=e.wire.discovers;e.until(80*second);expect(count==e.wire.discovers,"absolute retry budget");
    } else if(scenario=="acd_conflict" || scenario=="conflict_backoff_recover") {
        e.wire.conflict=true;e.poll();e.until(9*second);
        expect(!e.snapshot().address && e.wire.declines==1 && !e.publications,"conflicting candidate never published");
        if(scenario=="conflict_backoff_recover") {e.until(30*second);expect(e.snapshot().address==address1 && e.snapshot().conflicts==1,"backoff discover accepts fresh issuer context");}
    } else if(scenario=="request_tx_anchor") {
        e.wire.ack=false;e.poll();expect(e.wire.requests.size()==1,"actual request sent");
        e.until(4*second);e.wire.answer();e.poll();e.until(12*second);auto value=e.snapshot();
        expect(value.address && value.request_sent==e.wire.request_times.front() && value.expires==value.request_sent+40*second,"ACK and retransmission never extend original request anchor");
    } else if(scenario=="malformed_reply") {
        e.wire.ack=false;e.poll();auto malformed=e.wire.reply(e.wire.last_request,5);malformed.pop_back();malformed.insert(malformed.end(),{53,1,5,255});
        e.wire.udp(server1,67,68,malformed);e.poll();expect(!e.snapshot().address && e.snapshot().rejected==1,"duplicate option blocked before upstream");
        e.wire.answer();e.poll();e.until(11*second);expect(e.snapshot().address==address1,"valid reply after malformed accepted");
    } else if(scenario=="untransmitted_request") {
        e.wire.blocked=true;e.poll();expect(e.wire.requests.empty(),"blocked REQUEST has no TX authority");
        // A forged ACK with the OFFER XID still has no successful request anchor.
        e.wire.last_request=e.wire.last_discover;e.wire.answer();e.poll();
        expect(e.snapshot().rejected==1,"ACK without real REQUEST transmission rejected");
        e.until(62*second);expect(!e.snapshot().address,"no bind without a transmitted request");
    } else {
        e.bound();auto initial=e.snapshot();const auto epoch=e.publications;
        if(scenario=="link_loss_reacquire") {
            const auto slot=e.core.attach(200,e.wire.now);expect(slot>=0,"old application session");
            e.wire.arp=false;auto api=e.stack.api();
            expect(!api.open(api.context,0,protocol::udp,server2,3333,e.wire.now+second),"old UDP socket");
            const u8 payload[]{4,5,6};expect(api.send(api.context,0,payload,sizeof(payload))==3,"queued old ARP payload");
            expect(!api.open(api.context,1,protocol::tcp,server2,3333,e.wire.now+20*second),"old pending TCP socket");
            e.wire.link_up=false;e.poll();
            expect(!e.snapshot().address && e.snapshot().reason==3 && !e.core.alive(slot) &&
                   e.publications==epoch+1,"link loss immediately retires lease/session epoch");
            const auto frames=e.wire.app_frames,discoveries=e.wire.discovers,probes=e.wire.probes;
            e.wire.arp_reply(server2,address1);e.poll();e.until(e.wire.now+70*second);
            expect(e.wire.discovers==discoveries && e.wire.app_frames==frames,"down link has no retry or deferred packet revival");
            e.wire.offered=address2;e.wire.arp=true;e.wire.link_up=true;e.poll();e.until(e.wire.now+12*second);
            u32 flags=0;
            expect(e.snapshot().address==address2 && e.publications==epoch+2 && e.wire.probes>=probes+3 &&
                   e.wire.app_frames==frames && api.send(api.context,0,payload,sizeof(payload))==closed &&
                   api.status(api.context,1,flags)==closed,
                   "reappearance reacquires with ACD; old UDP/TCP and ARP stay retired");
        } else if(scenario=="multiple_resolvers") {
            expect(lwip_ntohl(ip4_addr_get_u32(ip_2_ip4(dns_getserver(0))))==server1 &&
                   lwip_ntohl(ip4_addr_get_u32(ip_2_ip4(dns_getserver(1))))==server2,
                   "approved DHCP option 6 configures both resolver endpoints");
            const auto slot=e.core.attach(200,e.wire.now);expect(slot>=0,"application session before resolver change");
            e.wire.reverse_resolvers=true;e.until(initial.t1+second);
            expect(e.publications==epoch+1 && !e.core.alive(slot) &&
                   lwip_ntohl(ip4_addr_get_u32(ip_2_ip4(dns_getserver(0))))==server2 &&
                   lwip_ntohl(ip4_addr_get_u32(ip_2_ip4(dns_getserver(1))))==server1,
                   "resolver order change retires application epoch and replaces both endpoints");
        } else if(scenario=="arp_deferred_request_anchor") {
            e.wire.arp=false;e.wire.ack=false;e.until(initial.t1+2*second);
            expect(e.wire.requests.size()==1,"ARP queuing did not count as REQUEST transmit");
            e.wire.arp_reply(server1,address1);e.poll();const auto transmitted=e.wire.now;
            e.until(transmitted+second);e.wire.answer();e.poll();
            expect(e.snapshot().request_sent==transmitted,"only resolved link_output starts renewal clock");
        } else if(scenario=="renew") {
            e.until(initial.t1+second);auto value=e.snapshot();
            expect(value.address==address1 && value.expires>initial.expires && e.publications==epoch,"unchanged renewal retains epoch");
            expect(r32(e.wire.requests.front().data()+4)!=r32(e.wire.requests.back().data()+4),"renewal uses fresh XID");
        } else if(scenario=="expire" || scenario=="queued_arp_retirement") {
            e.wire.ack=e.wire.offer=false;
            const auto slot=e.core.attach(200,e.wire.now);expect(slot>=0,"application session");
            if(scenario=="queued_arp_retirement") {
                e.wire.arp=false;auto api=e.stack.api();expect(!api.open(api.context,0,protocol::udp,server2,3333,e.wire.now+second),"UDP open");
                const u8 payload[]={1,2,3};expect(api.send(api.context,0,payload,sizeof(payload))==3,"queued ARP payload");
            }
            e.until(initial.expires);expect(!e.snapshot().address && !e.core.alive(slot) && e.publications==epoch+1,"expiry retires application generation");
            const auto frames=e.wire.app_frames;e.wire.arp_reply(server2,address1);e.poll();expect(e.wire.app_frames==frames,"retired ARP queue cannot transmit");
        } else if(scenario=="nak_config_change") {
            e.wire.ack=false;e.until(initial.t1+second);e.wire.answer(6);e.wire.offered=address2;e.wire.ack=true;e.poll();
            expect(!e.snapshot().address,"NAK immediately closes old epoch");e.until(e.wire.now+12*second);
            expect(e.snapshot().address==address2 && e.publications==epoch+2,"bounded reacquisition publishes new address");
        } else if(scenario=="rebind_new_issuer") {
            e.wire.ack=false;e.until(initial.t1+second);const auto xid=r32(e.wire.last_request.data()+4);const auto sent=e.wire.request_times.back();
            e.until(initial.t2+100'000'000ull);expect(r32(e.wire.last_request.data()+4)==xid,"T2 retains transaction XID");
            e.wire.issuer=server2;e.wire.answer();e.poll();auto value=e.snapshot();
            expect(value.server==server2 && value.request_sent==sent && e.publications==epoch,"rebind issuer update without epoch or timestamp extension");
        } else if(scenario=="max_finite_lease") {
            e.wire.lease=0xfffffffe;e.wire.t1=0x7fffffff;e.wire.t2=0xdffffffe;
            e.until(initial.t1+second);auto value=e.snapshot();
            expect(value.expires-value.request_sent==0xfffffffeull*second && value.t1<value.t2 && value.t2<value.expires,"maximum finite lease arithmetic");
        } else if(scenario=="clock_regression") {
            e.wire.now=initial.request_sent-1;expect(e.stack.advance_dhcp()==io,"clock regression fails closed");
            expect(e.publications==epoch+1,"clock failure retires epoch");
        } else expect(false,"unknown scenario");
    }
}
}
int main(int argc,char** argv) {
    const char* cases[]={"renew","expire","nak_config_change","rebind_new_issuer","malformed_reply","acd_conflict","conflict_backoff_recover","request_tx_anchor","queued_arp_retirement","no_static_fallback","untransmitted_request","max_finite_lease","arp_deferred_request_anchor","initial_discover_backpressure","initial_discover_budget","initial_udp_pcb_pressure","initial_udp_pcb_budget","clock_regression","multiple_resolvers","initial_link_down","link_loss_reacquire"};
    if(argc==2 && std::string(argv[1])=="--list") {for(auto value:cases)std::puts(value);return 0;}
    expect(argc==2,"one scenario");run(argv[1]);std::printf("DHCP_PRODUCTION_PASS %s\n",argv[1]);
}
