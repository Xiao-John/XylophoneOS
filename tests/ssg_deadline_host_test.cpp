// SPDX-License-Identifier: Apache-2.0
#include <xos/thread_core.hpp>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <vector>

namespace {
using namespace xos;
struct io_step { u64 operation; i64 result; u64 after_ns; };
u64 now_ns;
std::vector<io_step> steps;
unsigned position, read_bytes, written_bytes, checks, failures;

void arrange(u64 start,std::initializer_list<io_step> planned) {
    now_ns=start;steps=planned;position=0;read_bytes=written_bytes=0;
}
void check(bool passed,const char *name) {
    ++checks;
    std::printf("SSG_DEADLINE %s=%s\n",name,passed?"PASS":"FAIL");
    if(!passed)++failures;
}
}

namespace xos::sdk {
i64 syscall(u64 number,u64 first,u64 second,u64 third) {
    if(number==sys_clock_monotonic)return static_cast<i64>(now_ns);
    if(number==sys_handle_write && first==2)return static_cast<i64>(third);
    if(position==steps.size() || steps[position].operation!=number){
        std::fprintf(stderr,"unexpected transport operation=%llu step=%u\n",
                     static_cast<unsigned long long>(number),position);
        std::abort();
    }
    const auto step=steps[position++];now_ns=step.after_ns;
    if(step.result>0 && (number==sys_pipe_read || number==sys_handle_read)){
        if(static_cast<u64>(step.result)>third)std::abort();
        std::memset(reinterpret_cast<void*>(second),'A',static_cast<unsigned>(step.result));
        read_bytes+=static_cast<unsigned>(step.result);
    }
    if(step.result>0 && (number==sys_pipe_write || number==sys_handle_write))
        written_bytes+=static_cast<unsigned>(step.result);
    return step.result;
}
}

#include "ssg_deadline_implementation.inc"

int main() {
    actual_sink sink;char bytes[4]{};
    using sink_state=actual_sink::io_state;
    using subscriber_state=actual_subscriber::read_state;
    constexpr auto blocked=process_error_would_block;

    arrange(10,{{sys_pipe_write,4,20}});
    check(sink.write_frame(bytes,4,100)==sink_state::complete && written_bytes==4,
          "event_before_deadline");
    arrange(10,{{sys_pipe_write,blocked,10},{sys_pipe_wait,0,99},{sys_pipe_write,4,99}});
    check(sink.write_frame(bytes,4,100)==sink_state::complete && written_bytes==4,
          "event_ready_before_deadline");
    arrange(10,{{sys_pipe_write,blocked,10},{sys_pipe_wait,0,101},{sys_pipe_write,4,101}});
    check(sink.write_frame(bytes,4,100)==sink_state::timeout && written_bytes==0 && position==2,
          "event_ready_after_deadline_not_sent");
    arrange(100,{{sys_pipe_write,4,100}});
    check(sink.write_frame(bytes,4,100)==sink_state::timeout && position==0,
          "event_deadline_equality_not_sent");

    arrange(10,{{sys_pipe_read,2,20},{sys_pipe_read,2,30}});
    check(sink.read_exact(bytes,4,100)==sink_state::complete && read_bytes==4,
          "ack_short_reads_before_deadline");
    arrange(10,{{sys_pipe_read,blocked,10},{sys_pipe_wait,0,101},{sys_pipe_read,4,101}});
    check(sink.read_exact(bytes,4,100)==sink_state::timeout && read_bytes==0 && position==2,
          "late_ack_ready_is_timeout");
    arrange(10,{{sys_pipe_read,2,101},{sys_pipe_read,2,101}});
    check(sink.read_exact(bytes,4,100)==sink_state::timeout && read_bytes==2 && position==1,
          "partial_ack_deadline_stops_reading");
    arrange(10,{{sys_pipe_read,4,101}});
    check(sink.read_exact(bytes,4,100)==sink_state::timeout && read_bytes==4,
          "ack_observed_after_deadline_remains_unknown");
    arrange(100,{{sys_pipe_read,4,100}});
    check(sink.read_exact(bytes,4,100)==sink_state::timeout && position==0,
          "ack_deadline_equality_not_consumed");
    arrange(10,{{sys_pipe_read,2,20},{sys_pipe_read,0,30}});
    check(sink.read_exact(bytes,4,100)==sink_state::incomplete && read_bytes==2,
          "ack_truncation_still_incomplete");
    arrange(10,{{sys_pipe_read,blocked,10},{sys_pipe_wait,thread_error_timeout,100}});
    check(sink.read_exact(bytes,4,100)==sink_state::timeout && read_bytes==0,
          "ack_kernel_timeout_preserved");

    arrange(10,{{sys_handle_read,2,20},{sys_handle_read,2,30}});
    check(actual_subscriber::read_exact(bytes,4,100,false)==subscriber_state::complete && read_bytes==4,
          "subscriber_short_reads_before_deadline");
    arrange(10,{{sys_handle_read,blocked,10},{sys_pipe_wait,0,101},{sys_handle_read,4,101}});
    check(actual_subscriber::read_exact(bytes,4,100,false)==subscriber_state::timeout && read_bytes==0,
          "subscriber_late_readiness_is_timeout");
    arrange(100,{{sys_handle_read,4,100}});
    check(actual_subscriber::read_exact(bytes,4,100,true)==subscriber_state::timeout && position==0,
          "subscriber_idle_session_deadline_checked");
    arrange(10,{{sys_handle_read,1,20},{sys_handle_read,3,200}});
    check(actual_subscriber::read_exact(bytes,4,100,true)==subscriber_state::complete && read_bytes==4,
          "subscriber_first_byte_starts_frame_budget");
    arrange(10,{{sys_handle_read,4,101}});
    check(actual_subscriber::read_exact(bytes,4,100,false)==subscriber_state::timeout && read_bytes==4,
          "subscriber_completion_after_deadline_rejected");
    arrange(10,{{sys_handle_read,0,20}});
    check(actual_subscriber::read_exact(bytes,4,100,true)==subscriber_state::eof,
          "subscriber_idle_eof_preserved");
    arrange(10,{{sys_handle_read,2,20},{sys_handle_read,0,30}});
    check(actual_subscriber::read_exact(bytes,4,100,false)==subscriber_state::truncated,
          "subscriber_partial_eof_preserved");

    constexpr u64 ack_deadline=actual_subscriber::frame_timeout_ns+10;
    constexpr auto ack_bytes=ssg_subscription::header_size+4;
    arrange(10,{{sys_handle_write,ack_bytes,20}});
    check(actual_subscriber::write_ack(1,ssg_subscription::ack_committed) && written_bytes==ack_bytes,
          "subscriber_ack_before_deadline");
    arrange(10,{{sys_handle_write,blocked,10},{sys_pipe_wait,0,ack_deadline+1},
                {sys_handle_write,ack_bytes,ack_deadline+1}});
    check(!actual_subscriber::write_ack(1,ssg_subscription::ack_committed) && written_bytes==0,
          "subscriber_ack_ready_after_deadline_not_sent");

    std::printf("SSG_DEADLINE_HOST checks=%u failures=%u\n",checks,failures);
    return failures?1:0;
}
