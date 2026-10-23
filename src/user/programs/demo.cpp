#include <xos/sdk.hpp>
namespace {
volatile xos::u64 zeros[1024];
volatile xos::u64 data = 0x584f53;
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    using namespace xos::sdk;
    if (startup == nullptr || startup->magic != startup_magic || startup->version != 1 ||
        startup->size != sizeof(startup_info) || startup->handle_count != 3) { return 91; }
    for (u32 i = 0; i < 1024; ++i) { if (zeros[i] != 0) { return 92; } }
    if (data != 0x584f53) { return 93; }
    zeros[1000] = 123;
    print("[demo] bss=zero data=valid argc="); decimal(startup->argc); print("\n");
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    for (u32 i = 0; i < startup->argc; ++i) {
        print("arg["); decimal(i); print("]="); print(argv[i]); print("\n");
    }
    print("[demo] stderr=valid\n", startup->handles[2]);
    if (write(99, "x", 1) != -1 || close(1) != 0 || write(1, "x", 1) != -1 || close(1) != -1) {
        return 94;
    }
    if (syscall(sys_process_create, 7) != process_error_denied) { return 95; }
    if (syscall(1, reinterpret_cast<u64>("x"), 1) != -1 ||
        syscall(sys_image_info, 1, 0) != -1 || syscall(sys_process_wait, 7, 0) != -2) { return 96; }
    print("[demo] handles=checked create=denied\n", 2);
    return 42;
}
