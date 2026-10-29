// SPDX-License-Identifier: Apache-2.0
// Scheduler/IPC adapter only. Hardware and validation stay in display/PS2 modules.
u64 display_service_pid, display_client_pid, display_focus_pid;
u32 display_request_handle, display_response_handle;
bool display_delivered, display_presented;

bool display_endpoint(u64 handle) {
    return handle!=0 && (handle==display_request_handle || handle==display_response_handle);
}
void display_wake(u64 handle, i64 result) {
    for(auto& thread:threads) {
        if(thread.state==thread_state::blocked && thread.wait_kind==thread_wait_kind::display &&
           (handle==~u64{0} || thread.wait_target==handle)) {ready_with(thread,result);}
    }
}
void display_drop_client() {
    display_wake(~u64{0},display_unavailable);
    for(auto& endpoint:endpoints) {
        if(display_endpoint(endpoint.handle)){endpoint=endpoint_record{};}
    }
    display_request_handle=0;display_response_handle=0;display_client_pid=0;display_focus_pid=0;
    display_delivered=false;display_presented=false;display::input_reset(false);
}
void display_release(u64 pid) {
    if(pid==display_client_pid || pid==display_service_pid){display_drop_client();}
    if(pid==display_service_pid){display_service_pid=0;}
}

// Presented bytes come from the authenticated channel sender, never a user PID.
// Copy the fixed descriptor from the kernel IPC snapshot, preflight every source
// page before the first device write. The single-core non-preemptible syscall
// prevents any same-process thread from unmapping or mutating it mid-copy.
i64 display_present_channel(u64 handle) {
    if(current->pid!=display_service_pid || handle!=display_request_handle ||
       !display_delivered || display_presented || display_focus_pid!=display_client_pid) {return display_denied;}
    const auto* endpoint=endpoint_for(handle);
    if(endpoint==nullptr || endpoint->length!=sizeof(display_request)){return display_invalid;}
    display_request request{};copy_bytes(&request,endpoint->data,sizeof(request));
    if(request.version!=1 || request.size!=sizeof(request) || request.reserved!=0 ||
       request.operation!=display_operation::present || !display::valid(request.present)){return display_invalid;}
    auto* client=task_by_pid(display_client_pid);
    const auto& p=request.present;
    if(client==nullptr || client->closing ||
       !space_range_ok(client->cr3,p.pixels,p.length,false)){return display_fault;}
    const auto screen=display::mode();
    for(u32 row=0;row<p.rect.height;++row) {
        const u64 offset=u64{row+p.rect.y}*p.stride+u64{p.rect.x}*4;
        u64 source=p.pixels+offset, destination=u64{row+p.rect.y}*screen.stride+u64{p.rect.x}*4;
        u64 remaining=u64{p.rect.width}*4;
        while(remaining!=0) {
            const u64 in_page=source&(page_size-1);
            const u64 amount=remaining<page_size-in_page?remaining:page_size-in_page;
            u64 physical=0;page_permissions permissions{};
            (void)query_page_in(client->cr3,source&~(page_size-1),&physical,&permissions);
            display::write(destination,reinterpret_cast<const u8*>(physical+in_page),amount);
            source+=amount;destination+=amount;remaining-=amount;
        }
    }
    if(!display::commit(p.rect)){return display_unavailable;}
    display_presented=true;return 0;
}

