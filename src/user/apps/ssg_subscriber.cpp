// SPDX-License-Identifier: Apache-2.0
// Independent, read-only Consumer for the private SSG-P4A subscription prototype.
#include "../ssg/subscriber_state.hpp"
#include <xos/sdk.hpp>
#include <xos/thread_core.hpp>
#include <cstdio>
#include <cstring>

namespace {
using namespace xos;
using namespace ssg_subscription;
constexpr u64 frame_timeout_ns=5000000000ull;

enum class read_state { complete, eof, truncated, timeout, error };

template<class... Args>
void log_line(const char *format,Args... args) {
    char buffer[256]{};
    const int count=std::snprintf(buffer,sizeof(buffer),format,args...);
    if(count<=0)return;
    const unsigned length=static_cast<unsigned>(count>=static_cast<int>(sizeof(buffer))?sizeof(buffer)-1:count);
    (void)sdk::write(2,buffer,length);
}

read_state read_exact(char *data,unsigned length,u64 deadline,bool allow_idle_wait) {
    unsigned offset=0;
    u64 current_deadline=deadline;
    while(offset<length){
        if(thread::clock()>=current_deadline)return read_state::timeout;
        const auto result=sdk::syscall(sys_handle_read,0,reinterpret_cast<u64>(data+offset),length-offset);
        if(result>0){
            if(offset==0 && allow_idle_wait)current_deadline=thread::clock()+frame_timeout_ns;
            offset+=static_cast<unsigned>(result);
            continue;
        }
        if(result==0)return offset==0?read_state::eof:read_state::truncated;
        if(result!=process_error_would_block)return read_state::error;
        const auto waited=sdk::syscall(sys_pipe_wait,0,0,current_deadline);
        if(waited==thread_error_timeout)return read_state::timeout;
        if(waited<0)return read_state::error;
    }
    return thread::clock()<current_deadline?read_state::complete:read_state::timeout;
}

bool write_ack(unsigned sequence,unsigned status) {
    char frame[header_size+4]{};unsigned frame_size=0;
    if(!encode_ack(frame,sizeof(frame),sequence,status,frame_size))return false;
    const u64 deadline=thread::clock()+frame_timeout_ns;
    for(;;){
        if(thread::clock()>=deadline)return false;
        const auto result=sdk::syscall(sys_handle_write,u64{1}|pipe_write_atomic_flag,
            reinterpret_cast<u64>(frame),frame_size);
        if(result==static_cast<i64>(frame_size))return true;
        if(result!=process_error_would_block){
            log_line("P4A_ACK_WRITE result=%lld bytes=%u\n",(long long)result,frame_size);return false;
        }
        const auto waited=sdk::syscall(sys_pipe_wait,1,frame_size,deadline);
        if(waited<0){
            log_line("P4A_ACK_WAIT result=%lld bytes=%u\n",(long long)waited,frame_size);return false;
        }
    }
}

bool valid_instance(const char *value) {
    if(value==nullptr || std::strlen(value)!=32)return false;
    for(unsigned i=0;i<32;++i){
        const char c=value[i];
        if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;
    }
    return true;
}

int reject_frame(consumer_state &state,unsigned sequence,const char *reason) {
    state.require_resync(QString::fromLatin1(reason));
    log_line("P4A_SUBSCRIBER_RESET_REQUIRED reason=%s stream=%u\n",reason,sequence);
    if(sequence==0 || !write_ack(sequence,ack_rejected)){
        log_line("P4A_SUBSCRIBER_ACK status=UNKNOWN stream=%u\n",sequence);
        return 4;
    }
    log_line("P4A_SUBSCRIBER_ACK status=REJECTED stream=%u\n",sequence);
    return 3;
}

int run(const QString &browser_instance,const QString &notes_instance,unsigned duration_seconds,
        bool pause_before_read,bool capture_frames,bool wrong_ack_sequence,bool duplicate_ack) {
    if(sdk::syscall(sys_process_stdio,0,0)!=0 || sdk::syscall(sys_process_stdio,0,1)!=0 ||
       sdk::syscall(sys_process_stdio,0,2)!=1){
        log_line("P4A_SUBSCRIBER_ERROR reason=DEDICATED_PIPES_REQUIRED\n");return 2;
    }
    if(browser_instance==notes_instance){
        log_line("P4A_SUBSCRIBER_ERROR reason=SOURCE_INSTANCE_COLLISION\n");return 2;
    }
    consumer_state state(browser_instance,notes_instance);
    const u64 session_deadline=thread::clock()+(u64(duration_seconds)+5)*1000000000ull;
    log_line("P4A_SUBSCRIBER_READY protocol=%u pid=%llu slots=browser,notes read_fd=0 ack_fd=1\n",
             protocol_version,(unsigned long long)sdk::pid());
    if(pause_before_read)thread::sleep_until(thread::clock()+10000000000ull);
    unsigned received=0,acks_sent=0;
    for(;;){
        char header_bytes[header_size]{};
        const auto header_read=read_exact(header_bytes,sizeof(header_bytes),session_deadline,true);
        if(header_read==read_state::eof){
            // A clean close requires an initial accepted state from both prewired sources.
            const unsigned browser_events=state.source(browser_slot).local_sequence;
            const unsigned notes_events=state.source(notes_slot).local_sequence;
            if(browser_events==0 || notes_events==0){
                log_line("P4A_SUBSCRIBER_STOP reason=PREMATURE_EOF browser_events=%u notes_events=%u events=%u acks_sent=%u\n",
                         browser_events,notes_events,received,acks_sent);
                return 5;
            }
            log_line("P4A_SUBSCRIBER_STOP reason=SUPERVISOR_CLOSED events=%u acks_sent=%u\n",received,acks_sent);
            return 0;
        }
        if(header_read!=read_state::complete){
            const char *reason=header_read==read_state::timeout?"SESSION_DEADLINE":
                header_read==read_state::truncated?"TRUNCATED_HEADER":header_read==read_state::error?"PIPE_READ_ERROR":"EOF";
            return reject_frame(state,0,reason);
        }
        frame_header decoded{};
        if(!decode_header(header_bytes,event_kind,decoded)){
            const unsigned sequence=get_u32(header_bytes+12);
            return reject_frame(state,sequence,"HEADER_INVALID");
        }
        char payload[max_payload_size]{};
        const auto payload_read=read_exact(payload,decoded.payload_size,thread::clock()+frame_timeout_ns,false);
        if(payload_read!=read_state::complete){
            const char *reason=payload_read==read_state::timeout?"TRUNCATED_PAYLOAD_TIMEOUT":
                payload_read==read_state::truncated?"TRUNCATED_PAYLOAD":"PAYLOAD_READ_ERROR";
            return reject_frame(state,decoded.stream_sequence,reason);
        }
        char full_frame[xos::process_pipe_bytes]{};
        std::memcpy(full_frame,header_bytes,header_size);
        std::memcpy(full_frame+header_size,payload,decoded.payload_size);
        if(capture_frames && !emit_frame_capture("RX",decoded.stream_sequence,full_frame,
                                                  header_size+decoded.payload_size,2))
            return reject_frame(state,decoded.stream_sequence,"RX_CAPTURE_FAILED");
        if(!verify_payload(payload,decoded))return reject_frame(state,decoded.stream_sequence,"CHECKSUM_INVALID");
        if(!state.accept(decoded.source_slot,decoded.stream_sequence,payload,decoded.payload_size))
            return reject_frame(state,decoded.stream_sequence,state.error().toUtf8().constData());

        const auto &source=state.source(decoded.source_slot);
        ++received;
        log_line("P4A_RECEIVE stream=%u slot=%s local=%u type=%s state=%s revision=%s bytes=%u frame_hash=%08x\n",
                 decoded.stream_sequence,source.slot.toUtf8().constData(),source.local_sequence,
                 source.last_event_type.toUtf8().constData(),source.state.toUtf8().constData(),
                 source.revision.toUtf8().constData(),header_size+decoded.payload_size,
                 payload_checksum(full_frame,header_size+decoded.payload_size));
        log_line("P4A_SUBSCRIBER_COMMIT stream=%u slot=%s state=%s commit=IN_MEMORY_READ_ONLY_STATE ack=PENDING\n",
                 decoded.stream_sequence,source.slot.toUtf8().constData(),source.state.toUtf8().constData());
        const unsigned ack_sequence=wrong_ack_sequence && received==1
            ?decoded.stream_sequence+1:decoded.stream_sequence;
        if(!write_ack(ack_sequence,ack_committed)){
            log_line("P4A_SUBSCRIBER_ACK status=UNKNOWN stream=%u state=%s\n",
                     decoded.stream_sequence,source.state.toUtf8().constData());return 4;
        }
        ++acks_sent;
        log_line("P4A_SUBSCRIBER_ACK status=SENT stream=%u ack_sequence=%u proof=IN_MEMORY_READ_ONLY_STATE\n",
                 decoded.stream_sequence,ack_sequence);
        if(duplicate_ack && received==1){
            if(!write_ack(ack_sequence,ack_committed)){
                log_line("P4A_SUBSCRIBER_ACK status=UNKNOWN stream=%u state=%s\n",
                         decoded.stream_sequence,source.state.toUtf8().constData());return 4;
            }
            ++acks_sent;
            log_line("P4A_SUBSCRIBER_ACK status=SENT stream=%u ack_sequence=%u duplicate=1\n",
                     decoded.stream_sequence,ack_sequence);
        }
    }
}
}

