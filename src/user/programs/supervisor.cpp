// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/sdk.hpp>
#include <xos/display_client.hpp>
#include <xos/elf.hpp>
#include <xos/execution.hpp>
#include <string.h>
#include <unistd.h>
#include <xos/file_ui.hpp>
#include <xos/file_abi.hpp>
#include <xos/file_client.hpp>
#include <xos/text.hpp>

namespace {
using namespace xos;
using namespace xos::sdk;

bool demo_keep;
bool demo_quiet;
bool verbose_trace;

u64 number(const char* text) {
    u64 value = 0;
    if (*text == '\0') { return 0; }
    while (*text != '\0') {
        if (*text < '0' || *text > '9' || value > (~u64{0} - 9) / 10) { return 0; }
        value = value * 10 + static_cast<u64>(*text++ - '0');
    }
    return value;
}
void display_started(i64 child,i64 result) {
    char output[96]{};u32 used=0;
    const auto append=[&](const char* text){while(*text!=0 && used+1<sizeof(output)){output[used++]=*text++;}};
    const auto integer=[&](i64 value){
        if(value<0){output[used++]='-';}
        u64 number_value=value<0?u64{0}-static_cast<u64>(value):static_cast<u64>(value);
        char digits[20];u32 count=0;
        do{digits[count++]=static_cast<char>('0'+number_value%10);number_value/=10;}while(number_value!=0);
        while(count!=0){output[used++]=digits[--count];}
    };
    append("[display-start] pid=");integer(child);append(" result=");integer(result);append("\n");
    (void)xos::sdk::write(1,output,used); // one serial write: service startup cannot split this receipt
}

void result_line(u64 child, bool explicit_wait = false) {
    process_status status{};
    const i64 result = wait(child, status);
    if (result < 0) { print("wait: error="); signed_decimal(result); print("\n"); return; }
    if (!verbose_trace) {
        if (status.outcome == process_outcome::exited) {
            if (status.code != 0 || explicit_wait) {
                print("xsh: program exited with status "); signed_decimal(status.code); print("\n");
            }
        } else if (status.outcome == process_outcome::faulted) {
            print("xsh: program faulted (vector="); decimal(status.vector); print(")\n");
        } else {
            print("xsh: program cancelled (code="); signed_decimal(status.code); print(")\n");
        }
        return;
    }
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
const char* const kChildPath[] = {"PATH=/usr/bin:/bin:/", nullptr};

const char* candidate_description(execution::candidate_kind kind) {
    switch (kind) {
    case execution::candidate_kind::missing: return "not found";
    case execution::candidate_kind::directory: return "is a directory";
    case execution::candidate_kind::not_executable: return "not executable";
    case execution::candidate_kind::incompatible: return "incompatible target or format";
    case execution::candidate_kind::unreadable: return "cannot read program";
    case execution::candidate_kind::executable: return "executable";
    }
    return "unavailable";
}
void candidate_error(const char* name, const execution::candidate& candidate) {
    if (verbose_trace && candidate.format_error != elf::error::none) {
        print("elf: rejected reason="); print(elf::error_name(candidate.format_error)); print("\n");
    }
    print("xsh: "); print(candidate.path[0] ? candidate.path : name); print(": ");
    print(candidate_description(candidate.kind));
    if (verbose_trace) {
        print(" (format="); print(elf::error_name(candidate.format_error));
        print(", error="); signed_decimal(candidate.error); print(")");
    }
    print("\n");
}
const char* launch_stage_name(execution::launch_stage stage) {
    switch (stage) {
    case execution::launch_stage::open: return "open file";
    case execution::launch_stage::inspect: return "validate executable";
    case execution::launch_stage::prepare: return "prepare arguments and handles";
    case execution::launch_stage::create: return "create process";
    case execution::launch_stage::map: return "load process image";
    case execution::launch_stage::start: return "start process";
    case execution::launch_stage::none: return "launch program";
    }
    return "launch program";
}
bool builtin_named(const char* name) {
    const char* const names[] = {"help", "trace", "type", "ps", "kill", "images", "exec", "spawn",
        "wait", "stats", "primtest", "elftest", "ls", "cat", "stat", "rm", "edit", "filetest",
        "sync", "exec-file", "exec-driver", "exd", "spawn-file", "mkdir", "mv", "demo",
        "maint-run", "maint-recover", "maint-status"};
    for (const auto* item : names) { if (equal(name, item)) { return true; } }
    return false;
}
void launch_file(const char* name, u32 argc, char** argv, u32 spawn_depth, bool background) {
    const auto candidate = execution::resolve(name, "/usr/bin:/bin:/");
    if (candidate.kind != execution::candidate_kind::executable) {
        candidate_error(name, candidate); return;
    }
    spawn_options options{};
    options.grant_spawn = spawn_depth == 1;
    options.delegate_spawn_depth = spawn_depth > 1 ? spawn_depth : 0;
    options.environment = kChildPath;
    options.environment_count = 1;
    execution::launch_diagnostic diagnostic{};
    const i64 child = execution::spawn_file_diagnosed(candidate.path, argc, argv, options, diagnostic);
    if (child < 0) {
        print("xsh: cannot "); print(launch_stage_name(diagnostic.stage)); print(": "); print(candidate.path);
        print(" (error="); signed_decimal(child); print(")\n");
        return;
    }
    if (verbose_trace) {
        print("[loader] started pid="); decimal(static_cast<u64>(child));
        print(" file="); print(candidate.path); print("\n");
    } else if (background) {
        print("xsh: started pid="); decimal(static_cast<u64>(child)); print("\n");
    }
    if (!background) { result_line(static_cast<u64>(child)); }
}
// Explicit supervisor entry; filenames do not confer maintenance authority.
void maintenance_run(u32 argc, char** argv, bool recovering) {
    process_guard_info gate{};
    if (syscall(sys_process_guard, static_cast<u64>(process_guard_action::query),
                reinterpret_cast<u64>(&gate)) != 0) { print("maintenance: unavailable\n"); return; }
    file::Client files;
    if (!files.init()) { print("maintenance: files unavailable\n"); return; }
    i64 result;
    if (recovering) {
        if (gate.owner_pid != pid()) { print("maintenance: no retained session\n"); return; }
        // Releasing only the file lease leaves the kernel admission barrier up.
        result = files.maintenance_release();
        if (result == 0) { result = syscall(sys_process_guard, static_cast<u64>(process_guard_action::rearm)); }
    } else {
        result = syscall(sys_process_guard, static_cast<u64>(process_guard_action::begin));
    }
    if (result != 0) {
        print("maintenance: busy or denied error="); signed_decimal(result); print("\n"); return;
    }
    const auto candidate = execution::resolve(argv[0], "/usr/bin:/bin:/");
    execution::launch_diagnostic diagnostic{};
    spawn_options options{};
    options.environment = kChildPath; options.environment_count = 1;
    const i64 child = candidate.kind == execution::candidate_kind::executable ?
        execution::spawn_file_diagnosed(candidate.path, argc, argv, options, diagnostic) : -1;
    process_status outcome{};
    const bool completed = child > 0 && wait(static_cast<u64>(child), outcome) == 0;
    const bool success = completed && outcome.outcome == process_outcome::exited && outcome.code == 0;
    if (!success && (child > 0 || recovering)) {
        print("maintenance: retained; run maint-recover with a recovery tool\n"); return;
    }
    result = files.maintenance_release();
    if (result == 0) { result = syscall(sys_process_guard, static_cast<u64>(process_guard_action::end)); }
    if (result != 0) { print("maintenance: retained; cleanup error="); signed_decimal(result); print("\n"); }
    else if (child > 0) { print("maintenance: completed\n"); }
    else { print("maintenance: program unavailable; session closed\n"); }
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
        print("Files     ls [path] | cat/stat/rm/edit <file> | mkdir <path> | mv <old> <new> | sync\n"
              "Programs  <command> [args] | exd <command> [args] | type <command>\n"
              "          exec-file | exec-driver (exd) | spawn-file | exec | spawn | wait\n"
              "Maintain  maint-run <program> [args] | maint-recover <program> [args] | maint-status\n"
              "Shell     dash -i starts dash; exit inside dash returns here\n"
              "Display   display-start | exec gfxdemo [check|fault|hold|stop]\n"
              "Debug     trace on/off | ps | kill <pid> | stats | images | primtest | elftest | filetest\n"
              "Search    /usr/bin:/bin:/; paths containing '/' are used directly\n");
    } else if (equal(argv[0], "trace")) {
        if (argc == 1) { print(verbose_trace ? "xsh: trace on\n" : "xsh: trace off\n"); }
        else if (argc == 2 && (equal(argv[1], "on") || equal(argv[1], "off"))) {
            const bool enabled = equal(argv[1], "on");
            const auto result = syscall(sys_debug_trace, enabled ? 1 : 0);
            if (result < 0) { print("xsh: cannot change trace (error="); signed_decimal(result); print(")\n"); }
            else { verbose_trace = enabled; print(enabled ? "xsh: trace on\n" : "xsh: trace off\n"); }
        } else { print("Usage: trace [on|off]\n"); }
    } else if (equal(argv[0], "type")) {
        if (argc != 2) { print("Usage: type <command>\n"); }
        else if (equal(argv[1], "exd")) { print("exd: alias for exec-driver\n"); }
        else if (builtin_named(argv[1])) { print(argv[1]); print(": Xsh builtin\n"); }
        else {
            const auto candidate = execution::resolve(argv[1], "/usr/bin:/bin:/");
            if (candidate.kind == execution::candidate_kind::executable) {
                print(argv[1]); print(" -> "); print(candidate.path); print("\n");
            } else { candidate_error(argv[1], candidate); }
        }
    } else if (equal(argv[0], "ps") && argc == 1) {
        char buffer[768];
        const i64 count = syscall(9, reinterpret_cast<u64>(buffer), sizeof(buffer));
        if (count < 0) { print("ps: error="); signed_decimal(count); print("\n"); return; }
        for (i64 offset = 0; count > 0 && offset < count;) {
            const i64 chunk = count - offset > 256 ? 256 : count - offset;
            (void)xos::sdk::write(1, buffer + offset, static_cast<u64>(chunk)); offset += chunk;
        }
    } else if (equal(argv[0], "kill") && argc == 2) {
        print(syscall(10, number(argv[1])) == 0 ? "kill: accepted\n" : "kill: invalid pid\n");
    } else if (equal(argv[0], "images") && argc == 1) {
        image_list();
    } else if (equal(argv[0], "display-start") && (argc==1 || (argc==2 && equal(argv[1],"fault")))) {
        const char* args[]={"display",argc==2?"fault":"normal"};
        const i64 child=spawn(image_named("display"),2,args);
        const i64 granted=child>0?display_control(display_action::grant_service,static_cast<u64>(child)):child;
        display_started(child,granted);
        if(child>0 && granted!=0){(void)syscall(10,static_cast<u64>(child));result_line(static_cast<u64>(child));}
    } else if ((equal(argv[0], "exec") || equal(argv[0], "spawn")) && argc >= 2) {
        const u32 image = image_named(argv[1]);
        if (image == 0) { print("exec: unknown image\n"); return; }
        const i64 child = spawn(image, argc - 1, argv + 1);
        if (child < 0) { print("exec: error="); signed_decimal(child); print("\n"); return; }
        if (verbose_trace || equal(argv[0], "spawn")) {
            print("[loader] started pid="); decimal(static_cast<u64>(child));
            print(" image="); print(argv[1]); print("\n");
        }
        if (equal(argv[0], "exec")) { result_line(static_cast<u64>(child)); }
    } else if (equal(argv[0], "wait") && argc == 2) {
        result_line(number(argv[1]), true);
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
    } else if ((equal(argv[0], "maint-run") || equal(argv[0], "maint-recover")) && argc >= 2) {
        maintenance_run(argc - 1, argv + 1, equal(argv[0], "maint-recover"));
    } else if (equal(argv[0], "maint-status") && argc == 1) {
        process_guard_info gate{};
        const i64 result = syscall(sys_process_guard, static_cast<u64>(process_guard_action::query),
                                   reinterpret_cast<u64>(&gate));
        print("maintenance: owner="); decimal(gate.owner_pid); print(" worker="); decimal(gate.worker_pid);
        print(" error="); signed_decimal(result); print("\n");
    } else if ((equal(argv[0], "exec-file") || equal(argv[0], "spawn-file") ||
                equal(argv[0], "exec-driver") || equal(argv[0], "exd")) && argc >= 2) {
        const bool driver = equal(argv[0], "exec-driver") || equal(argv[0], "exd");
        launch_file(argv[1], argc - 1, argv + 1, driver ? 1u : 0u,
                    equal(argv[0], "spawn-file"));
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
    } else {
        // dash is the explicitly configured development shell; make is the
        // pinned explicit -B build tool. Both may delegate smaller construction
        // depths to the other and to GNU compiler drivers. Other bare commands
        // retain the legacy direct-child construction authority.
        const bool development_tool = equal(argv[0], "dash") || equal(argv[0], "make");
        launch_file(argv[0], argc, argv, development_tool ? 3u : 1u, false);
    }
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    using namespace xos::sdk;
    const auto trace_result = syscall(sys_debug_trace, 0);
    if (trace_result < 0) { print("xsh: lifecycle trace control unavailable\n"); }
    ui::init();
    print("\nWelcome to Xshell | XylophoneOS\n"
          "help: commands   dash -i: POSIX shell   trace on: diagnostics\n\n");
    bool last_cr = false;
    for (;;) {
        print("xsh> ");
        char line[2048]{};
        u32 used = 0;
        bool overflow = false;
        const u64 prompt_tick = ticks();
        for (;;) {
            char byte;
            const auto got = xos::sdk::read(0, &byte, 1);
            if (got <= 0) {
                if (!demo_keep && !demo_quiet && ticks() - prompt_tick >= 100) {
                    bool killed = false;
                    killed = syscall(10, 1) == 0 || killed;
                    killed = syscall(10, 2) == 0 || killed;
                    killed = syscall(10, 3) == 0 || killed;
                    killed = syscall(10, 4) == 0 || killed;
                    demo_quiet = true;
                    if (killed) { print(verbose_trace ? "\n[xsh] demo tasks stopped\nxsh> " : "\nxsh> "); }
                }
                yield();
                continue;
            }
            if (byte == '\n' && last_cr) { last_cr = false; continue; }
            last_cr = byte == '\r';
            if (byte == '\r' || byte == '\n') { print("\n"); break; }
            const u8 value = static_cast<u8>(byte);
            if (value == '\b' || value == 127) {
                if (used > 0 && !overflow) {
                    const auto erased = xos::text::erase_last(line, used);
                    used = erased.size;
                    for (u32 i = 0; i < erased.columns; ++i) { print("\b \b"); }
                }
            } else if ((value >= 32 && value <= 126) || value >= 0x80) {
                if (used < sizeof(line) - 1 && !overflow) {
                    line[used++] = byte; (void)xos::sdk::write(1, &byte, 1);
                } else { overflow = true; }
            }
        }
        if (overflow) { print("xsh: input line too long\n"); continue; }
        if (!xos::text::valid(line, used)) { print("xsh: invalid UTF-8 input\n"); continue; }
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
        if (count == 99) { print("xsh: too many arguments\n"); continue; }
        execute(count, arguments);
    }
}
