// SPDX-License-Identifier: Apache-2.0
#include <xos/dynamic.hpp>
#include <xos/file_client.hpp>
#include <xos/sdk.hpp>
#include "image_reader.hpp"
#include "fixture.hpp"
using namespace xos;
extern "C" void run_admission_cases();
static u32 checks, failures;
extern "C" void admission_check(const char* name, bool passed) {
    ++checks;
    if (!passed) ++failures;
    sdk::print(passed ? "D3_ADMISSION_PASS " : "D3_ADMISSION_FAIL ");
    sdk::print(name); sdk::print("\n");
}
extern "C" int xos_user_main(const startup_info*) {
    run_admission_cases();
    file::client files;
    u32 handle = 0, size = 0, version = 0;
    bool pin = files.init() && files.open("/bin/identity.so", file::read_only | file::open_pin,
                                        handle, size, version) == 0;
    if (pin) {
        loader::opened_file source{&files, handle, size, loader::file_read_mode::positioned};
        pin = files.seek(handle, 73) == 73 && size == fixture_object.file_bytes
            && dynamic::verify_object(loader::file_read, &source, fixture_object) == dynamic::error::none
            && files.seek(handle, 0, file::seek_current) == 73;
        pin = files.close(handle) == 0 && pin;
    }
    admission_check("same_native_file_pin_and_cursor", pin);
    sdk::print(failures ? "D3_ADMISSION_REJECTED checks=" : "D3_ADMISSION_OK checks=");
    sdk::decimal(checks); sdk::print("\n");
    return failures ? 65 : 0;
}
