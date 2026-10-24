// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/file_client.hpp>
namespace {
using namespace xos;
// Loaded from disk, never embedded in the kernel. Volatile forces real reads.
volatile const u8 payload[262144] = {90};
u8 bss_probe[2*1024*1024];
file::Client client;
u8 chunk[3000];
int failure(u32 stage) {
    sdk::print("[e08] FAILED stage="); sdk::decimal(stage); sdk::print("\n"); return 1;
}
}
extern "C" int xos_user_main(const xos::startup_info* start) {
    using namespace xos;
    if(payload[0]!=90 || payload[262143]!=0 || bss_probe[0]!=0 || bss_probe[sizeof(bss_probe)-1]!=0) return failure(1);
    for(u32 i=0;i<sizeof(bss_probe);i+=4096) bss_probe[i]=static_cast<u8>(i/4096);
    if(!client.init()) return failure(2);
    file_session_info forbidden{};
    u64 sectors=0;
    if(sdk::syscall(sys_file_session,0,reinterpret_cast<u64>(&forbidden))!=process_error_denied ||
       sdk::syscall(sys_block_info,reinterpret_cast<u64>(&sectors))!=block_error_denied ||
       sdk::ipc_send(2,chunk,1)>=0 || sdk::ipc_recv(3,chunk,1)>=0 || client.read(1,chunk,1)>=0) return failure(17);
    const auto* argv=reinterpret_cast<const char* const*>(start->argv);
    const bool bench = start->argc>1 && sdk::equal(argv[1],"bench");
    const bool abandon = start->argc>1 && sdk::equal(argv[1],"abandon");
    const bool verify = start->argc>1 && sdk::equal(argv[1],"verify");
    u32 h=0,size=0,version=0;
    if(client.open("/src/long_source_name.txt",file::read_only,h,size,version)!=0) return failure(3);
    if(client.read(h,chunk,1)!=1 || chunk[0]!='X') return failure(4);
    // Deliberately leave an open and uncommitted disk staging when killed.
    if(abandon) {
        if(client.begin_replace("/out/abandoned_source.txt",6000)!=0 || client.chunk_replace(0,chunk,1)!=0) return failure(5);
        sdk::print("[e08] abandoned-ready\n");
        for(;;) sdk::yield();
    }
    u32 denied_handle=0,denied_size=0,denied_version=0;
    if(client.open("/src/long_source_name.txt",file::write_only,denied_handle,denied_size,denied_version)>=0 ||
       client.replace("/src/long_source_name.txt","bad",3)>=0 || client.close(h)!=0) return failure(6);
    if(bench) {
        sdk::print("[e08] ata-start\n");
        if(client.block_bench(8*1024*1024)!=8*1024*1024) return failure(18);
        sdk::print("[e08] ata-done\n");
        if(client.open("/src/throughput_payload.bin",file::read_only,h,size,version)!=0) return failure(7);
        sdk::print("[e08] bench-start bytes="); sdk::decimal(size); sdk::print("\n");
        u32 total=0; u32 hash=2166136261u;
        for(;;) {
            const i64 n=client.read(h,chunk,sizeof(chunk)); if(n<0) return failure(8); if(n==0) break;
            for(u32 i=0;i<static_cast<u32>(n);++i) hash=(hash^chunk[i])*16777619u;
            total+=static_cast<u32>(n);
        }
        if(total!=size || client.close(h)!=0) return failure(9);
        sdk::print("[e08] bench-done bytes="); sdk::decimal(total); sdk::print(" hash="); sdk::decimal(hash); sdk::print("\n");
        return 0;
    }
    if(!verify) {
        const i64 directory=client.mkdir("/out/guest_directory");
        if(directory!=0 && directory!=static_cast<i64>(file::status::busy)) return failure(19);
        if(client.replace("/out/guest_directory/two words.txt","kept",4)!=0 ||
           client.rename("/out/guest_directory/two words.txt","/out/guest_directory/renamed_source.txt")!=0) return failure(20);
        file::entry entries[2]{};u32 count=0,cursor=0;
        if(client.list("/out/guest_directory",entries,2,count,cursor)!=0 || count!=1 ||
           !sdk::equal(entries[0].name,"renamed_source.txt") ||
           client.remove("/out/guest_directory/renamed_source.txt")!=0 ||
           client.remove("/out/guest_directory")!=0) return failure(21);
        if(client.replace("/src/../bad","x",1)>=0 || client.replace("/out/trailing.","x",1)>=0) return failure(22);

        if(client.begin_replace("/out/long_result_name.txt",262144)!=0) return failure(10);
        for(u32 offset=0;offset<262144;) {
            const u32 n=262144-offset>sizeof(chunk)?static_cast<u32>(sizeof(chunk)):262144-offset;
            for(u32 i=0;i<n;++i) chunk[i]=static_cast<u8>((offset+i)*17u+3u);
            if(client.chunk_replace(offset,chunk,n)!=0) return failure(11);
            offset+=n;
        }
        if(client.commit_replace()!=0) return failure(12);
    }
    const i64 reopened=client.open("/out/long_result_name.txt",file::read_only,h,size,version);
    if(reopened!=0 || size!=262144) {
        sdk::print("[e08] reopen error=");sdk::signed_decimal(reopened);sdk::print(" size=");sdk::decimal(size);sdk::print("\n");return failure(13);
    }
    u32 position=0;
    for(;;) {
        const i64 n=client.read(h,chunk,sizeof(chunk)); if(n<0) return failure(14); if(n==0) break;
        for(u32 i=0;i<static_cast<u32>(n);++i) if(chunk[i]!=static_cast<u8>((position+i)*17u+3u)) return failure(15);
        position+=static_cast<u32>(n);
    }
    if(position!=size || client.close(h)!=0 || client.read(h,chunk,1)>=0 || client.sync()!=0) return failure(16);
    sdk::print("[e08] large-elf bss=ok path=ok stream=262144 sync=ok\n");
    return 0;
}
