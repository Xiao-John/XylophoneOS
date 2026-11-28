// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../../../src/ports/webkit/browser/transport.hpp"
#include <xos/execution.hpp>
#include <xos/net_service_client.hpp>

namespace xos::clarke {
struct launch_probe_context {
    net2::session_client* authority;
    u64 pid = 0;
    i64 first_abort = process_error_state;
    bool double_abort = false, revoked = false;
};
inline i64 prepare_launch_probe(u64 pid, void* raw) {
    auto& context = *static_cast<launch_probe_context*>(raw); context.pid = pid;
    const process_budget_vector limits{1,1024,1,8,0,0};
    i64 result = sdk::set_process_budget(pid, limits);
    if (result) return result;
    net2::message input{}, output{}; input.action = net2::operation::revoke_peer;
    input.object = pid; input.deadline = deadline_after(bootstrap_ns);
    context.revoked = true; result = context.authority->request(input, output);
    if (result) return result;
    if (context.double_abort) context.first_abort = sdk::syscall(sys_process_abort, pid);
    return 0;
}
inline bool launch_probe(u64 service, const execution::image_receipt& receipt, bool double_abort) {
    net2::session_client authority;
    net2::peer_policy_snapshot before{}, after{};
    if (authority.connect(service) || authority.peer_policy(net2::peer_policy_action::query,0,deadline_after(bootstrap_ns),before)) return false;
    launch_probe_context context{&authority,0,process_error_state,double_abort,false};
    sdk::spawn_options options{}; options.stdio[0] = -2;
    options.prepare_child = prepare_launch_probe; options.prepare_context = &context;
    const char* arguments[]{"/clarke_launch.elf"};
    execution::launch_abort_outcome outcome{};
    const auto resources = sdk::stats();
    const i64 spawned = execution::spawn_verified_static_file(arguments[0],1,arguments,options,receipt,outcome);
    const bool confirmed = spawned < 0 && outcome.version == 1 && outcome.size == sizeof(outcome) &&
        outcome.pid == context.pid && context.pid && outcome.never_started == 1 && outcome.abort_attempted == 1 && outcome.abort_result == 0;
    i64 released = process_error_state;
    if (confirmed && context.revoked)
        released = authority.peer_policy(net2::peer_policy_action::release_retired,context.pid,deadline_after(bootstrap_ns),after);
    const i64 queried = authority.peer_policy(net2::peer_policy_action::query,0,deadline_after(bootstrap_ns),after);
    const auto final = sdk::stats();
    const bool restored = resources.tasks == final.tasks && resources.completions == final.completions && resources.free_pages == final.free_pages;
    const bool ok = !queried && context.revoked && outcome.pid == context.pid && spawned < 0 &&
        (double_abort ? (context.first_abort == 0 && !confirmed && outcome.abort_attempted == 1 &&
                        outcome.abort_result < 0 && released == process_error_state && after.occupied == before.occupied + 1) :
                       (confirmed && !released && after.occupied == before.occupied)) && restored;
    sdk::print("CLARKE_START_PROBE double_abort="); sdk::decimal(double_abort); sdk::print(" spawned="); sdk::signed_decimal(spawned);
    sdk::print(" pid="); sdk::decimal(outcome.pid); sdk::print(" first_abort="); sdk::signed_decimal(context.first_abort);
    sdk::print(" never_started="); sdk::decimal(outcome.never_started); sdk::print(" attempted="); sdk::decimal(outcome.abort_attempted);
    sdk::print(" abort="); sdk::signed_decimal(outcome.abort_result); sdk::print(" release="); sdk::signed_decimal(released);
    sdk::print(" policy_before="); sdk::decimal(before.occupied); sdk::print(" policy_after="); sdk::decimal(after.occupied);
    sdk::print(" resources="); sdk::decimal(restored); sdk::print(" result="); sdk::print(ok ? "PASS\n" : "FAIL\n");
    return ok;
}
}
