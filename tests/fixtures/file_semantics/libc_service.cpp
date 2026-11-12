// SPDX-License-Identifier: Apache-2.0
// Production files.cpp/FatFs behind the real SDK's IPC requests. The sole
// substituted boundary is kernel IPC transport and its authenticated PID.
#define xos_file_fixture_external_syscall
#define main file_semantics_unused_main
#include "file_semantics.cpp"
#undef main

extern "C" void identity_service_mount(const char* path) {
    FILE* image = std::fopen(path, "rb");
    require(image != nullptr, "libc image");
    std::fseek(image, 0, SEEK_END);
    original.resize(static_cast<size_t>(std::ftell(image)));
    std::rewind(image);
    require(std::fread(original.data(), 1, original.size(), image) == original.size(), "libc image read");
    std::fclose(image);
    reset_media();
    sessions[0].pid = 10;
}

extern "C" void identity_service_request(const xos::file::request* in, xos::file::response* out) {
    handle(*in, *out, sessions[0], 0);
}

extern "C" void identity_service_finished() {
    close_session(sessions[0]);
    retry_description_cleanup();
    for (const auto& description : descriptions) { require(!description.used, "libc closes descriptions"); }
    for (const auto& object : file_objects) { require(!object.used, "libc and session release objects"); }
    require(!recovery_failed, "libc leaves recovery gate open");
}