int main(int argc,char **argv) {
    if(argc<4 || argc>8 || !valid_instance(argv[1]) || !valid_instance(argv[2])){
        log_line("P4A_SUBSCRIBER_ERROR reason=INVALID_STARTUP\n");return 2;
    }
    bool valid=false;
    const auto duration=QString::fromLocal8Bit(argv[3]).toUInt(&valid);
    if(!valid || duration<1 || duration>3600){
        log_line("P4A_SUBSCRIBER_ERROR reason=INVALID_DURATION\n");return 2;
    }
    bool pause=false,capture=false,wrong_ack=false,duplicate_ack=false;
    for(int i=4;i<argc;++i){
        if(std::strcmp(argv[i],"--test-pause-reader")==0)pause=true;
        else if(std::strcmp(argv[i],"--test-capture-frame")==0)capture=true;
        else if(std::strcmp(argv[i],"--test-wrong-ack-sequence")==0)wrong_ack=true;
        else if(std::strcmp(argv[i],"--test-duplicate-ack")==0)duplicate_ack=true;
        else {log_line("P4A_SUBSCRIBER_ERROR reason=UNKNOWN_STARTUP_OPTION\n");return 2;}
    }
    return run(QString::fromLatin1(argv[1]),QString::fromLatin1(argv[2]),duration,pause,capture,wrong_ack,duplicate_ack);
}
