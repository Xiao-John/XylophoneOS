// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/sdk.hpp>
#include <xos/thread_core.hpp>
#include <QtCore/QByteArray>
#include <QtCore/QThread>
#include <limits>
#include <cstdio>
#include <pthread.h>

// Private experiment protocol, not an OS ABI. One request is in flight at a time.
// stdin (0) is the incoming pipe; stderr (2) is the outgoing pipe; stdout stays
// the diagnostic console. Length and sequence are unsigned little-endian u32.
namespace ssg_pipe {
constexpr unsigned max_request=4096, max_response=81920;
constexpr xos::u64 io_timeout_ns=30000000000ull;
inline void put32(char *p, unsigned v){for(unsigned i=0;i<4;i++)p[i]=char((v>>(8*i))&255);}
inline unsigned get32(const char *p){unsigned v=0;for(unsigned i=0;i<4;i++)v|=unsigned(static_cast<unsigned char>(p[i]))<<(8*i);return v;}

// sys_pipe_wait has no deadline. This helper waits on the existing monotonic
// wait-word deadline and closes both local routes on a stalled partial frame.
// Closing is terminal: it never retries or pretends a partial message succeeded.
class Watchdog final {
    alignas(4) xos::u32 state=0; // even=idle, odd=armed, reserved=terminal
    xos::u64 deadline=0;
    pthread_t thread{};
    bool started=false;
    static constexpr xos::u32 timed_out=0xfffffffeu, stopped=0xffffffffu;
    static void *entry(void *argument){static_cast<Watchdog *>(argument)->run();return nullptr;}
    // This worker only uses the mechanism-level wait and pipe syscalls.
    void run() {
        for(;;){
            const auto s=__atomic_load_n(&state,__ATOMIC_ACQUIRE);
            if(s==stopped)return;
            if(s==timed_out || !(s&1u)){xos::thread::wait(&state,s);continue;}
            const auto until=__atomic_load_n(&deadline,__ATOMIC_ACQUIRE);
            if(xos::thread::wait(&state,s,until)==xos::thread_error_timeout){
                auto expected=s;
                if(__atomic_compare_exchange_n(&state,&expected,timed_out,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
                    xos::sdk::close(0);xos::sdk::close(2);
                }
            }
        }
    }
public:
    Watchdog(){started=pthread_create(&thread,nullptr,entry,this)==0;if(!started)__atomic_store_n(&state,timed_out,__ATOMIC_RELEASE);}
    Watchdog(const Watchdog &)=delete;
    Watchdog &operator=(const Watchdog &)=delete;
    ~Watchdog(){
        __atomic_store_n(&state,stopped,__ATOMIC_RELEASE);xos::thread::wake(&state);
        // Qt's detached QThread can report finished before native TLS cleanup.
        // Joining the native worker prevents process exit from racing that cleanup.
        if(started && pthread_join(thread,nullptr)!=0)xos::sdk::exit(126);
    }
    bool arm(xos::u64 timeout=io_timeout_ns){
        auto s=__atomic_load_n(&state,__ATOMIC_ACQUIRE);
        if((s&1u) || s>=timed_out-2)return false;
        __atomic_store_n(&deadline,xos::thread::clock()+timeout,__ATOMIC_RELEASE);
        const bool ok=__atomic_compare_exchange_n(&state,&s,s+1,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);
        if(ok)xos::thread::wake(&state);
        return ok;
    }
    bool disarm(){
        auto s=__atomic_load_n(&state,__ATOMIC_ACQUIRE);
        if(!(s&1u) || s==stopped)return false;
        const bool ok=__atomic_compare_exchange_n(&state,&s,s+1,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);
        if(ok)xos::thread::wake(&state);
        return ok;
    }
    bool expired() const{return __atomic_load_n(&state,__ATOMIC_ACQUIRE)==timed_out;}
};

enum class Result { ok, eof, truncated, bad_frame, limit, io_error, timeout };
inline const char *name(Result r){switch(r){case Result::ok:return "OK";case Result::eof:return "EOF";case Result::truncated:return "TRUNCATED";case Result::bad_frame:return "BAD_FRAME";case Result::limit:return "LIMIT";case Result::timeout:return "TIMEOUT";default:return "IO_ERROR";}}
inline Result read_exact(char *p,unsigned length,bool initial=false){
    unsigned n=0;
    while(n<length){
        const auto r=xos::sdk::read(0,p+n,length-n);
        if(r>0){n+=unsigned(r);continue;}
        if(r==0)return n==0&&initial?Result::eof:Result::truncated;
        if(r!=xos::process_error_would_block)return Result::io_error;
        if(xos::sdk::syscall(xos::sys_pipe_wait,0)<0)return Result::io_error;
    }
    return Result::ok;
}
inline Result write_all(const char *p,unsigned length){
    unsigned n=0;bool logged_backpressure=false;
    while(n<length){
        const auto r=xos::sdk::write(2,p+n,length-n);
        if(r>0){n+=unsigned(r);continue;}
        if(r!=xos::process_error_would_block)return Result::io_error;
        if(!logged_backpressure){std::printf("SSG_PIPE_BACKPRESSURE pid=%llu remaining=%u\n",(unsigned long long)xos::sdk::pid(),length-n);logged_backpressure=true;}
        if(xos::sdk::syscall(xos::sys_pipe_wait,2,1)<0)return Result::io_error;
    }
    return Result::ok;
}
template<class Timer>
inline Result receive(QByteArray &body,unsigned &sequence,unsigned maximum,Timer &watch,bool idle_allowed){
    char header[12];
    // An idle provider is allowed to block indefinitely until the first byte.
    if(!idle_allowed && !watch.arm())return Result::timeout;
    auto r=read_exact(header,1,true);
    if(r!=Result::ok){if(!idle_allowed&&!watch.disarm()&&watch.expired())return Result::timeout;return r;}
    if(idle_allowed && !watch.arm())return Result::timeout;
    r=read_exact(header+1,11);
    if(r==Result::ok && QByteArray(header,4)!="SSG1")r=Result::bad_frame;
    unsigned size=0;
    if(r==Result::ok){size=get32(header+4);sequence=get32(header+8);if(!size || size>maximum)r=Result::limit;}
    if(r==Result::ok){body.resize(int(size));r=read_exact(body.data(),size);}
    if(!watch.disarm() && watch.expired())return Result::timeout;
    return r;
}
template<class Timer>
inline Result send(const QByteArray &body,unsigned sequence,unsigned maximum,Timer &watch){
    if(body.isEmpty() || unsigned(body.size())>maximum)return Result::limit;
    if(!watch.arm())return Result::timeout;
    char header[12]={'S','S','G','1'};put32(header+4,unsigned(body.size()));put32(header+8,sequence);
    auto r=write_all(header,sizeof(header));if(r==Result::ok)r=write_all(body.constData(),unsigned(body.size()));
    if(!watch.disarm() && watch.expired())return Result::timeout;
    return r;
}
}
