/* SPDX-License-Identifier: Apache-2.0 */
/* Test-only fixed-width durable evidence. This is not a public XOS ABI. */
#ifndef XOS_TERMINAL_OWNER_EVIDENCE_H
#define XOS_TERMINAL_OWNER_EVIDENCE_H
typedef unsigned long long owner_u64;
struct owner_event { owner_u64 value[32]; };
enum owner_field {
    oe_kind, oe_pid, oe_parent, oe_owner, oe_actor, oe_child,
    oe_started_ns, oe_finished_ns, oe_generation, oe_threads, oe_blocked,
    oe_state, oe_terminal_send, oe_terminal_receive, oe_ready, oe_ack,
    oe_read_result, oe_read_errno, oe_exec_result, oe_exec_errno,
    oe_raw_send, oe_raw_receive, oe_file_byte, oe_pipe_result,
    oe_controller_preserved, oe_authority, oe_wait_status
};
struct owner_setup { owner_u64 value[32]; };
enum owner_setup_field {
    os_control, os_owner, os_actor, os_controller, os_child,
    os_baseline_pages, os_baseline_tasks, os_baseline_completions,
    os_before_pages, os_before_tasks, os_before_completions,
    os_owner_user_pages, os_owner_kernel_stack_pages, os_owner_channels,
    os_owner_pipe_references, os_pending_seen_ns, os_exit_started_ns
};
struct owner_report {
    owner_u64 magic, version, size, status;
    unsigned char nonce[32];
    struct owner_setup setup;
    struct owner_event events[3];
    owner_u64 observer_pid, observer_parent, free_pages, tasks, observer_thread_results;
    owner_u64 observer_user_pages, observer_kernel_stack_pages;
    owner_u64 observer_channels, observer_pipe_references, stable_ns;
    owner_u64 failure_line, failure_code;
    owner_u64 process_stats_query_result, thread_stats_query_result;
    owner_u64 observer_threads, observer_reserved_threads, observer_waiting_threads;
};
#define OWNER_REPORT_MAGIC 0x3152454e574f5458ULL
#define OWNER_REPORT_VERSION 2ULL
#endif
