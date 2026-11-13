// SPDX-License-Identifier: Apache-2.0
// The interrupt gate serializes object publication with IRQ delivery and exit.
void granted_memory_release(void*, u64 physical) {
    if (release_user_page(physical) != memory_result::none) halt();
}
bool granted_memory_map(void*, u64 pid, u64 address, u64 physical, bool writable) {
    auto* process = task_by_pid(pid);
    if (!process || process->user_pages >= process_max_pages ||
        retain_user_page(physical) != memory_result::none) return false;
    if (map_page_in(process->cr3, address, physical, {writable, false, true}) != memory_result::none) {
        (void)release_user_page(physical);
        vm_prune_empty_page_tables_in(process->cr3, address);
        return false;
    }
    ++process->user_pages;
    return true;
}
void granted_memory_unmap(void*, u64 pid, u64 address) {
    auto* process = task_by_pid(pid);
    u64 physical = 0;
    if (!process || unmap_page_in(process->cr3, address, &physical) != memory_result::none ||
        release_user_page(physical) != memory_result::none) halt();
    --process->user_pages;
    vm_prune_empty_page_tables_in(process->cr3, address);
}
bool granted_memory_pinned(void*, u64 pid, u64 begin, u64 end) {
    return pinned_range(task_by_pid(pid), begin, end);
}

void cancel_granted_memory_pins(void*, u64 pid, u64 begin, u64 end) {
    for (auto& thread : threads) {
        if (!thread.process || thread.process->pid != pid ||
            thread.state == thread_state::free || thread.state == thread_state::dead) continue;
        bool overlap = thread.user_pin.overlaps(begin, end);
        for (const auto& pin : thread.ipc_v1_pins) overlap = overlap || pin.overlaps(begin, end);
        if (!overlap) continue;
        if (thread.state == thread_state::running) {
            ipc_v1_unpin(thread); thread.user_pin.clear();
            continue;
        }
        const bool device = thread.wait_kind == thread_wait_kind::device_irq;
        const bool ipc = thread.wait_kind == thread_wait_kind::ipc_v1_call ||
            thread.wait_kind == thread_wait_kind::ipc_v1_receive ||
            thread.wait_kind == thread_wait_kind::ipc_v1_notification ||
            thread.wait_kind == thread_wait_kind::ipc_v1_wait_set;
        if (thread.wait_kind == thread_wait_kind::ipc_v1_call && thread.ipc_v1_call_slot < ipc_v1_max_pending_calls) {
            auto& call = ipc_v1_calls[thread.ipc_v1_call_slot];
            if (call.caller_thread_slot == static_cast<u32>(&thread - threads)) call = {};
        }
        if (thread.wait_kind == thread_wait_kind::ipc_v1_receive && thread.ipc_v1_token) {
            for (u32 i = 0; i < ipc_v1_max_pending_calls; ++i) {
                auto& call = ipc_v1_calls[i];
                if (call.state == ipc_v1_call_state::delivered && call.reply_token == thread.ipc_v1_token) {
                    ipc_v1_wake_call(i, static_cast<i64>(ipc_v1_error::closed)); call = {};
                }
            }
        }
        if (thread.wait_kind == thread_wait_kind::join) {
            for (auto& target : threads)
                if (target.process == thread.process && target.tid == thread.wait_target && target.joiner == thread.tid)
                    target.joiner = 0;
        }
        ipc_v1_unpin(thread);
        thread.user_pin.clear();
        // The revoked output is no longer writable: do not run deferred copyout.
        thread.wait_kind = thread_wait_kind::none;
        ready_with(thread, ipc ? static_cast<i64>(ipc_v1_error::address) :
                   (device ? device_fault : thread_error_address));
    }
}

bool device_grant_authorized(void*, u64 issuer, u64 target) {
    if (!current || issuer != current->pid || !current->supervisor || current->closing) return false;
    const auto* child = owned_process(target);
    return child && child->state == task_state::building && !child->closing && !child->replacement_pending;
}
i64 device_inspect_backend(void*, u64 instance, u64 rights, device_grants::description& out) {
    return platform::device_inspect(instance, rights, out);
}
bool device_memory_enable_backend(void*, u64 instance) { return platform::device_memory_enable(instance); }
bool device_dma_start_backend(void*, u64 instance) { return platform::device_dma_start(instance); }
bool device_dma_stop_backend(void*, u64 instance) { return platform::device_dma_stop(instance); }
void device_disable_backend(void*, u64 instance) { platform::device_disable(instance); }
bool device_dma_allocate_backend(void*, u32 pages, u64 alignment, u64& physical) {
    return allocate_contiguous_user_pages(pages, alignment, &physical) == memory_result::none;
}
bool device_map_backend(void* context, u64 pid, u64 address, u64 physical, bool write, bool dma) {
    if (dma) return granted_memory_map(context, pid, address, physical, write);
    auto* process = task_by_pid(pid);
    if (!process || process->user_pages >= process_max_pages) return false;
    if (map_device_page_in(process->cr3, address, physical, write) != memory_result::none) {
        vm_prune_empty_page_tables_in(process->cr3, address); return false;
    }
    ++process->user_pages; return true;
}
void device_unmap_backend(void* context, u64 pid, u64 address, bool dma) {
    if (dma) { granted_memory_unmap(context, pid, address); return; }
    auto* process = task_by_pid(pid);
    if (!process || unmap_page_in(process->cr3, address, nullptr) != memory_result::none) halt();
    --process->user_pages;
    vm_prune_empty_page_tables_in(process->cr3, address);
}
void device_mask_backend(void*, u8 irq) { platform::irq_mask(irq); }
bool device_unmask_backend(void*, u64 instance, u8 irq) { return platform::device_irq_enable(instance, irq); }
void device_wake_backend(void*, u64 event, i64 result, const device_output& out) {
    for (auto& thread : threads) {
        if ((thread.state == thread_state::blocked || thread.state == thread_state::ready) &&
            thread.wait_kind == thread_wait_kind::device_irq && thread.device_event_token == event) {
            thread.device_result = out;
            ready_with(thread, result);
        }
    }
}
device_grants::backend device_backend{nullptr, device_grant_authorized, device_inspect_backend,
    device_memory_enable_backend, device_dma_start_backend, device_dma_stop_backend, device_disable_backend,
    device_dma_allocate_backend, granted_memory_release, device_map_backend, device_unmap_backend,
    granted_memory_pinned, cancel_granted_memory_pins, device_mask_backend, device_unmask_backend, device_wake_backend};