void* display_syscall(interrupt_frame* frame) {
    i64 result=display_invalid;
    const u64 second=frame->rsi,third=frame->rdx;
    if(frame->rax==sys_display_present){
        result=second==0 && third==0?display_present_channel(frame->rdi):display_invalid;
    } else switch(static_cast<display_action>(frame->rdi)) {
    case display_action::mode: {
        if(third!=0){break;}
        if(!display::available()){result=display_unavailable;break;}
        if(!user_range_ok(second,sizeof(display_mode),true)){result=display_fault;break;}
        const auto mode=display::mode();copy_to_user(second,&mode,sizeof(mode));result=0;break;
    }
    case display_action::grant_service: {
        if(!current->supervisor){result=display_denied;break;}
        if(third!=0){break;}
        auto* service=owned_process(second);
        if(service==nullptr || service->closing || service->block_access ||
           service->threads_enabled || second==display_client_pid){result=display_denied;break;}
        if(display_service_pid!=0){result=display_busy;break;}
        if(!display::available()){result=display_unavailable;break;}
        display_service_pid=second;service->spawn_depth=0;
        // The display role has no files/block/constructor authority.
        for(auto& endpoint:endpoints){
            if(endpoint.used && (endpoint.handle==service->session_request_handle ||
               endpoint.handle==service->session_response_handle)){endpoint=endpoint_record{};}
        }
        service->session_request_handle=0;service->session_response_handle=0;
        service->send_handle=0;service->recv_handle=0;
        result=0;break;
    }
    case display_action::connect: {
        if(third!=0){break;}
        if(!user_range_ok(second,sizeof(display_channel),true)){result=display_fault;break;}
        if(!display::available() || display_service_pid==0){result=display_unavailable;break;}
        if(current->pid==display_service_pid || current->supervisor || current->block_access){result=display_denied;break;}
        if(display_client_pid!=0){result=display_busy;break;}
        const u32 request=endpoint_attach(display_service_pid,current->pid,current->pid,sizeof(display_request));
        const u32 response=endpoint_attach(current->pid,display_service_pid,current->pid,sizeof(display_reply));
        if(request==0 || response==0) {
            if(auto* e=endpoint_for(request)){*e=endpoint_record{};}
            if(auto* e=endpoint_for(response)){*e=endpoint_record{};}
            result=display_resources;break;
        }
        display_request_handle=request;display_response_handle=response;
        display_client_pid=current->pid;display_focus_pid=current->pid;display::input_reset(true);
        const display_channel channel{request,response,current->pid};
        copy_to_user(second,&channel,sizeof(channel));display_wake(0,0);result=0;break;
    }
    case display_action::accept: {
        if(current->pid!=display_service_pid){result=display_denied;break;}
        if(third!=0){break;}
        if(!user_range_ok(second,sizeof(display_channel),true)){result=display_fault;break;}
        if(display_client_pid==0){result=display_again;break;}
        const display_channel channel{display_request_handle,display_response_handle,display_client_pid};
        copy_to_user(second,&channel,sizeof(channel));result=0;break;
    }
    case display_action::wait: {
        if(third!=0){break;}
        if(second==0 && current->pid==display_service_pid) {
            if(display_client_pid!=0){result=0;break;}
        } else if(second==0 && current->pid==display_focus_pid) {
            if(display::input_pending()){result=0;break;}
        } else {
            const auto* e=endpoint_for(second);
            if(!display_endpoint(second) || e==nullptr || e->receiver_pid!=current->pid){result=display_denied;break;}
            if(e->pending){result=0;break;}
        }
        if(second==0 && current->pid!=display_service_pid && current->pid!=display_focus_pid){result=display_denied;break;}
        frame->rax=0;current_thread->wait_kind=thread_wait_kind::display;
        current_thread->wait_target=second;current_thread->state=thread_state::blocked;
        return schedule(frame);
    }
    case display_action::disconnect:
        if(second!=0 || third!=0){break;}
        if(current->pid!=display_client_pid){result=display_denied;break;}
        display_drop_client();result=0;break;
    case display_action::input: {
        if(current->pid!=display_service_pid || display_focus_pid==0){result=display_denied;break;}
        if(third!=0){break;}
        if(!user_range_ok(second,sizeof(display_event),true)){result=display_fault;break;}
        display_event event{};
        if(!display::input_read(event)){result=display_again;break;}
        copy_to_user(second,&event,sizeof(event));result=0;break;
    }
    case display_action::focus:
        if(current->pid!=display_service_pid){result=display_denied;break;}
        if(third!=0 || (second!=0 && second!=display_client_pid)){break;}
        display_focus_pid=second;display::input_reset(second!=0);result=0;break;
    case display_action::shutdown:
        if(current->pid!=display_service_pid){result=display_denied;break;}
        if(second!=0 || third!=0){break;}
        display_release(current->pid);result=0;break;
    case display_action::service_info:
        if(second!=0 || third!=0){break;}
        result=static_cast<i64>(display_service_pid);break;
    }
    frame->rax=static_cast<u64>(result);return frame;
}
