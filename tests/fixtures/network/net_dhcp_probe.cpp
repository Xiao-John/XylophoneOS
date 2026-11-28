// SPDX-License-Identifier: Apache-2.0
#include <xos/net_transport.hpp>
#include <xos/text.hpp>
namespace {
using namespace xos;
using namespace xos::net2;
constexpr u64 second=1'000'000'000ull;
void check(bool valid,const char* what,i64 result=0) {
    if(valid)return;
    sdk::print("DHCP_GUEST_FAIL ");sdk::print(what);sdk::print(" result=");sdk::signed_decimal(result);sdk::print("\n");sdk::exit(90);
}
u64 now(){const i64 value=sdk::syscall(sys_clock_monotonic);check(value>=0,"clock",value);return value;}
void pause(){check(!sdk::syscall(sys_sleep_until,now()+20'000'000ull),"sleep");}
u64 number(const char* text){u64 value=0;check(*text,"number");while(*text){check(*text>='0'&&*text<='9',"number digit");value=value*10+*text++-'0';}return value;}
void print_snapshot(const char* marker,const lease_snapshot& value) {
    sdk::print(marker);sdk::print(" epoch=");sdk::decimal(value.epoch);sdk::print(" state=");sdk::decimal(value.state);
    sdk::print(" address=");sdk::decimal(value.address);sdk::print(" server=");sdk::decimal(value.server);
    sdk::print(" request=");sdk::decimal(value.request_sent);sdk::print(" t1=");sdk::decimal(value.t1);
    sdk::print(" t2=");sdk::decimal(value.t2);sdk::print(" expiry=");sdk::decimal(value.expires);
    sdk::print(" reason=");sdk::decimal(value.reason);sdk::print(" rejected=");sdk::decimal(value.rejected);
    sdk::print(" conflicts=");sdk::decimal(value.conflicts);
    sdk::print(" starts=");sdk::decimal(value.start_attempts);sdk::print(" start_failures=");sdk::decimal(value.start_failures);sdk::print("\n");
}
i64 open(session_client& client,u64& handle) {
    message request{},reply{};request.action=operation::open;request.address=0x0a000202;
    request.transport=protocol::udp;request.port=3333;request.deadline=now()+second;
    const auto status=client.request(request,reply);handle=reply.object;return status;
}
void challenge(session_client& client,u64 handle,const char* nonce) {
    message request{},reply{};request.action=operation::send;request.object=handle;
    request.deadline=now()+second;request.length=32;__builtin_memcpy(request.data,nonce,32);
    check(client.request(request,reply)==32,"UDP nonce");
    const auto deadline=now()+5*second;
    for(;;){request={};request.action=operation::receive;request.object=handle;request.flags=32;request.deadline=now()+second;
        const auto status=client.request(request,reply);if(!status){check(reply.length==32,"challenge length");break;}
        check(status==would_block&&now()<deadline,"challenge wait",status);pause();}
    char hex[65]{};constexpr char digits[]="0123456789abcdef";
    for(u32 i=0;i<32;++i){hex[i*2]=digits[reply.data[i]>>4];hex[i*2+1]=digits[reply.data[i]&15];}
    sdk::print("DHCP_GUEST_CHALLENGE data=");sdk::print(hex);sdk::print("\n");
}
lease_snapshot snapshot(session_client& client,u64 pid,u32& closures) {
    lease_snapshot value{};
    for(u32 attempt=0;attempt<3;++attempt){const auto result=client.lease_status(now()+second,value);
        if(!result)return value;
        check(result==closed,"snapshot RPC",result);++closures;client.close();
        check(!client.connect(pid),"read-only reconnect");}
    check(false,"repeated config churn");return {};
}
void link_epoch(session_client& client,u64 pid,const lease_snapshot& initial,u64 initial_handle,
                const char* nonce,u32& closures) {
    message request{},reply{};
    request.action=operation::close;request.object=initial_handle;request.deadline=now()+second;
    check(!client.request(request,reply),"close initial challenge connection");
    u64 handles[2]{};
    for(u32 i=0;i<2;++i){
        request={};request.action=operation::open;request.address=0x0a000203;request.port=4444;
        request.transport=i?protocol::tcp:protocol::udp;request.deadline=now()+second;
        check(!client.request(request,reply)&&reply.object,"old queued connection");handles[i]=reply.object;
    }
    request={};request.action=operation::send;request.object=handles[0];request.length=32;
    request.deadline=now()+second;__builtin_memcpy(request.data,nonce,32);
    check(client.request(request,reply)==32,"queued UDP behind unresolved ARP");
    u64 ticket=0;check(!client.resolve_start("pending.dhcp.test",17,now()+30*second,ticket)&&ticket,"old DNS ticket");
    sdk::print("DHCP_LINK_READY_QUEUED\n");
    const auto prior_closures=closures;
    const auto deadline=now()+30*second;
    lease_snapshot down{};
    for(;;){down=snapshot(client,pid,closures);if(!down.address&&down.reason==3)break;
        check(now()<deadline,"link-down deadline");pause();}
    check(down.epoch==initial.epoch+1&&closures>prior_closures,"link loss retires application epoch");
    u64 denied=0;check(open(client,denied)==closed&&!denied,"link-down new traffic denied");
    for(const auto handle:handles){request={};request.action=operation::status;request.object=handle;request.deadline=now()+second;
        check(client.request(request,reply)==closed,"old connection closed while link down");}
    resolve_reply answer{};check(client.resolve_result(ticket,now()+second,answer)==closed,"old DNS closed while link down");
    print_snapshot("DHCP_LINK_DOWN",down);sdk::print("DHCP_LINK_DOWN_READY\n");
    lease_snapshot fresh{};
    for(;;){fresh=snapshot(client,pid,closures);if(fresh.address)break;
        check(now()<deadline,"link-up reacquisition deadline");pause();}
    check(fresh.address==0x0a000210&&fresh.epoch==initial.epoch+2&&fresh.request_sent>initial.request_sent&&
          fresh.start_attempts>initial.start_attempts,"fresh lease after link up");
    for(const auto handle:handles){request={};request.action=operation::status;request.object=handle;request.deadline=now()+second;
        check(client.request(request,reply)==closed,"old connection cannot resurrect");}
    check(client.resolve_result(ticket,now()+second,answer)==closed,"old ticket cannot resurrect");
    print_snapshot("DHCP_LINK_UP",fresh);sdk::print("DHCP_LINK_UP_BOUND\n");
    check(!sdk::syscall(sys_sleep_until,now()+500'000'000ull),"late ARP injection interval");
    u64 current=0;check(!open(client,current),"fresh application connection");challenge(client,current,nonce);
    sdk::print("DHCP_GUEST_PASS link_loss\n");
}
void device_epoch(session_client& client,u64 pid,u64 initial_handle,const char* nonce) {
    message request{},reply{};
    request.action=operation::close;request.object=initial_handle;request.deadline=now()+second;
    check(!client.request(request,reply),"close device initial challenge");
    u64 udp=0;
    for(u32 i=0;i<2;++i){request={};request.action=operation::open;request.address=0x0a000203;
        request.port=4444;request.transport=i?protocol::tcp:protocol::udp;request.deadline=now()+second;
        check(!client.request(request,reply)&&reply.object,"device old queued transport");
        if(!i)udp=reply.object;}
    request={};request.action=operation::send;request.object=udp;request.length=32;
    request.deadline=now()+second;__builtin_memcpy(request.data,nonce,32);
    check(client.request(request,reply)==32,"device queued UDP behind ARP");
    u64 ticket=0;check(!client.resolve_start("pending.dhcp.test",17,now()+30*second,ticket)&&ticket,
                       "device old DNS ticket");
    sdk::print("DHCP_DEVICE_READY_QUEUED\n");const auto deadline=now()+35*second;
    for(;;){lease_snapshot value{};const auto result=client.lease_status(now()+second,value);
        if(result==closed)break;
        check(!result&&now()<deadline,"device old service closure",result);pause();}
    sdk::print("DHCP_DEVICE_OLD_CLOSED\n");
    // Keep the original caller alive until the replacement publishes its
    // name. A new endpoint cannot satisfy the authenticated old PID binding.
    for(;;){pause();const auto result=client.connect(pid);
        if(result==denied)break;
        check(result==closed&&now()<deadline,"replacement rejects old service identity",result);}
    sdk::print("DHCP_GUEST_PASS device_old_identity\n");
}
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;using namespace xos::net2;
    check(startup->argc==4,"usage");const auto* args=reinterpret_cast<const char*const*>(startup->argv);
    const char* mode=args[1];const auto pid=number(args[2]);check(sdk::length(args[3])==32,"nonce");
    if(sdk::equal(mode,"dns") || sdk::equal(mode,"dns_closed")) {
        xos::net2::client resolver;check(!resolver.connect(pid),"resolver transport connect");
        char name[64]="live-";__builtin_memcpy(name+5,args[3],32);__builtin_memcpy(name+37,".dhcp.test",11);
        resolve_reply answer{};const auto result=resolver.resolve_ipv4(name,47,now()+4*second,answer);
        if(sdk::equal(mode,"dns_closed")) check(result==closed&&!answer.address,"unconfigured DHCP resolver closed",result);
        else {
            check(!result&&answer.address==0x0a000202&&answer.epoch&&answer.expiry>now(),"native DHCP hostname resolution",result);
            sdk::print("DHCP_GUEST_DNS epoch=");sdk::decimal(answer.epoch);sdk::print(" address=");sdk::decimal(answer.address);sdk::print("\n");
        }
        sdk::print("DHCP_GUEST_PASS ");sdk::print(mode);sdk::print("\n");return 0;
    }
    session_client client;check(!client.connect(pid),"connect");u32 closures=0;
    lease_snapshot initial{};const auto acquisition=now()+55*second;
    for(;;){initial=snapshot(client,pid,closures);
        config_snapshot config{};const auto result=client.configuration(now()+second,config);
        if(result==closed){client.close();check(!client.connect(pid),"configuration reconnect");++closures;continue;}
        check(!result&&config.mode==network_mode::dhcp,"DHCP installation",result);
        check(config.epoch==initial.epoch&&config.address==initial.address,"coherent snapshot");
        if(sdk::equal(mode,"acd_conflict")&&initial.conflicts){check(!initial.address,"conflict never published");
            u64 denied_handle=0;check(open(client,denied_handle)==closed&&!denied_handle,"no static fallback");
            print_snapshot("DHCP_GUEST_FINAL",initial);sdk::print("DHCP_GUEST_PASS acd_conflict\n");return 0;}
        if(initial.address)break;
        check(!config.mask&&!config.gateway&&!config.resolver,"zero unconfigured tuple");
        check(now()<acquisition,"acquisition deadline");pause();}
    check(initial.address==0x0a00020f&&initial.server==0x0a000202,"initial admitted tuple");
    if(sdk::equal(mode,"malformed"))check(initial.rejected>=3,"strict malformed rejection");
    if(sdk::equal(mode,"conflict_backoff_recover"))check(initial.conflicts>=1,"conflict history");
    print_snapshot("DHCP_GUEST_BOUND",initial);
    u64 handle=0;check(!open(client,handle)&&handle,"UDP open");challenge(client,handle,args[3]);
    if(sdk::equal(mode,"link_loss")){link_epoch(client,pid,initial,handle,args[3],closures);return 0;}
    if(sdk::equal(mode,"device_old")){device_epoch(client,pid,handle,args[3]);return 0;}
    if(sdk::equal(mode,"bound")||sdk::equal(mode,"malformed")||sdk::equal(mode,"conflict_backoff_recover")) {
        sdk::print("DHCP_GUEST_PASS ");sdk::print(mode);sdk::print("\n");return 0;}
    if(sdk::equal(mode,"restart_old")) {
        sdk::print("DHCP_GUEST_RESTART_READY\n");const auto deadline=now()+20*second;
        for(;;){lease_snapshot value{};const auto result=client.lease_status(now()+second,value);
            if(result==closed) break;
            check(!result&&now()<deadline,"old service wait",result);pause();}
        const auto reconnect=client.connect(pid);
        check(reconnect==closed||reconnect==denied,"old PID cannot authenticate replacement");
        sdk::print("DHCP_GUEST_PASS restart_old\n");return 0;}
    u64 ticket=0;
    if(sdk::equal(mode,"expire")||sdk::equal(mode,"nak_config_change"))
        check(!client.resolve_start("pending.dhcp.test",17,now()+30*second,ticket)&&ticket,"pending resolver ticket");
    const u32 prior_closures=closures;
    const auto deadline=now()+50*second;
    lease_snapshot current{};
    for(;;){current=snapshot(client,pid,closures);
        if(sdk::equal(mode,"renew")&&current.expires>initial.expires){
            check(current.epoch==initial.epoch&&current.address==initial.address&&current.request_sent>initial.request_sent,"renewal clock and stable epoch");break;}
        if(sdk::equal(mode,"rebind_new_issuer")&&current.server==0x0a000203){
            check(current.epoch==initial.epoch&&current.request_sent>initial.request_sent,"rebind keeps configuration epoch");break;}
        if(sdk::equal(mode,"expire")&&!current.address&&current.reason==5){
            check(current.epoch==initial.epoch+1&&closures>prior_closures,"expiry closes old application transport");break;}
        if(sdk::equal(mode,"nak_config_change")&&current.address==0x0a000210){
            check(current.epoch==initial.epoch+2&&current.reason==1&&closures>prior_closures,"NAK retires then replaces epoch");break;}
        check(now()<deadline,"lifecycle deadline");pause();}
    if(ticket){message request{},reply{};request.action=operation::status;request.object=handle;request.deadline=now()+second;
        check(client.request(request,reply)==closed,"old connection retired");resolve_reply answer{};
        check(client.resolve_result(ticket,now()+second,answer)==closed,"old resolver ticket retired");
        sdk::print("DHCP_GUEST_OLD_RESOURCES_CLOSED\n");
        if(current.address){check(!open(client,handle),"new epoch UDP open");challenge(client,handle,args[3]);}}
    print_snapshot("DHCP_GUEST_FINAL",current);sdk::print("DHCP_GUEST_PASS ");sdk::print(mode);sdk::print("\n");return 0;
}
