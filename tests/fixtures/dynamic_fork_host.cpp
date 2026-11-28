// SPDX-License-Identifier: Apache-2.0
// Include the production adapter so only its private initial state can be
// seeded by this test. Kernel channels and launch/policy boundaries are mocked;
// the separate launch-control suite and actual guest exercise those layers.
#include "../../src/user/loader/dynamic/spawn.cpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
namespace model {
using namespace xos;
u64 self, now;
channel_info handles[4]; u32 handle_count;
xos_fork_control_offer offer;
i64 record_error, send_error, receive_error, await_error;
u64 advance_on_receive;
u32 record_calls, sends, notifications, waits, cancels, closes;
bool configured = true, quarantined, native_committed;
void need(bool good, const char* label) { if (!good) { std::fprintf(stderr, "FORK_HOST_FAIL %s\n", label); std::abort(); } }
void reset() {
    using namespace xos::dynamic;
    self = 100; now = 1000; handle_count = 2;
    handles[0] = {1, sizeof(channel_info), 10, channel_send, 42, 42};
    handles[1] = {1, sizeof(channel_info), 11, channel_receive, 42, 42};
    offer = {}; record_error = send_error = receive_error = await_error = 0; advance_on_receive = 0;
    record_calls = sends = notifications = waits = cancels = closes = 0;
    configured = true; quarantined = native_committed = false;
    active_control = {XOS_LAUNCH_CONTROL_MAGIC, 1, sizeof(active_control), 42, 100, 7, 99, 2000, 10, 11, {0, 0}};
    active_artifact = {}; active_artifact.id = 3; active_artifact.sha256[0] = 9;
    active_ready = true; operation_owner = fork_parent_pid = fork_registered_child = 0;
    selected = {}; capsule = {}; fork_offer = {};
    replacing = registered = exec_pins_moved = false; prepared_child = 0;
}
void prepare() {
    need(xos_dynamic_fork_begin() == 0, "begin");
    need(xos_dynamic_fork_prepare(101, 3000) == 0, "prepare");
    need(record_calls == 1 && sends == 0, "no-ipc-to-building-child");
    // Child validation cases model delivery of these exact retained bytes.
    // Parent finish cases below separately require native commit before send.
    offer = xos::dynamic::fork_offer;
    need(offer.magic == XOS_FORK_CONTROL_MAGIC &&
         offer.size == 128 && offer.controller_pid == 100 && offer.child_pid == 101 &&
         offer.generation == 1 && offer.nonce == 567 && offer.deadline == 3000 &&
         offer.ready_handle == 30 && offer.ack_handle == 31 && offer.artifact.id == 3 &&
         offer.artifact.sha256[0] == 9 && !offer.reserved[0] && !offer.reserved[1] && !offer.reserved[2], "offer-shape");
}
void child() {
    self = 101; native_committed = true;
    handles[0] = {1, sizeof(channel_info), 30, channel_send, 100, 100};
    handles[1] = {1, sizeof(channel_info), 31, channel_receive, 100, 100};
}
void restore_parent() {
    using namespace xos::dynamic;
    self = 100;
    active_control = {XOS_LAUNCH_CONTROL_MAGIC, 1, sizeof(active_control), 42, 100, 7, 99, 2000, 10, 11, {0, 0}};
    active_ready = true; operation_owner = fork_parent_pid = 100; fork_registered_child = 101;
    fork_offer = offer; native_committed = true;
}
}
namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    using namespace model;
    if (number == 6) return static_cast<i64>(self);
    if (number == sys_clock_monotonic) return static_cast<i64>(now);
    if (number == sys_process_cancel) { need(first == 101, "cancel-owned-child"); ++cancels; return 0; }
    if (number == sys_channel) {
        if (first == static_cast<u64>(channel_action::enumerate)) {
            if (second >= handle_count) return thread_error_not_found;
            *reinterpret_cast<channel_info*>(third) = handles[second]; return 0;
        }
        if (first == static_cast<u64>(channel_action::wait)) return thread_error_timeout;
    }
    if (number == 4) {
        need(self == 100 && first == 31 && third == 128, "send-on-fresh-ack");
        ++sends;
        if (!native_committed) return ipc_error_broken;
        offer = *reinterpret_cast<const xos_fork_control_offer*>(second); return send_error;
    }
    if (number == 5) {
        need(self == 101 && first == 31 && third == 128, "receive-authenticated-offer");
        if (receive_error) return receive_error;
        *reinterpret_cast<xos_fork_control_offer*>(second) = offer;
        if (advance_on_receive) now = advance_on_receive;
        return sizeof(offer);
    }
    need(false, "unexpected-syscall"); return process_error_invalid;
}
}
namespace xos::dynamic {
error inspect_controller(controller_snapshot& state) {
    state = {}; state.owner_pid = model::self;
    state.flags = model::configured ? controller_configured : 0;
    if (model::quarantined) state.flags |= controller_quarantined;
    return error::none;
}
i64 admission(void*, u64 child, const launch::artifact&, const launch::artifact& artifact, u64 deadline) {
    model::need(child == 101 && artifact.id == 3 && artifact.sha256[0] == 9 && deadline == 3000, "bounded-artifact-admission");
    return model::record_error;
}
}
namespace xos::launch {
i64 record_child(u64 child, u64 deadline, descriptor& output, const artifact& admitted_artifact,
                 admission_check check, void* context, bool extended_channels) {
    model::need(!extended_channels, "ordinary-fork-retains-legacy-quota");
    ++model::record_calls;
    const auto admitted = check(context, child, {}, admitted_artifact, deadline);
    if (admitted) return admitted;
    output = {XOS_LAUNCH_CONTROL_MAGIC, 1, sizeof(output), 100, child, 1, 567, deadline, 30, 31, {0, 0}};
    return 0;
}
i64 notify_ready(const descriptor& control, const artifact& admitted_artifact, i64 status, u32 phase) {
    ++model::notifications;
    model::need(control.child_pid == model::self && control.controller_pid == 100 && control.ready_handle == 30 &&
                control.ack_handle == 31 && control.generation == 1 && control.nonce == 567 &&
                admitted_artifact.id == 3 && admitted_artifact.sha256[0] == 9 && !status && !phase, "child-ready-identity");
    return model::now >= control.deadline ? thread_error_timeout : 0;
}
i64 await_ready(u64 child, diagnostic&) { model::need(child == 101, "await-child"); return model::await_error; }
i64 wait(u64 child, process_status& output, u32) {
    model::need(child == 101, "reap-owned-child"); ++model::waits; output = {}; return 0;
}
i64 close_control(u64 child) { model::need(child == 101, "close-child-control"); ++model::closes; return 0; }
}
int main() {
    using namespace xos;
    using namespace xos::dynamic;
    using namespace model;
    reset(); prepare(); child();
    need(!xos_dynamic_fork_child(3000) && active_ready && active_control.child_pid == 101 &&
         active_control.controller_pid == 100 && !fork_parent_pid && !operation_owner && notifications == 1,
         "successful-child-adoption");
    need(xos_dynamic_fork_child(3000) == process_error_state && notifications == 1, "offer-not-reused");
    restore_parent(); need(!xos_dynamic_fork_finish(101, 1) && sends == 1 && !cancels && !waits && !closes &&
         !operation_owner && active_control.controller_pid == 42 && active_control.child_pid == 100,
         "parent-retains-upstream-control");

    for (u32 mode = 0; mode < 7; ++mode) {
        reset();
        if (mode == 0) active_ready = false;
        if (mode == 1) model::configured = false;
        if (mode == 2) quarantined = true;
        if (mode == 3) selected.live = true;
        if (mode == 4) handles[1].controller_pid = 999;
        if (mode == 5) handle_count = 0;
        if (mode == 6) handles[0].rights = channel_receive;
        need(xos_dynamic_fork_begin() < 0 && !operation_owner && !record_calls && !fork_parent_pid, "begin-refuses-invalid-authority");
    }
    reset(); operation_owner = 100;
    need(xos_dynamic_fork_begin() == process_error_busy && operation_owner == 100, "competing-operation-preserved");
    reset(); need(!xos_dynamic_fork_begin(), "begin-record-failure"); record_error = process_error_denied;
    need(xos_dynamic_fork_prepare(101, 3000) == process_error_denied && !sends, "record-denial-no-offer");
    need(!xos_dynamic_fork_finish(101, 0) && !operation_owner && !closes, "record-failure-release");
    reset(); need(!xos_dynamic_fork_begin(), "begin-send-failure"); send_error = ipc_error_broken;
    need(!xos_dynamic_fork_prepare(101, 3000) && !sends, "prepare-defers-send");
    native_committed = true;
    need(xos_dynamic_fork_finish(101, 1) == ipc_error_broken && sends == 1 &&
         cancels == 1 && waits == 1 && closes == 1 && !operation_owner, "send-failure-no-replay-kill-reap");
    reset(); prepare();
    need(!xos_dynamic_fork_finish(101, 0) && !sends && !cancels && !waits && closes == 1,
         "uncommitted-abort-closes-without-send");

    for (u32 mode = 0; mode < 12; ++mode) {
        reset(); prepare(); child();
        if (mode == 0) ++offer.magic;
        if (mode == 1) ++offer.version;
        if (mode == 2) --offer.size;
        if (mode == 3) ++offer.controller_pid;
        if (mode == 4) ++offer.child_pid;
        if (mode == 5) ++offer.generation;
        if (mode == 6) offer.nonce = 0;
        if (mode == 7) ++offer.deadline;
        if (mode == 8) ++offer.ready_handle;
        if (mode == 9) ++offer.ack_handle;
        if (mode == 10) offer.reserved[2] = 1;
        if (mode == 11) ++offer.artifact.sha256[31];
        need(xos_dynamic_fork_child(3000) == process_error_denied && !notifications && active_control.child_pid == 100,
             "malformed-offer-not-adopted");
    }
    reset(); prepare(); child(); handles[2] = handles[0]; handles[2].handle = 32; handle_count = 3;
    need(xos_dynamic_fork_child(3000) == process_error_denied && !notifications, "ambiguous-native-pair");
    reset(); prepare(); child(); now = 3000;
    need(xos_dynamic_fork_child(3000) == thread_error_timeout && !notifications, "expired-offer");
    reset(); prepare(); child(); advance_on_receive = 3000;
    need(xos_dynamic_fork_child(3000) == thread_error_timeout && !active_ready, "late-ready-rejected");
    reset(); prepare(); child(); receive_error = process_error_would_block;
    need(xos_dynamic_fork_child(3000) == thread_error_timeout && !notifications, "bounded-missing-offer");
    reset(); prepare(); child(); receive_error = ipc_error_broken;
    need(xos_dynamic_fork_child(3000) == ipc_error_broken && !notifications, "dead-controller");
    reset(); prepare(); native_committed = true; now = 3000;
    need(xos_dynamic_fork_finish(101, 1) == thread_error_timeout && !sends && cancels == 1 &&
         waits == 1 && closes == 1 && !operation_owner, "late-publish-kill-reap-no-send");
    reset(); prepare(); native_committed = true; await_error = thread_error_timeout;
    need(xos_dynamic_fork_finish(101, 1) == thread_error_timeout && cancels == 1 && waits == 1 && closes == 1 &&
         !fork_parent_pid && !operation_owner && active_control.child_pid == 100, "ready-failure-kill-reap-cleanup");
    std::puts("DYNAMIC_FORK_HOST_PASS groups=10 malformed_variants=12 begin_rejections=7");
}
