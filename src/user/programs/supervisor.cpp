// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/sdk.hpp>
#include <xos/elf.hpp>
#include <xos/file_ui.hpp>
#include <xos/file_abi.hpp>

namespace {
using namespace xos;
using namespace xos::sdk;

bool demo_keep;
bool demo_quiet;

u64 number(const char* text) {
    u64 value = 0;
    if (*text == '\0') { return 0; }
    while (*text != '\0') {
        if (*text < '0' || *text > '9' || value > (~u64{0} - 9) / 10) { return 0; }
        value = value * 10 + static_cast<u64>(*text++ - '0');
    }
    return value;
}
void result_line(u64 child) {
    process_status status{};
    const i64 result = wait(child, status);
    if (result < 0) { print("wait: error="); signed_decimal(result); print("\n"); return; }
    print("[wait] pid="); decimal(status.pid); print(" kind=");
    switch (status.outcome) {
    case process_outcome::exited: print("exited"); break;
    case process_outcome::faulted: print("faulted"); break;
    case process_outcome::killed: print("killed"); break;
    }
    print(" code="); signed_decimal(status.code);
    if (status.outcome == process_outcome::faulted) {
        print(" vector="); decimal(status.vector); print(" address="); decimal(status.address);
    }
    print("\n");
}
u32 image_named(const char* name) {
    for (u32 id = 1; id < 32; ++id) {
        image_info info{};
        if (syscall(sys_image_info, id, reinterpret_cast<u64>(&info)) < 0) { break; }
        if (equal(name, info.name)) { return id; }
    }
    return 0;
}
void image_list() {
    for (u32 id = 1; id < 32; ++id) {
        image_info info{};
        if (syscall(sys_image_info, id, reinterpret_cast<u64>(&info)) < 0) { break; }
        print("image="); print(info.name); print(" bytes="); decimal(info.size); print("\n");
    }
}
void show_stats() {
    const auto state = stats();
    print("[resources] free="); decimal(state.free_pages);
    print(" tasks="); decimal(state.tasks); print(" completions="); decimal(state.completions); print("\n");
}
void primitive_check() {
    const auto before = stats();
    bool ok = true;
    u64 previous = 0;
    for (u32 i = 0; i < 12; ++i) {
        const i64 child = syscall(sys_process_create, 7);
        if (child <= 0 || static_cast<u64>(child) <= previous) { ok = false; break; }
        previous = static_cast<u64>(child);
        process_page invalid{0x100000, 0, 0, map_read | map_write};
        ok = ok && syscall(sys_process_map, previous, reinterpret_cast<u64>(&invalid)) < 0;
        invalid = {process_user_begin, 0, 0, map_read | map_write | map_execute};
        ok = ok && syscall(sys_process_map, previous, reinterpret_cast<u64>(&invalid)) < 0;
        invalid = {process_user_begin, 0x100000, 8, map_read};
        ok = ok && syscall(sys_process_map, previous, reinterpret_cast<u64>(&invalid)) < 0;
        process_page valid{process_user_begin, 0, 0, map_read | map_execute};
        ok = ok && syscall(sys_process_map, previous, reinterpret_cast<u64>(&valid)) == 0;
        ok = ok && syscall(sys_process_map, previous, reinterpret_cast<u64>(&valid)) < 0;
        process_entry bad_entry{process_user_begin, process_user_end - 16, process_user_end - 4096};
        ok = ok && syscall(sys_process_start, previous, reinterpret_cast<u64>(&bad_entry)) < 0;
        ok = ok && syscall(sys_process_abort, previous) == 0;
        ok = ok && syscall(sys_process_abort, previous) < 0;
    }
    u64 handles[8]{};
    u32 count = 0;
    for (; count < 8; ++count) {
        const i64 created = syscall(sys_process_create, 7);
        if (created < 0) { ok = ok && created == process_error_resources; break; }
        handles[count] = static_cast<u64>(created);
    }
    ok = ok && count != 0 && count < 8;
    for (u32 i = 0; i < count; ++i) {
        ok = ok && syscall(sys_process_abort, handles[i]) == 0;
    }
    const i64 capped = syscall(sys_process_create, 7);
    const u64 pressure_started = ticks();
    u32 pressure_pages = 0;
    if (capped <= 0) { ok = false; }
    else {
        for (u32 i = 0; i < process_max_pages; ++i) {
            process_page page{process_user_begin + u64{i} * 4096, 0, 0, map_read | map_write};
            const i64 mapped = syscall(sys_process_map, static_cast<u64>(capped), reinterpret_cast<u64>(&page));
            if (mapped != 0) { ok = false; break; }
            ++pressure_pages;
        }
        process_page overflow{process_user_begin + process_max_pages * 4096, 0, 0, map_read | map_write};
        ok = ok && syscall(sys_process_map, static_cast<u64>(capped), reinterpret_cast<u64>(&overflow)) == process_error_resources;
        ok = ok && syscall(sys_process_abort, static_cast<u64>(capped)) == 0;
    }
    print("[primitive] page_pressure="); decimal(pressure_pages);
    print(" ticks="); decimal(ticks() - pressure_started); print("\n");
    const auto after = stats();
    ok = ok && before.free_pages == after.free_pages && before.tasks == after.tasks &&
         before.completions == after.completions;
    print(ok ? "[primitive] bounds=w_x=source=duplicate=entry=stale=capacity checked rollback=stable\n"
             : "[primitive] FAILED\n");
}

void execute(u32 argc, char** argv) {
    if (argc == 0) { return; }
    if (equal(argv[0], "help")) {
        print("ps | kill <pid> | images | exec <image> [args] | spawn <image> [args]\n"
              "wait <pid> | stats | primtest | elftest\n"
              "ls | cat <file> | stat <file> | rm <file> | edit <file> | filetest\n"
              "sync | exec-file/spawn-file/exec-driver <file> [args] | mkdir <path> | mv <old> <new> | help\n");
    } else if (equal(argv[0], "ps") && argc == 1) {
        char buffer[768];
        const i64 count = syscall(9, reinterpret_cast<u64>(buffer), sizeof(buffer));
        if (count < 0) { print("ps: error="); signed_decimal(count); print("\n"); return; }
        for (i64 offset = 0; count > 0 && offset < count;) {
            const i64 chunk = count - offset > 256 ? 256 : count - offset;
            (void)write(1, buffer + offset, static_cast<u64>(chunk)); offset += chunk;
        }
    } else if (equal(argv[0], "kill") && argc == 2) {
        print(syscall(10, number(argv[1])) == 0 ? "kill: accepted\n" : "kill: invalid pid\n");
    } else if (equal(argv[0], "images") && argc == 1) {
        image_list();
    } else if ((equal(argv[0], "exec") || equal(argv[0], "spawn")) && argc >= 2) {
        const u32 image = image_named(argv[1]);
        if (image == 0) { print("exec: unknown image\n"); return; }
        const i64 child = spawn(image, argc - 1, argv + 1);
        if (child < 0) { print("exec: error="); signed_decimal(child); print("\n"); return; }
        print("[loader] started pid="); decimal(static_cast<u64>(child));
        print(" image="); print(argv[1]); print("\n");
        if (equal(argv[0], "exec")) { result_line(static_cast<u64>(child)); }
    } else if (equal(argv[0], "wait") && argc == 2) {
        result_line(number(argv[1]));
    } else if (equal(argv[0], "ls") && (argc == 1 || argc == 2)) {
        ui::list(argc == 2 ? argv[1] : "/");
    } else if (equal(argv[0], "cat") && argc == 2) {
        ui::cat(argv[1]);
    } else if (equal(argv[0], "stat") && argc == 2) {
        ui::stat(argv[1]);
    } else if (equal(argv[0], "mkdir") && argc == 2) {
        ui::make_directory(argv[1]);
    } else if (equal(argv[0], "mv") && argc == 3) {
        ui::rename_file(argv[1], argv[2]);
    } else if (equal(argv[0], "rm") && argc == 2) {
        ui::remove_file(argv[1]);
    } else if (equal(argv[0], "edit") && argc == 2) {
        ui::edit(argv[1]);
    } else if (equal(argv[0], "filetest") && argc == 1) {
        ui::filetest();
    } else if (equal(argv[0], "sync") && argc == 1) {
        const i64 synced = ui::sync();
        if (synced == 0) { print("[files] sync=ok\n"); }
        else { print("[files] sync error="); signed_decimal(synced); print("\n"); }
    } else if ((equal(argv[0], "exec-file") || equal(argv[0], "spawn-file") || equal(argv[0], "exec-driver")) && argc >= 2) {
        spawn_options options{};
        options.grant_spawn = equal(argv[0], "exec-driver");
        const i64 child = options.grant_spawn
            ? spawn_file_options(argv[1], argc - 1, argv + 1, options)
            : spawn_file(argv[1], argc - 1, argv + 1);
        if (child < 0) { print("exec-file: error="); signed_decimal(child); print("\n"); return; }
        print("[loader] started pid="); decimal(static_cast<u64>(child));
        print(" file="); print(argv[1]); print("\n");
        if (!equal(argv[0], "spawn-file")) { result_line(static_cast<u64>(child)); }
    } else if (equal(argv[0], "demo") && argc == 2) {
        if (equal(argv[1], "keep")) {
            demo_keep = true;
            print("demo: keep\n");
        } else if (equal(argv[1], "quiet")) {
            bool killed = false;
            killed = syscall(10, 1) == 0 || killed;
            killed = syscall(10, 2) == 0 || killed;
            killed = syscall(10, 3) == 0 || killed;
            killed = syscall(10, 4) == 0 || killed;
            demo_quiet = true;
            print(killed ? "[sup] demo tasks stopped\n" : "[sup] demo tasks already stopped\n");
        } else {
            print("demo: keep|quiet\n");
        }
    } else if (equal(argv[0], "stats") && argc == 1) {
        show_stats();
    } else if (equal(argv[0], "primtest") && argc == 1) {
        primitive_check();
    } else if (equal(argv[0], "elftest") && argc == 1) {
        const auto before = stats();
        const auto checked = elf::self_check(target_elf_machine());
        const auto after = stats();
        print("[elf] cases="); decimal(checked);
        print(checked == 24 && before.free_pages == after.free_pages ? " result=pass resources=stable\n"
                                                                    : " result=FAILED\n");
    } else { print("supervisor: unknown command; try help\n"); }
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    using namespace xos::sdk;
    print("[sup] XOS E07 user loader + persistent work disk; type help; Escape cancels a foreground child\n");
    ui::init();
    bool last_cr = false;
    for (;;) {
        print("sup> ");
        char line[2048]{};
        u32 used = 0;
        bool overflow = false;
        const u64 prompt_tick = ticks();
        for (;;) {
            char byte;
            const auto got = read(0, &byte, 1);
            if (got <= 0) {
                if (!demo_keep && !demo_quiet && ticks() - prompt_tick >= 100) {
                    bool killed = false;
                    killed = syscall(10, 1) == 0 || killed;
                    killed = syscall(10, 2) == 0 || killed;
                    killed = syscall(10, 3) == 0 || killed;
                    killed = syscall(10, 4) == 0 || killed;
                    demo_quiet = true;
                    if (killed) { print("\n[sup] demo tasks stopped; prompt is sup>\nsup> "); }
                }
                yield();
                continue;
            }
            if (byte == '\n' && last_cr) { last_cr = false; continue; }
            last_cr = byte == '\r';
            if (byte == '\r' || byte == '\n') { print("\n"); break; }
            if (byte == '\b' || byte == 127) {
                if (used > 0 && !overflow) { --used; print("\b \b"); }
            } else if (byte >= 32 && byte <= 126) {
                if (used < sizeof(line) - 1 && !overflow) {
                    line[used++] = byte; (void)write(1, &byte, 1);
                } else { overflow = true; }
            }
        }
        if (overflow) { print("supervisor: line_too_long\n"); continue; }
        line[used] = '\0';
        char* arguments[process_max_args + 1]{};
        u32 count = 0;
        bool in_word = false;
        for (u32 i = 0; i < used; ++i) {
            if (line[i] == ' ') { line[i] = '\0'; in_word = false; }
            else if (!in_word) {
                if (count == process_max_args + 1) { count = 99; break; }
                arguments[count++] = line + i; in_word = true;
            }
        }
        if (count == 99) { print("supervisor: too_many_arguments\n"); continue; }
        execute(count, arguments);
    }
}
