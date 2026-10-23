#include <xos/sdk.hpp>
extern "C" void provoke_user_fault(xos::u32 kind);
extern "C" int xos_user_main(const xos::startup_info* info) {
    xos::u32 kind = 0;
    if (info->argc > 1) {
        const auto* argv = reinterpret_cast<const char* const*>(info->argv);
        if (xos::sdk::equal(argv[1], "readonly")) { kind = 1; }
        if (xos::sdk::equal(argv[1], "nx")) { kind = 2; }
        if (xos::sdk::equal(argv[1], "fpu")) { kind = 3; }
    }
    xos::sdk::print("[fault] testing protected memory\n");
    provoke_user_fault(kind);
    return 99;
}
