// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/sdk.hpp>
#include <xos/audio_client.hpp>
#include <xos/display_client.hpp>
#include <xos/elf.hpp>
#include <xos/execution.hpp>
#include <xos/fault_sha256.hpp>
#include <string.h>
#include <unistd.h>
#include <xos/file_ui.hpp>
#include <xos/file_abi.hpp>
#include <xos/file_client.hpp>
#include <xos/text.hpp>
#include <xos/thread_abi.hpp>
#include <xos/device.hpp>
#include <xos/net_client.hpp>
#include "fault_bundle.hpp"
#include "../services/shell_terminal.hpp"

namespace {
using namespace xos;
using namespace xos::sdk;

bool demo_keep;
bool demo_quiet;
bool verbose_trace;
bool persistent_recovery_gate;
xos::audio::client audio_session;
u64 audio_service_pid, audio_retry_after_ns;
u64 network_service_pid;

// The transaction directory is a durable recovery marker. Only a definite
// not-found result permits ordinary startup or release of the admission guard.
i64 persistent_marker_status(const char* path) {
    file::client files;
    if (!files.init()) { return static_cast<i64>(file::status::io); }
    u32 size = 0, attributes = 0;
    return files.stat_info(path, size, attributes);
}

bool marker_is_absent() {
    return persistent_marker_status("/var/lib/xypm/transaction") == static_cast<i64>(file::status::not_found) &&
           persistent_marker_status("/var/lib/xypm/txdata") == static_cast<i64>(file::status::not_found) &&
           persistent_marker_status("/var/lib/xypm/transaction_commit") == static_cast<i64>(file::status::not_found);
}

void start_persistent_recovery_gate() {
    if (marker_is_absent()) { return; }
    persistent_recovery_gate = true;
    // The boot demos are the only ordinary tasks allowed before Xsh starts.
    for (u64 demo = 1; demo <= 4; ++demo) { (void)syscall(10, demo); }
    demo_quiet = true;
    const i64 guarded = syscall(sys_process_guard, static_cast<u64>(process_guard_action::begin));
    print(guarded == 0 ? "maintenance: persistent recovery required\n"
                       : "maintenance: recovery check failed; startup locked\n");
}

// Session-only command history, bounded independently of the supervisor stack.
constexpr u32 history_capacity = 16;
constexpr u32 input_capacity = 2048;
char input_history[history_capacity][input_capacity]{};
u32 history_count;

u32 input_columns(const char* line, u32 start, u32 end) {
    u32 columns = 0;
    while (start < end) {
        xos::text::decoded unit{};
        if (xos::text::decode(line + start, end - start, unit) != xos::text::decode_status::ok) {
            ++start; ++columns; continue;
        }
        columns += xos::text::width(unit.codepoint);
        start += unit.bytes;
    }
    return columns;
}

u32 previous_character(const char* line, u32 position) {
    if (position == 0) { return 0; }
    --position;
    while (position != 0 && xos::text::continuation(static_cast<u8>(line[position]))) { --position; }
    return position;
}

u32 next_character(const char* line, u32 length, u32 position) {
    if (position >= length) { return length; }
    xos::text::decoded unit{};
    if (xos::text::decode(line + position, length - position, unit) != xos::text::decode_status::ok) {
        return position + 1;
    }
    return position + unit.bytes;
}

void redraw_input(const char* line, u32 length, u32 position) {
    print("\rxsh> ");
    if (length != 0) { (void)xos::sdk::write(1, line, length); }
    print("\x1b[K");
    const u32 columns = input_columns(line, position, length);
    for (u32 i = 0; i < columns; ++i) { print("\b"); }
}

void remember_input(const char* line, u32 length) {
    if (length == 0) { return; }
    if (history_count != 0 && equal(input_history[history_count - 1], line)) { return; }
    if (history_count == history_capacity) {
        for (u32 i = 1; i < history_count; ++i) { memcpy(input_history[i - 1], input_history[i], input_capacity); }
        --history_count;
    }
    memcpy(input_history[history_count], line, length);
    input_history[history_count][length] = '\0';
    ++history_count;
}

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

void result_line(u64 child, bool explicit_wait = false, const fault_bundle::receipt* diagnostic = nullptr,
                 bool terminal_session = false) {
    process_status status{};
    const i64 result = wait(child, status);
    if (terminal_session && user::shell_terminal::finish_application() != 0) {
        if (user::shell_terminal::recover("/bin/terminal.elf") <= 0) return;
        print("xsh: terminal session failed; service restarted\n");
    }
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
        if (diagnostic != nullptr && !fault_bundle::save(status, *diagnostic)) { print("[fault-bundle] not saved; result unknown\n"); }
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
    if (diagnostic != nullptr && !fault_bundle::save(status, *diagnostic)) { print("[fault-bundle] not saved; result unknown\n"); }
}
u32 image_named(const char* name) {
    for (u32 id = 1; id < 32; ++id) {
        image_info info{};
        if (syscall(sys_image_info, id, reinterpret_cast<u64>(&info)) < 0) { break; }
        if (equal(name, info.name)) { return id; }
    }
    return 0;
}

i64 delegate_audio_controller(u64 child, void*) {
    return xos::sdk::pio_grant(xos::pio_grant_action::delegate, child,
                               xos::pio_resource_pc_speaker);
}

// audio_service runs without supervisor rights and cannot read the image
// catalog (sys_image_info/sys_image_read are supervisor-only), so publish
// the tone worker image as a regular file the service reads back before
// spawning. No privilege is granted; the 16 KiB bound fails loudly instead
// of spawning from a stale copy (the current image is ~9.5 KiB). The file
// carries no ACL, so the digest published in argv[2] is what lets the
// service refuse a substituted image (issue G-1).
i64 publish_tone_worker(u32 tone, char digest_text[audio::worker_digest_hex_length + 1]) {
    image_info info{};
    i64 result = sdk::syscall(sys_image_info, tone, reinterpret_cast<u64>(&info));
    if (result < 0) return result;
    if (info.size == 0 || info.size > audio::worker_image_limit) return process_error_resources;
    static u8 worker_image[audio::worker_image_limit];
    image_read_request request{0, reinterpret_cast<u64>(worker_image), info.size};
    result = sdk::syscall(sys_image_read, tone, reinterpret_cast<u64>(&request));
    if (result != static_cast<i64>(info.size)) return result < 0 ? result : process_error_invalid;
    // Digest of the exact bytes handed to the service: whatever ends up at
    // worker_image_path must hash to this value or the service refuses it.
    sha256 hash;
    hash.update(worker_image, static_cast<xos::usize>(info.size));
    u8 digest[32];
    hash.finish(digest);
    hex_digest(digest, digest_text);
    file::client files;
    if (!files.init()) return static_cast<i64>(file::status::io);
    // replace() chunks past the single-request payload cap, creates the
    // target when missing, and commits atomically (the plain write() call
    // rejects anything larger than one request as invalid).
    return files.replace(audio::worker_image_path, worker_image, static_cast<u32>(info.size));
}

struct network_launch { u64 instance, grant; u32 channel; };
i64 prepare_network_driver(u64 child, void* context) {
    auto& launch = *static_cast<network_launch*>(context);
    device_output grant{};
    i64 result = device::grant(child, launch.instance, device_right_all, grant);
    if (result) return result;
    launch.grant = grant.token;
    const channel_create channel{channel_version, sizeof(channel_create), sdk::pid(), child, sizeof(net::bootstrap), 0};
    result = sdk::channel_open(channel);
    if (result < 0) return result;
    launch.channel = static_cast<u32>(result);
    const net::bootstrap message{net::version, sizeof(net::bootstrap), grant.token};
    return sdk::ipc_send(launch.channel, &message, sizeof(message));
}
void start_network(u64 instance, bool probe) {
    if (instance == 0 || instance > 65536) { print("net: instance must be 1 + PCI BDF\n"); return; }
    if (!probe && network_service_pid) {
        process_status status{};
        const i64 waited = syscall(sys_process_wait, network_service_pid, reinterpret_cast<u64>(&status), 1);
        if (waited == process_error_would_block) { print("net: owned service already running\n"); return; }
        if (waited) { print("net: owner status error="); signed_decimal(waited); print("\n"); return; }
        network_service_pid = 0;
    }
    const u32 image = image_named("net_service");
    if (!image) { print("net: driver image missing\n"); return; }
    network_launch launch{instance, 0, 0};
    spawn_options options{}; options.stdio[0] = -2;
    options.prepare_child = prepare_network_driver; options.prepare_context = &launch;
    const char* arguments[]{"net_service", probe ? "probe" : "serve"};
    const i64 child = sdk::spawn_image_options(image, 2, arguments, options);
    if (child < 0) {
        if (launch.channel) (void)sdk::channel_close(launch.channel);
        if (launch.grant) (void)device::revoke(launch.grant);
        print("net: start error="); signed_decimal(child); print("\n"); return;
    }
    if (probe) result_line(static_cast<u64>(child));
    else {
        network_service_pid = static_cast<u64>(child);
        print("[net-start] pid="); decimal(network_service_pid); print("\n");
    }
}
void stop_network() {
    if (!network_service_pid) { print("net: no owned service\n"); return; }
    net::client client;
    i64 result = client.connect(network_service_pid);
    if (!result) {
        net::message response{};
        result = client.request(net::operation::stop, nullptr, 0, response,
            static_cast<u64>(syscall(sys_clock_monotonic)) + 2000000000ull);
    }
    client.close();
    if (result) { print("net: stop error="); signed_decimal(result); print("\n"); return; }
    result_line(network_service_pid); network_service_pid = 0;
}

i64 start_audio_service() {
    const u32 image = image_named("audio_service");
    if (image == 0) return process_error_resources;
    const u32 tone = image_named("audio_tone");
    if (tone == 0) return process_error_resources;
    char worker_digest[audio::worker_digest_hex_length + 1] = {};
    const i64 published = publish_tone_worker(tone, worker_digest);
    if (published != 0) return published;
    // The service runs without supervisor rights and cannot enumerate the
    // image catalog (sys_image_info is supervisor-only); hand it the tone
    // image id as argv[1] and the published worker digest as argv[2]
    // instead of granting privilege.
    char tone_arg[4] = {};
    tone_arg[0] = static_cast<char>('0' + (tone / 10) % 10);
    tone_arg[1] = static_cast<char>('0' + tone % 10);
    const char* arguments[] = {"audio_service", tone_arg, worker_digest};
    spawn_options options{};
    for (u32 i = 0; i < 3; ++i) options.stdio[i] = -2;
    options.delegate_spawn_depth = 2;
    options.prepare_child = delegate_audio_controller;
    const i64 child = xos::sdk::spawn_image_options(image, 3, arguments, options);
    if (child > 0) {
        audio_service_pid = static_cast<u64>(child);
        audio_retry_after_ns = 0;
    }
    return child;
}

i64 ensure_audio_service(bool force = false) {
    if (audio_service_pid != 0) {
        process_status status{};
        const i64 waited = syscall(sys_process_wait, audio_service_pid,
                                   reinterpret_cast<u64>(&status), 1);
        if (waited == process_error_would_block) return 0;
        if (waited == 0) audio_service_pid = 0;
        else return waited;
        const i64 now = syscall(sys_clock_monotonic);
        if (now >= 0 && static_cast<u64>(now) <= thread_deadline_infinite - 1000000000ull)
            audio_retry_after_ns = static_cast<u64>(now) + 1000000000ull;
    }
    if (!force && audio_retry_after_ns != 0) {
        const i64 now = syscall(sys_clock_monotonic);
        if (now >= 0 && static_cast<u64>(now) < audio_retry_after_ns) return process_error_would_block;
    }
    const i64 started = start_audio_service();
    if (started < 0) {
        const i64 now = syscall(sys_clock_monotonic);
        if (now >= 0 && static_cast<u64>(now) <= thread_deadline_infinite - 1000000000ull)
            audio_retry_after_ns = static_cast<u64>(now) + 1000000000ull;
    }
    return started < 0 ? started : 0;
}

void print_audio_state(xos::audio::job_state state) {
    using xos::audio::job_state;
    switch (state) {
    case job_state::none: print("none"); break;
    case job_state::accepted: print("accepted"); break;
    case job_state::playing: print("playing"); break;
    case job_state::completed: print("completed"); break;
    case job_state::cancelled: print("cancelled"); break;
    case job_state::expired: print("expired"); break;
    case job_state::device_lost: print("device_lost"); break;
    }
}

i64 connect_audio_client() {
    if (audio_session.connected()) return 0;
    return audio_session.connect();
}

void submit_audio(const xos::audio::note* notes, u32 count) {
    i64 result = connect_audio_client();
    if (result != 0) {
        print("audio: service unavailable (error="); signed_decimal(result); print(")\n");
        return;
    }
    u64 job = 0;
    result = audio_session.submit(notes, count, job);
    if (result != 0) {
        print("audio: request rejected (error="); signed_decimal(result); print(")\n");
        return;
    }
    print("audio: accepted job="); decimal(job); print("\n");
}

bool parse_melody(const char* data, u32 length, xos::audio::note* output, u32& count) {
    count = 0;
    u32 position = 0;
    while (position < length) {
        if (count == xos::audio::max_notes) return false;
        auto parse_unsigned = [&](u32& value) {
            const u32 start = position;
            value = 0;
            while (position < length && data[position] >= '0' && data[position] <= '9') {
                const u32 digit = static_cast<u32>(data[position++] - '0');
                if (value > (0xffffffffu - digit) / 10) return false;
                value = value * 10 + digit;
            }
            return position != start;
        };
        xos::audio::note item{};
        if (!parse_unsigned(item.frequency_hz)) return false;
        if (position >= length || (data[position] != ' ' && data[position] != '\t')) return false;
        while (position < length && (data[position] == ' ' || data[position] == '\t')) ++position;
        if (!parse_unsigned(item.duration_ms)) return false;
        while (position < length && (data[position] == ' ' || data[position] == '\t')) ++position;
        if (position < length && data[position] == '\r') ++position;
        if (position < length && data[position] != '\n') return false;
        if (position < length) ++position;
        output[count++] = item;
    }
    return xos::audio::validate_sequence(output, count) == 0;
}

void audio_job_command(u32 argc, char** argv) {
    using namespace xos::audio;
    if (argc == 2 && equal(argv[1], "close")) {
        const i64 result = audio_session.close();
        print(result == 0 ? "audio: session closed\n" : "audio: close error=");
        if (result != 0) { signed_decimal(result); print("\n"); }
        return;
    }
    if (argc == 3 && (equal(argv[1], "status") || equal(argv[1], "cancel"))) {
        const u64 job = number(argv[2]);
        if (job == 0) { print("Usage: audio status|cancel <job>\n"); return; }
        i64 result = connect_audio_client();
        response reply{};
        if (result == 0) result = equal(argv[1], "status")
            ? audio_session.status(job, reply) : audio_session.cancel(job, reply);
        if (result != 0) {
            print("audio: result unknown or unavailable (error="); signed_decimal(result); print(")\n");
            return;
        }
        print("audio: job="); decimal(job); print(" state=");
        print_audio_state(static_cast<job_state>(reply.state));
        print(" notes="); decimal(reply.completed_notes); print("\n");
        return;
    }
    print("Usage: audio status|cancel <job> | audio close\n");
}

void melody_command(const char* path) {
    char contents[2048]{};
    u32 length = 0;
    file::client files;
    if (!files.init()) { print("melody: files service unavailable\n"); return; }
    const i64 loaded = files.read_all(path, contents, sizeof(contents), length);
    if (loaded != 0) { print("melody: cannot read file (error="); signed_decimal(loaded); print(")\n"); return; }
    xos::audio::note notes[xos::audio::max_notes]{};
    u32 count = 0;
    if (!parse_melody(contents, length, notes, count)) {
        print("melody: invalid sequence\n"); return;
    }
    submit_audio(notes, count);
}
void image_list() {
    for (u32 id = 1; id < 32; ++id) {
        image_info info{};
        if (syscall(sys_image_info, id, reinterpret_cast<u64>(&info)) < 0) { break; }
        print("image="); print(info.name); print(" bytes="); decimal(info.size); print("\n");
    }
}
const char* const kChildPath[] = {"PATH=/usr/bin:/bin:/", nullptr};
const char* const kMaintenancePath[] = {"PATH=/usr/bin:/bin:/", "XYP_RECOVERY_ABI=1", nullptr};

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
    case execution::launch_stage::file_setup: return "prepare file references";
    case execution::launch_stage::none: return "launch program";
    }
    return "launch program";
}
bool builtin_named(const char* name) {
    const char* const names[] = {"help", "trace", "type", "ps", "kill", "images", "exec", "spawn",
        "wait", "stats", "primtest", "elftest", "ls", "cat", "stat", "rm", "edit", "filetest",
        "sync", "exec-file", "exec-driver", "exd", "spawn-file", "mkdir", "mv", "demo",
        "maint-run", "maint-recover", "maint-recover-boot", "maint-status", "diag", "tty-run",
        "tone", "melody", "audio", "display-start", "interactium-start", "net-start", "net-stop", "net-probe"};
    for (const auto* item : names) { if (equal(name, item)) { return true; } }
    return false;
}
// SL2 authority modes for launch_file:
//  spawn_depth: legacy grant(1)/delegate(>1) — kept for exec-driver compat.
//  inherit_create: copy caller's can_create onto the child (common contract).
//  Ordinary bare commands and tty-run use inherit_create; exec-file uses neither;
//  exec-driver keeps the historical grant.
namespace {
struct launch_prepare_ctx {
    bool terminal;
};
xos::i64 launch_prepare_child(xos::u64 child, void* context) {
    const i64 auth = syscall(sys_process_authority, child,
                             static_cast<u64>(process_authority_mode::copy_from_caller));
    if (auth != 0) { return auth; }
    auto* ctx = static_cast<launch_prepare_ctx*>(context);
    if (ctx != nullptr && ctx->terminal) {
        return user::shell_terminal::prepare_application(child, nullptr);
    }
    return 0;
}
}  // namespace

