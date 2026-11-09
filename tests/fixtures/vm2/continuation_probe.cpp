// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
using namespace xos;
using namespace xos::sdk;
struct request { u32 version,size,operation,flags; u64 address,length,alignment; u32 protection,reserved0; u64 reserved1,reserved2; };
extern "C" int xos_user_main(const startup_info* info) {
    request r{1,64,0xfffe,0,4096,0,0,0,0,0,0};
    const auto argv=reinterpret_cast<const char* const*>(info->argv);
    const bool failure=info->argc>1 && equal(argv[1],"fail");
    if (info->argc>1 && equal(argv[1],"child")) {
        const char* child_argv[]={"spin"};
        const auto child=spawn_file("/bin/spin.elf",1,child_argv);
        if (child<=0) return 2;
        print("VM2_CHILD_PID="); decimal(static_cast<u64>(child)); print("\n");
    }
    if (failure) { r.address=128; r.flags=1; r.length=48; }
    const i64 before=syscall(sys_clock_monotonic,0);
    print("VM2_PROBE_START\n");
    const i64 result=syscall(67,reinterpret_cast<u64>(&r));
    const i64 after=syscall(sys_clock_monotonic,0);
    if (result != (failure ? -5 : 0) || after <= before) { print("VM2_PROBE_FAIL\n"); return 1; }
    print("VM2_PROBE_COMPLETE\n"); return 0;
}
