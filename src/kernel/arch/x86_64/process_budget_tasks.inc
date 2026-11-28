// SPDX-License-Identifier: Apache-2.0
// Included after the task/resource tables and user-copy primitives. All calls
// run under the existing non-preemptible syscall/continuation gate.
struct process_budget_domain {
    u64 id, owner_pid;
    process_budget_vector limits;
};
process_budget_domain process_budgets[32];
u64 next_process_budget_id = 1;

bool budget_within(const process_budget_vector& used, const process_budget_vector& limit) {
    return used.processes <= limit.processes && used.pages <= limit.pages &&
        used.threads <= limit.threads && used.ipc_objects <= limit.ipc_objects &&
        used.names <= limit.names && used.pipes <= limit.pipes;
}
process_budget_vector budget_add(process_budget_vector a, const process_budget_vector& b) {
    // All values derive from fixed kernel tables or validated system bounds.
    a.processes += b.processes; a.pages += b.pages; a.threads += b.threads;
    a.ipc_objects += b.ipc_objects; a.names += b.names; a.pipes += b.pipes;
    return a;
}
template<class F> void budget_visit_ipc(F visitor) {
    for (auto& object : ipc_v1_endpoints) if (object.used) visitor(object);
    for (auto& object : ipc_v1_notifications) if (object.used) visitor(object);
    for (auto& object : ipc_v1_wait_sets) if (object.used) visitor(object);
    for (auto& object : ipc_v1_grants) if (object.used) visitor(object);
}
process_budget_vector budget_attributed(const process_record& task, bool objects = true) {
    process_budget_vector result{};
    result.processes = task.replacement_pending ? 0 : 1;
    result.pages = u64{task.user_pages} + task.budget_reserved_pages;
    if (!task.replacement_pending) {
        for (const auto& thread : threads)
            if (thread.process == &task && thread.state != thread_state::free) ++result.threads;
    }
    for (const auto& endpoint : endpoints)
        if (endpoint.used && endpoint.owner_pid == task.pid &&
            (endpoint.generic_channel || (endpoint.generic && endpoint.handle == endpoint.channel_id))) ++result.ipc_objects;
    for (const auto& name : ipc_names)
        if (name.used && name.owner_pid == task.pid) ++result.names;
    if (objects) {
        for (const auto& pipe : pipes)
            if (pipe.used && pipe.owner_pid == task.pid) ++result.pipes;
        budget_visit_ipc([&](const auto& object) {
            if (object.owner_pid == task.pid) ++result.ipc_objects;
        });
        for (const auto& grant : ipc_v1_grants)
            if (grant.used && grant.owner_pid == task.pid) result.pages += grant.page_count;
    }
    return result;
}
process_budget_vector budget_usage(u64 bit) {
    process_budget_vector result{};
    for (const auto& task : tasks) {
        if (task.state == task_state::free || !(task.budget_mask & bit)) continue;
        auto own = budget_attributed(task, false);
        own.pipes = 0; // A pipe is charged once to its original domain set.
        result = budget_add(result, own);
    }
    // Keep pipe charges after the creator exits, until the last alias closes.
    for (const auto& pipe : pipes)
        if (pipe.used && (pipe.budget_mask & bit)) ++result.pipes;
    budget_visit_ipc([&](const auto& object) {
        if (object.budget_mask & bit) ++result.ipc_objects;
    });
    for (const auto& grant : ipc_v1_grants)
        if (grant.used && (grant.budget_mask & bit)) result.pages += grant.page_count;
    return result;
}
bool budget_admit(const process_record& owner, process_budget_vector addition) {
    for (u32 i = 0; i < 32; ++i) {
        if (!(owner.budget_mask & (u64{1} << i))) continue;
        if (!process_budgets[i].id ||
            !budget_within(budget_add(budget_usage(u64{1} << i), addition), process_budgets[i].limits))
            return false;
    }
    return true;
}
void budget_collect() {
    u64 referenced = 0;
    for (const auto& task : tasks)
        if (task.state != task_state::free) referenced |= task.budget_mask;
    for (const auto& pipe : pipes)
        if (pipe.used) referenced |= pipe.budget_mask;
    budget_visit_ipc([&](const auto& object) { referenced |= object.budget_mask; });
    for (u32 i = 0; i < 32; ++i)
        if (!(referenced & (u64{1} << i))) process_budgets[i] = {};
}
i64 budget_set(process_record& target, u64 address) {
    if (!user_range_ok(address, sizeof(process_budget_config), false)) return process_error_invalid;
    process_budget_config request{};
    copy_from_user(&request, address, sizeof(request));
    if (request.version != process_budget_version || request.size != sizeof(request) || request.reserved)
        return process_error_invalid;
    // A fresh local domain can only narrow every inherited domain. No mode
    // clears/replaces an ancestor; a fork never copies fresh quota credits.
    const process_budget_vector system_bounds{8, 8 * u64{process_max_pages} + ipc_v1_max_grants_system * u64{ipc_v1_max_grant_pages}, thread_max_total,
                                               max_endpoints + ipc_v1_max_endpoints_system + ipc_v1_max_notifications_system +
                                               ipc_v1_max_wait_sets_system + ipc_v1_max_grants_system, 8, process_max_pipes};
    if (!request.limits.processes || !request.limits.threads ||
        !budget_within(request.limits, system_bounds)) return process_error_invalid;
    if (target.budget_domain_id || target.replacement_pending || target.closing ||
        target.continuation.active()) return process_error_state;
    if (&target != current && (target.parent != current->pid || target.state != task_state::building))
        return process_error_denied;
    // Self-restriction is allowed before descendants exist. Restricting an
    // existing subtree without accounting its inherited aliases is forbidden.
    for (const auto& task : tasks)
        if (task.state != task_state::free && task.parent == target.pid) return process_error_busy;
    for (u32 i = 0; i < 32; ++i)
        if ((target.budget_mask & (u64{1} << i)) &&
            !budget_within(request.limits, process_budgets[i].limits)) return process_error_delegation;
    if (!budget_within(budget_attributed(target), request.limits)) return process_error_resources;
    budget_collect();
    if (!next_process_budget_id) return process_error_resources;
    for (u32 i = 0; i < 32; ++i) {
        if (process_budgets[i].id) continue;
        const u64 bit = u64{1} << i;
        process_budgets[i] = {next_process_budget_id++, target.pid, request.limits};
        target.budget_mask |= bit;
        target.budget_domain_id = process_budgets[i].id;
        for (auto& pipe : pipes)
            if (pipe.used && pipe.owner_pid == target.pid) pipe.budget_mask |= bit;
        budget_visit_ipc([&](auto& object) {
            if (object.owner_pid == target.pid) object.budget_mask |= bit;
        });
        return 0;
    }
    return process_error_resources;
}
i64 budget_query(const process_record& target, u64 address) {
    if (!user_range_ok(address, sizeof(process_budget_snapshot), false)) return process_error_invalid;
    process_budget_snapshot request{};
    copy_from_user(&request, address, sizeof(request));
    const process_budget_vector zero{};
    if (request.version != process_budget_version || request.size != sizeof(request) ||
        request.owner_pid || request.pid || request.image_generation || request.flags ||
        !budget_within(request.limits, zero) || !budget_within(request.usage, zero) ||
        !budget_within(request.attributed, zero)) return process_error_invalid;
    const process_budget_domain* domain = nullptr;
    u64 bit = 0;
    for (u32 i = 0; i < 32; ++i) {
        if (!(target.budget_mask & (u64{1} << i))) continue;
        const auto& candidate = process_budgets[i];
        if (request.domain_id ? candidate.id == request.domain_id : !domain || candidate.id > domain->id) {
            domain = &candidate; bit = u64{1} << i;
        }
    }
    if (request.domain_id && !domain) return process_error_denied;
    if (!user_range_ok(address, sizeof(request), true)) return process_error_invalid;
    process_budget_snapshot output{};
    output.version = process_budget_version; output.size = sizeof(output);
    output.pid = target.pid; output.image_generation = target.image_generation;
    output.attributed = budget_attributed(target);
    if (domain) {
        output.domain_id = domain->id; output.owner_pid = domain->owner_pid;
        output.flags = process_budget_active; output.limits = domain->limits; output.usage = budget_usage(bit);
    }
    copy_to_user(address, &output, sizeof(output));
    return 0;
}