void launch_file(const char* name, u32 argc, char** argv, u32 spawn_depth, bool background, bool diagnosed = false,
                 bool terminal_session = false, bool inherit_create = false) {
    const auto candidate = execution::resolve(name, "/usr/bin:/bin:/");
    if (candidate.kind != execution::candidate_kind::executable) {
        candidate_error(name, candidate); return;
    }
    if (!terminal_session && user::shell_terminal::active()) {
        print("xsh: terminal session active; use tty-run for compatible programs\n"); return;
    }
    if (terminal_session && !user::shell_terminal::active()) {
        if (!demo_keep && !demo_quiet) {
            for (u64 demo = 1; demo <= 4; ++demo) (void)syscall(10, demo);
            demo_quiet = true;
        }
        print("xsh: starting terminal service\n");
        if (user::shell_terminal::start("/bin/terminal.elf") <= 0 &&
            user::shell_terminal::recover("/bin/terminal.elf") <= 0) return;
    }
    spawn_options options{};
    fault_bundle::receipt diagnostic_receipt{};
    options.grant_spawn = spawn_depth == 1;
    options.delegate_spawn_depth = spawn_depth > 1 ? spawn_depth : 0;
    options.environment = kChildPath;
    options.environment_count = 1;
    const char* terminal_environment[] = {"PATH=/usr/bin:/bin:/", "TERM=xterm",
        "TERMINFO=/usr/local/share/terminfo", "LINES=24", "COLUMNS=80"};
    launch_prepare_ctx prepare_ctx{terminal_session};
    if (terminal_session) {
        for (u32 fd = 0; fd < 3; ++fd) options.stdio[fd] = -2;
        options.terminal_send_handle = user::shell_terminal::application_send_handle();
        options.environment = terminal_environment; options.environment_count = 5;
    }
    if (inherit_create || terminal_session) {
        options.prepare_child = launch_prepare_child;
        options.prepare_context = &prepare_ctx;
    }
    execution::launch_diagnostic diagnostic{};
    const i64 child = diagnosed
        ? execution::spawn_file_diagnosed_receipt(candidate.path, argc, argv, options, diagnostic, diagnostic_receipt)
        : execution::spawn_file_diagnosed(candidate.path, argc, argv, options, diagnostic);
    if (child < 0) {
        if (terminal_session && *options.terminal_send_handle != 0 &&
            user::shell_terminal::finish_application() != 0)
            (void)user::shell_terminal::recover("/bin/terminal.elf");
        else if (terminal_session && !user::shell_terminal::active())
            (void)user::shell_terminal::recover("/bin/terminal.elf");
        print("xsh: cannot "); print(launch_stage_name(diagnostic.stage)); print(": "); print(candidate.path);
        print(" (error="); signed_decimal(child); print(")\n");
        return;
    }
    if (verbose_trace && !terminal_session) {
        print("[loader] started pid="); decimal(static_cast<u64>(child));
        print(" file="); print(candidate.path); print("\n");
    } else if (background) {
        print("xsh: started pid="); decimal(static_cast<u64>(child)); print("\n");
    }
    if (!background) { result_line(static_cast<u64>(child), false, diagnosed ? &diagnostic_receipt : nullptr,
                                   terminal_session); }
}
// Explicit supervisor entry; filenames do not confer maintenance authority.
bool maintenance_run(u32 argc, char** argv, bool recovering, bool boot_image = false) {
    process_guard_info gate{};
    if (syscall(sys_process_guard, static_cast<u64>(process_guard_action::query),
                reinterpret_cast<u64>(&gate)) != 0) { print("maintenance: unavailable\n"); return false; }
    file::client files;
    if (!files.init()) { print("maintenance: files unavailable\n"); return false; }
    i64 result;
    if (recovering) {
        if (gate.owner_pid == 0 && persistent_recovery_gate) {
            result = syscall(sys_process_guard, static_cast<u64>(process_guard_action::begin));
        } else {
            if (gate.owner_pid != pid()) { print("maintenance: no retained session\n"); return false; }
            // Releasing only the file lease leaves the kernel admission barrier up.
            result = files.maintenance_release();
            if (result == 0) { result = syscall(sys_process_guard, static_cast<u64>(process_guard_action::rearm)); }
        }
    } else {
        result = syscall(sys_process_guard, static_cast<u64>(process_guard_action::begin));
    }
    if (result != 0) {
        print("maintenance: busy or denied error="); signed_decimal(result); print("\n"); return false;
    }
    i64 child = -1;
    if (boot_image) {
        const u32 image = image_named("xypm_recover");
        const char* arguments[] = {"xypm_recover"};
        if (image != 0) { child = spawn(image, 1, arguments); }
    } else {
        const auto candidate = execution::resolve(argv[0], "/usr/bin:/bin:/");
        execution::launch_diagnostic diagnostic{};
        spawn_options options{};
        const bool has_recovery_image = image_named("xypm_recover") != 0;
        options.environment = has_recovery_image ? kMaintenancePath : kChildPath;
        options.environment_count = has_recovery_image ? 2 : 1;
        if (candidate.kind == execution::candidate_kind::executable) {
            child = execution::spawn_file_diagnosed(candidate.path, argc, argv, options, diagnostic);
        }
    }
    process_status outcome{};
    const bool completed = child > 0 && wait(static_cast<u64>(child), outcome) == 0;
    const bool success = completed && outcome.outcome == process_outcome::exited && outcome.code == 0;
    if (!success && (child > 0 || recovering)) {
        print("maintenance: retained; run maint-recover with a recovery tool\n"); return false;
    }
    if (!marker_is_absent()) {
        persistent_recovery_gate = true;
        // A committed transaction is finalized by the immutable recovery image,
        // not by reopening the possibly replaced on-disk xypm executable.
        if (!recovering && success) {
            result = files.maintenance_release();
            if (result == 0) { result = syscall(sys_process_guard, static_cast<u64>(process_guard_action::rearm)); }
            const u32 image = image_named("xypm_recover");
            const char* arguments[] = {"xypm_recover"};
            const i64 recovery_child = result == 0 && image != 0 ? spawn(image, 1, arguments) : -1;
            process_status recovery_outcome{};
            const bool cleaned = recovery_child > 0 && wait(static_cast<u64>(recovery_child), recovery_outcome) == 0 &&
                recovery_outcome.outcome == process_outcome::exited && recovery_outcome.code == 0;
            if (!cleaned) { print("maintenance: retained; automatic recovery failed\n"); return false; }
        }
        if (!marker_is_absent()) { print("maintenance: retained; persistent recovery is required\n"); return false; }
    }
    result = files.maintenance_release();
    if (result == 0) { result = syscall(sys_process_guard, static_cast<u64>(process_guard_action::end)); }
    if (result != 0) {
        print("maintenance: retained; cleanup error="); signed_decimal(result); print("\n");
        return false;
    }
    persistent_recovery_gate = false;
    if (child > 0) { print("maintenance: completed\n"); }
    else { print("maintenance: program unavailable; session closed\n"); }
    return success;
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
    if (persistent_recovery_gate && !equal(argv[0], "help") && !equal(argv[0], "trace") &&
        !equal(argv[0], "ps") && !equal(argv[0], "kill") && !equal(argv[0], "stats") &&
        !equal(argv[0], "ls") && !equal(argv[0], "cat") && !equal(argv[0], "stat") &&
        !equal(argv[0], "maint-status") && !equal(argv[0], "maint-recover") &&
        !equal(argv[0], "maint-recover-boot")) {
        print("maintenance: persistent recovery required; command blocked\n"); return;
    }
    if (equal(argv[0], "help")) {
        print("Files     ls [path] | cat/stat/rm/edit <file> | mkdir <path> | mv <old> <new> | sync\n"
              "Programs  <command> [args] | exd <command> [args] | type <command>\n"
              "          exec-file | exec-driver (exd) | spawn-file | exec | spawn | wait\n"
              "          tty-run <terminal-compatible program> [args]\n"
              "Maintain  maint-run <program> [args] | maint-recover <program> [args] | maint-recover-boot | maint-status\n"
              "Shell     dash -i starts dash; exit inside dash returns here\n"
              "Audio     tone <Hz> <ms> | melody <file> | audio status|cancel <job> | audio close\n"
              "          audio start|restart manages the user-mode audio service\n"
              "Network   net-start <instance> | net-stop | net-probe <instance>\n"
              "Display   display-start | interactium-start | exec gfxdemo [check|fault|hold|stop]\n"
              "Debug     diag <program> [args] | trace on/off | ps | kill <pid> | stats | images | primtest | elftest | filetest\n"
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
    } else if ((equal(argv[0], "net-start") || equal(argv[0], "net-probe")) && argc == 2) {
        start_network(number(argv[1]), equal(argv[0], "net-probe"));
    } else if (equal(argv[0], "net-stop") && argc == 1) {
        stop_network();
    } else if (equal(argv[0], "display-start") && (argc==1 || (argc==2 &&
               (equal(argv[1],"fault") || equal(argv[1],"fault-present"))))) {
        const char* args[]={"display",argc==2?argv[1]:"normal"};
        const i64 child=spawn(image_named("display"),2,args);
        const i64 granted=child>0?display_control(display_action::grant_service,static_cast<u64>(child)):child;
        display_started(child,granted);
        if(child>0 && granted!=0){(void)syscall(10,static_cast<u64>(child));result_line(static_cast<u64>(child));}
    } else if (equal(argv[0], "interactium-start") && argc == 1) {
        const char* display_args[]={"display","normal"};
        const i64 display_pid=spawn(image_named("display"),2,display_args);
        const i64 granted=display_pid>0?display_control(display_action::grant_service,
                                                          static_cast<u64>(display_pid)):display_pid;
        display_started(display_pid,granted);
        if(display_pid>0 && granted!=0){
            (void)syscall(10,static_cast<u64>(display_pid));
            result_line(static_cast<u64>(display_pid));
            return;
        }
        const char* args[]={"interactiumd"};
        const i64 child=spawn(image_named("interactiumd"),1,args);
        print("[interactium-start] pid=");signed_decimal(child);print(" display=");
        signed_decimal(display_pid);print("\n");
    } else if ((equal(argv[0], "exec") || equal(argv[0], "spawn")) && argc >= 2) {
        if (user::shell_terminal::active()) {
            print("xsh: legacy image unavailable in terminal session\n"); return;
        }
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
    } else if (equal(argv[0], "maint-recover-boot") && argc == 1) {
        maintenance_run(0, nullptr, true, true);
    } else if ((equal(argv[0], "maint-run") || equal(argv[0], "maint-recover")) && argc >= 2) {
        maintenance_run(argc - 1, argv + 1, equal(argv[0], "maint-recover"));
    } else if (equal(argv[0], "maint-status") && argc == 1) {
        process_guard_info gate{};
        const i64 result = syscall(sys_process_guard, static_cast<u64>(process_guard_action::query),
                                   reinterpret_cast<u64>(&gate));
        print("maintenance: owner="); decimal(gate.owner_pid); print(" worker="); decimal(gate.worker_pid);
        print(" error="); signed_decimal(result); print("\n");
    } else if (equal(argv[0], "tone") && argc == 3) {
        const u64 frequency = number(argv[1]), duration = number(argv[2]);
        if (frequency < audio::min_frequency_hz || frequency > audio::max_frequency_hz ||
            duration < audio::min_note_ms || duration > audio::max_note_ms) {
            print("Usage: tone <40..5000 Hz> <10..2000 ms>\n"); return;
        }
        const audio::note item{static_cast<u32>(frequency), static_cast<u32>(duration)};
        submit_audio(&item, 1);
    } else if (equal(argv[0], "melody") && argc == 2) {
        melody_command(argv[1]);
    } else if (equal(argv[0], "audio") && argc == 2 && equal(argv[1], "start")) {
        const i64 result = ensure_audio_service(true);
        if (result == 0) { print("audio: service running\n"); }
        else { print("audio: service start failed (error="); signed_decimal(result); print(")\n"); }
    } else if (equal(argv[0], "audio") && argc == 2 && equal(argv[1], "restart")) {
        (void)audio_session.close();
        if (audio_service_pid != 0) {
            const u64 old_pid = audio_service_pid;
            const i64 killed = syscall(sys_process_cancel, old_pid);
            if (killed == 0) {
                process_status status{};
                (void)syscall(sys_process_wait, old_pid, reinterpret_cast<u64>(&status), 1);
            }
            audio_service_pid = 0;
        }
        audio_retry_after_ns = 0;
        const i64 result = ensure_audio_service(true);
        if (result == 0) { print("audio: service restarted; reconnect for a new session\n"); }
        else { print("audio: restart failed (error="); signed_decimal(result); print(")\n"); }
    } else if (equal(argv[0], "audio") && argc >= 2) {
        audio_job_command(argc, argv);
    } else if (equal(argv[0], "tty-run") && argc >= 2) {
        launch_file(argv[1], argc - 1, argv + 1, 0, false, false, true, true);
    } else if (equal(argv[0], "diag")) {
        if (argc < 2) { print("Usage: diag <program> [args]\n"); return; }
        // Diagnosed target uses the common inherit-create contract (SL3).
        launch_file(argv[1], argc - 1, argv + 1, 0, false, true, false, true);
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
        // SL2: every bare command uses the common inherit-create contract;
        // no name-based depth grants (shell_launch contract §4).
        launch_file(argv[0], argc, argv, 0, false, false, false, true);
    }
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    using namespace xos::sdk;
    const auto trace_result = syscall(sys_debug_trace, 0);
    if (trace_result < 0) { print("xsh: lifecycle trace control unavailable\n"); }
    start_persistent_recovery_gate();
    // Bootstrap installation must not run when marker inspection or guard
    // establishment fails; doing so could modify a disk awaiting recovery.
    process_guard_info startup_gate{};
    const i64 gate_query = syscall(sys_process_guard, static_cast<u64>(process_guard_action::query),
                                   reinterpret_cast<u64>(&startup_gate));
    const bool ui_ran = !persistent_recovery_gate ||
                        (gate_query == 0 && startup_gate.owner_pid == pid());
    if (ui_ran) { ui::init(); }
    print("\nWelcome to Xshell | XylophoneOS\n"
          "help: commands   dash -i: POSIX shell   trace on: diagnostics\n\n");
    (void)ensure_audio_service();
    // DU4: one-shot P2 install after demos are quieted so process_guard can begin.
    if (ui_ran && ui::bundle_install_ok() && ui::staged_count() > 0 &&
        !ui::bundle_marker_present()) {
        if (!demo_keep && !demo_quiet) {
            for (u64 demo = 1; demo <= 4; ++demo) { (void)syscall(10, demo); }
            demo_quiet = true;
        }
        bool all_ok = true;
        for (u32 i = 0; i < ui::staged_count(); ++i) {
            const char* path = ui::staged_path(i);
            if (path == nullptr) { all_ok = false; continue; }
            char program[] = "xypm";
            // ensure is idempotent: an already-installed identical package is
            // a success, so a partial first boot can finish on retry.
            char action[] = "ensure";
            char* args[] = {program, action, const_cast<char*>(path)};
            if (!maintenance_run(3, args, false)) { all_ok = false; }
        }
        if (all_ok && ui::bundle_marker_write()) {
            print("[files] bundle packages installed\n");
        } else if (all_ok) {
            print("[files] bundle marker write failed; will retry next boot\n");
        } else {
            print("[files] bundle package install incomplete; will retry next boot\n");
        }
    }
    bool last_cr = false;
    for (;;) {
        print("xsh> ");
        char line[input_capacity]{};
        char draft[input_capacity]{};
        char pending[4]{};
        u32 used = 0, cursor = 0, pending_size = 0;
        u32 history_index = history_count;
        bool overflow = false, invalid = false;
        // 0 normal, 1 ESC, 2 CSI, 3 discard malformed sequence, 4 SS3.
        u32 escape_state = 0, sequence_size = 0;
        char sequence[8]{};
        u64 escape_tick = 0;
        const u64 prompt_tick = ticks();
        const auto restore_history = [&](u32 index) {
            const char* source = index == history_count ? draft : input_history[index];
            used = static_cast<u32>(strlen(source));
            memcpy(line, source, used + 1);
            cursor = used;
            redraw_input(line, used, cursor);
        };
        const auto apply_sequence = [&](char key) {
            if (key == 'D') { cursor = previous_character(line, cursor); }
            else if (key == 'C') { cursor = next_character(line, used, cursor); }
            else if (key == 'H') { cursor = 0; }
            else if (key == 'F') { cursor = used; }
            else if (key == 'A' && history_index > 0) {
                if (history_index == history_count) { memcpy(draft, line, used); draft[used] = 0; }
                restore_history(--history_index);
                return;
            } else if (key == 'B' && history_index < history_count) {
                restore_history(++history_index);
                return;
            } else if (key == 'X' && cursor < used) {
                u32 next = next_character(line, used, cursor);
                memmove(line + cursor, line + next, used - next);
                used -= next - cursor; line[used] = 0;
            }
            redraw_input(line, used, cursor);
        };
        for (;;) {
            char byte;
            const auto got = xos::sdk::read(0, &byte, 1);
            if (got <= 0) {
                if (got < 0 && user::shell_terminal::needs_recovery()) {
                    if (user::shell_terminal::recover("/bin/terminal.elf") > 0) {
                        used = cursor = pending_size = escape_state = sequence_size = 0;
                        overflow = invalid = false; line[0] = 0;
                        print("\nxsh: terminal service restarted; input discarded\nxsh> ");
                    } else {
                        const i64 now = syscall(sys_clock_monotonic);
                        if (now >= 0) (void)syscall(sys_sleep_until, static_cast<u64>(now) + 100000000ull);
                        else yield();
                    }
                    continue;
                }
                if (escape_state != 0 && ticks() - escape_tick >= 20) {
                    if (escape_state == 1) { escape_state = 0; }
                    else { escape_state = 3; invalid = true; }
                }
                if (!demo_keep && !demo_quiet && ticks() - prompt_tick >= 100) {
                    bool killed = false;
                    killed = syscall(10, 1) == 0 || killed;
                    killed = syscall(10, 2) == 0 || killed;
                    killed = syscall(10, 3) == 0 || killed;
                    killed = syscall(10, 4) == 0 || killed;
                    demo_quiet = true;
                    if (killed) { print(verbose_trace ? "\n[xsh] demo tasks stopped\nxsh> " : "\nxsh> "); }
                }
                (void)ensure_audio_service();
                yield();
                continue;
            }
            if (byte == '\n' && last_cr) { last_cr = false; continue; }
            last_cr = byte == '\r';
            if (byte == '\r' || byte == '\n') {
                if (escape_state > 1 || pending_size != 0) { invalid = true; }
                print("\n"); break;
            }
            const u8 value = static_cast<u8>(byte);
            if (overflow) { continue; }
            if (escape_state != 0) {
                escape_tick = ticks();
                if (escape_state == 1) {
                    if (value == '[') { escape_state = 2; sequence_size = 0; }
                    else if (value == 'O') { escape_state = 4; }
                    else { escape_state = 0; invalid = true; }
                } else if (escape_state == 3) {
                    if (value >= 0x40 && value <= 0x7e) { escape_state = 0; }
                } else if (escape_state == 4) {
                    escape_state = 0;
                    if (value == 'H' || value == 'F') { apply_sequence(static_cast<char>(value)); }
                    else { invalid = true; }
                } else if (value >= 0x40 && value <= 0x7e) {
                    escape_state = 0;
                    char action = 0;
                    if (sequence_size == 0 && (value == 'A' || value == 'B' || value == 'C' || value == 'D' || value == 'H' || value == 'F')) {
                        action = static_cast<char>(value);
                    } else if (value == '~' && sequence_size == 1) {
                        if (sequence[0] == '1' || sequence[0] == '7') { action = 'H'; }
                        else if (sequence[0] == '4' || sequence[0] == '8') { action = 'F'; }
                        else if (sequence[0] == '3') { action = 'X'; }
                    }
                    if (action) { apply_sequence(action); } else { invalid = true; }
                } else if (sequence_size < sizeof(sequence) && value >= 0x20 && value <= 0x3f) {
                    sequence[sequence_size++] = byte;
                } else { escape_state = 3; invalid = true; }
                continue;
            }
            if (value == 0x1b) {
                if (pending_size != 0) { invalid = true; pending_size = 0; }
                escape_state = 1; escape_tick = ticks(); continue;
            }
            if (value == '\b' || value == 127) {
                if (pending_size != 0) { pending_size = 0; }
                else if (cursor != 0) {
                    u32 previous = previous_character(line, cursor);
                    const bool at_end = cursor == used;
                    const u32 erased_columns = input_columns(line, previous, cursor);
                    memmove(line + previous, line + cursor, used - cursor);
                    used -= cursor - previous; cursor = previous; line[used] = 0;
                    if (at_end) {
                        for (u32 i = 0; i < erased_columns; ++i) { print("\b \b"); }
                    } else { redraw_input(line, used, cursor); }
                }
                continue;
            }
            if ((value >= 32 && value <= 126) || value >= 0x80) {
                if (pending_size >= sizeof(pending)) { invalid = true; pending_size = 0; continue; }
                pending[pending_size++] = byte;
                xos::text::decoded unit{};
                const auto status = xos::text::decode(pending, pending_size, unit);
                if (status == xos::text::decode_status::incomplete) { continue; }
                if (status == xos::text::decode_status::invalid) { invalid = true; pending_size = 0; continue; }
                if (pending_size > sizeof(line) - 1 - used) { overflow = true; pending_size = 0; continue; }
                const bool at_end = cursor == used;
                memmove(line + cursor + pending_size, line + cursor, used - cursor);
                memcpy(line + cursor, pending, pending_size);
                cursor += pending_size; used += pending_size; line[used] = 0;
                if (at_end) { (void)xos::sdk::write(1, pending, pending_size); }
                else { redraw_input(line, used, cursor); }
                pending_size = 0;
            } else { invalid = true; }
        }
        if (overflow) { print("xsh: input line too long\n"); continue; }
        if (invalid || !xos::text::valid(line, used)) { print("xsh: invalid UTF-8 input or key sequence\n"); continue; }
        line[used] = '\0';
        memcpy(draft, line, used + 1);
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
        remember_input(draft, used);
        execute(count, arguments);
    }
}