void device_revoke_process(u64 pid) { device_store.revoke_process(device_backend, pid); }

union device_input_snapshot {
    device_grant_input grant;
    device_resource_input resource;
    device_map_input map;
    device_dma_input dma;
    device_irq_input irq;
};
i64 read_device_request(interrupt_frame* frame, device_request& request, device_input_snapshot& input) {
    if (frame->rsi || frame->rdx || (frame->rdi & 7)) return device_invalid;
    if (!user_range_ok(frame->rdi, sizeof(request), false)) return device_fault;
    copy_from_user(&request, frame->rdi, sizeof(request));
    const auto operation = static_cast<u32>(request.operation);
    if (request.version != 1 || request.size != sizeof(request) || request.flags || request.reserved ||
        operation < 1 || operation > 11 || (request.deadline_ns && request.operation != device_operation::irq_wait))
        return device_invalid;
    u32 input_length = 0;
    bool output = false;
    switch (request.operation) {
    case device_operation::grant: input_length = sizeof(device_grant_input); output = true; break;
    case device_operation::query: case device_operation::irq_bind:
        input_length = sizeof(device_resource_input); output = true; break;
    case device_operation::map: input_length = sizeof(device_map_input); output = true; break;
    case device_operation::dma_alloc: input_length = sizeof(device_dma_input); output = true; break;
    case device_operation::irq_wait: input_length = sizeof(device_irq_input); output = true; break;
    case device_operation::irq_ack: input_length = sizeof(device_irq_input); break;
    default: break;
    }
    if (request.input_length != input_length || request.output_length != (output ? sizeof(device_output) : 0) ||
        (!input_length && request.input_address) || (!output && request.output_address) ||
        (request.input_address & 7) || (request.output_address & 7) ||
        ((request.operation == device_operation::grant) != (request.object_token == 0))) return device_invalid;
    if (input_length) {
        if (!user_range_ok(request.input_address, input_length, false)) return device_fault;
        copy_from_user(&input, request.input_address, input_length);
    }
    if ((request.operation == device_operation::query || request.operation == device_operation::irq_bind) &&
        input.resource.reserved) return device_invalid;
    if ((request.operation == device_operation::irq_wait || request.operation == device_operation::irq_ack) &&
        input.irq.reserved) return device_invalid;
    if (output && (!user_range_ok(request.output_address, sizeof(device_output), true) ||
        !current_thread->ipc_v1_pins[0].set(request.output_address, sizeof(device_output)))) return device_fault;
    return 0;
}

void* device_authorize_syscall(interrupt_frame* frame) {
    device_request request{};
    device_input_snapshot input{};
    device_output out{};
    i64 result = read_device_request(frame, request, input);
    if (result) { frame->rax = static_cast<u64>(result); return frame; }
    const u64 pid = current->pid, token = request.object_token;
    switch (request.operation) {
    case device_operation::grant: result = device_store.grant(device_backend, pid, input.grant, out); break;
    case device_operation::query: result = device_store.query(pid, token, input.resource.index, out); break;
    case device_operation::map: result = device_store.map(device_backend, pid, token, input.map, out); break;
    case device_operation::unmap: result = device_store.unmap(device_backend, pid, token); break;
    case device_operation::dma_alloc: result = device_store.dma_allocate(device_backend, pid, token, input.dma, out); break;
    case device_operation::dma_release: result = device_store.dma_release(device_backend, pid, token); break;
    case device_operation::irq_bind: result = device_store.irq_bind(device_backend, pid, token, input.resource.index, out); break;
    case device_operation::irq_wait:
        result = device_store.irq_wait(pid, token, input.irq.sequence, out);
        if (result == device_busy) {
            if (!request.deadline_ns || thread_deadline_reached(clock::monotonic_ns(), request.deadline_ns)) result = device_timeout;
            else {
                current_thread->device_result = {};
                current_thread->device_event_token = token;
                current_thread->wait_buffer = request.output_address;
                current_thread->deadline_ns = request.deadline_ns;
                current_thread->wait_kind = thread_wait_kind::device_irq;
                current_thread->state = thread_state::blocked;
                return schedule(frame);
            }
        }
        break;
    case device_operation::irq_ack: result = device_store.irq_ack(device_backend, pid, token, input.irq.sequence); break;
    case device_operation::revoke: result = device_store.close(device_backend, pid, token, true); break;
    case device_operation::close: result = device_store.close(device_backend, pid, token, false); break;
    }
    if (request.output_length) {
        if (!current_thread->ipc_v1_pins[0].active()) result = device_fault;
        else { if (result) out = {}; copy_to_user(request.output_address, &out, sizeof(out)); }
        current_thread->ipc_v1_pins[0].clear();
    }
    frame->rax = static_cast<u64>(result); return frame;
}
