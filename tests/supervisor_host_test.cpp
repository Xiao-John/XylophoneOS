// SPDX-License-Identifier: Apache-2.0
#include <cstdio>
#include <cstring>

#include "../src/user/programs/supervisor.cpp"

namespace {
xos::i64 spawn_result = 57;
xos::i64 publish_result;
unsigned spawn_calls;
unsigned failures;

void check(bool condition, const char* label) {
    std::printf("%s: %s\n", label, condition ? "ok" : "FAIL");
    if (!condition) ++failures;
}
}

namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64) {
    if (number == sys_image_info) {
        if (first == 0 || first > 2) return process_error_invalid;
        auto& info = *reinterpret_cast<image_info*>(second);
        info = {};
        std::strcpy(info.name, first == 1 ? "audio_service" : "audio_tone");
        info.size = 1;
        return 0;
    }
    if (number == sys_image_read) {
        const auto& request = *reinterpret_cast<const image_read_request*>(second);
        *reinterpret_cast<u8*>(request.destination) = 0x42;
        return 1;
    }
    if (number == sys_process_wait) return process_error_would_block;
    if (number == sys_clock_monotonic) return 1000000000;
    if (number == sys_pio_grant) return 0;
    return process_error_invalid;
}

bool equal(const char* left, const char* right) { return std::strcmp(left, right) == 0; }

i64 spawn_image_options(u32 image, u32 argc, const char* const*, const spawn_options& options) {
    ++spawn_calls;
    check(image == 1 && argc == 3 && options.delegate_spawn_depth == 2,
          "audio service launch retains arguments and delegation");
    check(options.stdio[0] == -2 && options.stdio[1] == -2 && options.stdio[2] == -2,
          "audio service launch closes stdio");
    return spawn_result;
}
}

namespace xos::file {
bool client::init() { return true; }
i64 client::replace(const char*, const void*, u32) { return publish_result; }
}

int main() {
    check(ensure_audio_service(true) == 0 && audio_service_pid == 57 && spawn_calls == 1,
          "new audio service reports success");
    check(ensure_audio_service(true) == 0 && spawn_calls == 1,
          "running audio service reports success without respawn");
    audio_service_pid = 0;
    spawn_result = xos::process_error_resources;
    check(ensure_audio_service(true) == spawn_result && audio_service_pid == 0,
          "failed audio launch preserves error");
    check(ensure_audio_service() == xos::process_error_would_block && spawn_calls == 2,
          "failed audio launch backs off");
    spawn_result = 58;
    check(ensure_audio_service(true) == 0 && audio_service_pid == 58 && spawn_calls == 3,
          "forced audio restart reports success");
    audio_service_pid = 0;
    publish_result = static_cast<xos::i64>(xos::file::status::io);
    check(ensure_audio_service(true) == publish_result && spawn_calls == 3,
          "worker publish error prevents launch");
    check(builtin_named("display-start"), "type recognizes display-start");
    check(builtin_named("interactium-start"), "type recognizes interactium-start");
    check(!builtin_named("missing-program"), "type still resolves external names");
    if (failures != 0) return 1;
    std::printf("SUPERVISOR_CASES_PASSED=9\n");
    return 0;
}
