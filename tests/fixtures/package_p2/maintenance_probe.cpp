// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/file_client.hpp>
using namespace xos;
namespace {
file::Client files;
int bad(int code) { sdk::print("P2_PROBE_FAIL=");sdk::decimal(static_cast<u64>(code));sdk::print("\n");return code; }
}
extern "C" int xos_user_main(const startup_info* startup) {
    const char* const* argv=reinterpret_cast<const char* const*>(startup->argv);
    const char* mode=startup->argc>1?argv[1]:"normal";
    if (!files.init())return bad(1);
    if (sdk::equal(mode,"background")) {sdk::print("P2_BACKGROUND\n");for(;;)sdk::yield();}
    process_guard_info gate{};
    if (sdk::syscall(sys_process_guard,static_cast<u64>(process_guard_action::query),reinterpret_cast<u64>(&gate)))return bad(2);
    if (sdk::syscall(sys_process_guard,static_cast<u64>(process_guard_action::begin))!=process_error_denied)return bad(3);
    if (sdk::syscall(sys_process_guard,static_cast<u64>(process_guard_action::end))!=process_error_denied)return bad(4);
    if (sdk::syscall(sys_process_guard,static_cast<u64>(process_guard_action::query),1)!=process_error_invalid)return bad(5);
    if (sdk::equal(mode,"normal")) {
        if(gate.owner_pid||gate.worker_pid)return bad(6);
        if(files.maintenance_acquire()!=static_cast<i64>(file::status::busy))return bad(7);
        if(files.maintenance_release()!=static_cast<i64>(file::status::invalid))return bad(8);
        if(files.replace("/out/p2_normal.txt","normal",6))return bad(9);
        sdk::print("P2_NORMAL denied_controls writes_ok\n");return 0;
    }
    if (!gate.owner_pid||gate.worker_pid!=sdk::pid())return bad(10);
    if(files.replace("/out/p2_without_lease.txt","bad",3)!=static_cast<i64>(file::status::busy))return bad(11);
    if(files.maintenance_acquire())return bad(12);
    if(files.maintenance_acquire()!=static_cast<i64>(file::status::busy))return bad(13);
    if(files.maintenance_release()!=static_cast<i64>(file::status::invalid))return bad(14);
    if(sdk::syscall(sys_process_create,7)!=process_error_busy)return bad(15);
    if(sdk::syscall(sys_process_grant,0,1)!=process_error_denied)return bad(16);
    if(sdk::syscall(sys_process_delegate,0,1)!=process_error_denied)return bad(17);
    const char* value=sdk::equal(mode,"recover")?"recovered":"worker";
    if(files.replace("/out/p2_worker.txt",value,static_cast<u32>(sdk::length(value))))return bad(18);
    if(files.sync())return bad(19);
    sdk::print("P2_WORKER lease_ok spawn_denied\n");
    if(sdk::equal(mode,"spin"))for(;;)sdk::yield();
    if(sdk::equal(mode,"fault"))__builtin_trap();
    if(sdk::equal(mode,"fail"))return 7;
    sdk::print(sdk::equal(mode,"recover")?"P2_RECOVERED\n":"P2_SUCCESS\n");return 0;
}
