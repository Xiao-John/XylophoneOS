// SPDX-License-Identifier: Apache-2.0
// A deliberately bounded parent/child transport experiment, not a broker.
#include <xos/sdk.hpp>
#include <cstdio>
#include <cstring>
using namespace xos;

struct Message { u32 version, sequence, kind, value; };
static_assert(sizeof(Message)==16);

static i64 pipe_read(u32 token,void *data,u64 size){return sdk::syscall(sys_pipe_read,token,reinterpret_cast<u64>(data),size);}
static i64 pipe_write(u32 token,const void *data,u64 size){return sdk::syscall(sys_pipe_write,token,reinterpret_cast<u64>(data),size);}
static i64 pipe_close(u32 token){return sdk::syscall(sys_pipe_close,token);}

static int provider(){
    Message request{};
    if(sdk::syscall(sys_pipe_wait,0)!=0)return 11;
    if(sdk::read(0,&request,sizeof(request))!=sizeof(request))return 12;
    if(request.version!=1 || request.sequence!=7 || request.kind!=1 || request.value!=42)return 13;
    // This is synthetic provider data, not a Qt/Browser scene.
    const Message reply{1,request.sequence,2,request.value+1};
    if(sdk::write(1,&reply,sizeof(reply))!=sizeof(reply))return 14;
    return 0;
}

int main(int argc,char **argv){
    if(argc>1 && std::strcmp(argv[1],"provider")==0)return provider();
    int failures=0;
    auto check=[&](bool ok,const char *name){std::printf("PIPE_PROBE %s=%s\n",name,ok?"PASS":"FAIL");if(!ok)++failures;};
    pipe_handles req{},res{};
    if(sdk::syscall(sys_pipe_create,reinterpret_cast<u64>(&req))!=0 ||
       sdk::syscall(sys_pipe_create,reinterpret_cast<u64>(&res))!=0){std::printf("PIPE_PROBE create=FAIL\n");return 1;}
    const char *args[]={"/bin/semantic-pipe.elf","provider"};
    sdk::spawn_options options{};options.stdio[0]=req.read_token;options.stdio[1]=res.write_token;
    const auto child=sdk::spawn_file_options(args[0],2,args,options);
    if(child<0){std::printf("PIPE_PROBE child_start=FAIL error=%lld\n",(long long)child);return 2;}
    check(sdk::syscall(sys_process_stdio,child,0,req.read_token)==process_error_state,"running_child_cannot_be_rewired");
    check(pipe_close(req.read_token)==0 && pipe_close(res.write_token)==0,"parent_closes_unused_ends");
    const Message request{1,7,1,42};
    check(pipe_write(req.write_token,&request,sizeof(request))==sizeof(request),"bounded_request_sent");
    Message reply{};
    const auto ready=sdk::syscall(sys_pipe_wait,res.read_token);
    const auto received=pipe_read(res.read_token,&reply,sizeof(reply));
    check(ready==0 && received==sizeof(reply) && reply.version==1 && reply.sequence==7 && reply.kind==2 && reply.value==43,"child_reply_received");
    check(pipe_close(req.write_token)==0,"request_closed");
    process_status status{};
    const auto waited=sdk::wait(child,status);
    check(waited==0 && status.outcome==process_outcome::exited && status.code==0,"provider_exit_observed");
    check(sdk::syscall(sys_pipe_wait,res.read_token)==0 && pipe_read(res.read_token,&reply,sizeof(reply))==0,"reply_eof_after_exit");
    check(pipe_close(res.read_token)==0 && pipe_read(res.read_token,&reply,sizeof(reply))<0,"closed_reference_rejected");
    pipe_handles pressure{};char data[process_pipe_bytes]{};
    if(sdk::syscall(sys_pipe_create,reinterpret_cast<u64>(&pressure))!=0){std::printf("PIPE_PROBE pressure_create=FAIL\n");return 3;}
    check(pipe_write(pressure.write_token,data,sizeof(data))==sizeof(data) &&
          pipe_write(pressure.write_token,data,1)==process_error_would_block,"bounded_queue_backpressure");
    check(pipe_read(pressure.read_token,data,sizeof(data))==sizeof(data),"queue_drain");
    check(pipe_close(pressure.read_token)==0 && pipe_write(pressure.write_token,data,1)==pipe_error_broken,"closed_reader_detected");
    check(pipe_close(pressure.write_token)==0,"pressure_pipe_closed");
    std::printf("PIPE_PROBE_DONE failures=%d\n",failures);
    return failures?1:0;
}
