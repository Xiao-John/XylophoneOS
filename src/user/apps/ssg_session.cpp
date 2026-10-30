// SPDX-License-Identifier: Apache-2.0
// Restricted session parent. The shell must explicitly delegate child-spawn.
#include <xos/sdk.hpp>
#include <cstdio>
#include <cstring>
using namespace xos;
static void close_pipe(u32 token){if(token)sdk::syscall(sys_pipe_close,token);}
int main(int argc,char **argv){
    const char *document=argc>1?argv[1]:"/ssg.txt";
    const char *mode=argc>2?argv[2]:"scenario";
    u8 random[16]{};char instance[33]{};const char hex[]="0123456789abcdef";
    if(sdk::syscall(sys_random_bytes,reinterpret_cast<u64>(random),sizeof(random))!=0){std::printf("SSG_SESSION random=FAIL\n");return 2;}
    for(unsigned i=0;i<sizeof(random);++i){instance[i*2]=hex[random[i]>>4];instance[i*2+1]=hex[random[i]&15];}
    pipe_handles request{},response{};
    if(sdk::syscall(sys_pipe_create,reinterpret_cast<u64>(&request))!=0){std::printf("SSG_SESSION pipe=FAIL\n");return 2;}
    if(sdk::syscall(sys_pipe_create,reinterpret_cast<u64>(&response))!=0){close_pipe(request.read_token);close_pipe(request.write_token);return 2;}
    sdk::spawn_options client_options{};client_options.stdio[0]=response.read_token;client_options.stdio[2]=request.write_token;
    const char *client_args[16]={"/bin/ssg-consumer.elf",mode};unsigned count=2;bool text_scope=false,browser=false,local_probe=false;
    for(int i=3;i<argc;i++){
        if(std::strcmp(argv[i],"--text")==0)text_scope=true;
        else if(std::strcmp(argv[i],"--browser")==0)browser=true;
        else if(std::strcmp(argv[i],"--local-probe")==0)local_probe=true;
        else if(count<16)client_args[count++]=argv[i];
        else {close_pipe(request.read_token);close_pipe(request.write_token);close_pipe(response.read_token);close_pipe(response.write_token);std::printf("SSG_SESSION arguments=LIMIT\n");return 2;}
    }
    const auto client=sdk::spawn_file_options(client_args[0],count,client_args,client_options);
    if(client<0){std::printf("SSG_SESSION consumer_spawn=FAIL code=%lld\n",(long long)client);close_pipe(request.read_token);close_pipe(request.write_token);close_pipe(response.read_token);close_pipe(response.write_token);return 2;}
    sdk::spawn_options provider_options{};provider_options.stdio[0]=request.read_token;provider_options.stdio[2]=response.write_token;
    const char *provider_args[6]={browser?"/bin/browser.elf":"/bin/notes.elf",document,"--ssg-ipc-provider",instance};
    unsigned provider_count=4;if(text_scope)provider_args[provider_count++]="--ssg-ipc-text";
    if(local_probe)provider_args[provider_count++]="--ssg-probe";
    const auto provider=sdk::spawn_file_options(provider_args[0],provider_count,provider_args,provider_options);
    std::printf("SSG_SESSION parent=%llu provider=%lld consumer=%lld instance=%s text_scope=%s\n",(unsigned long long)sdk::pid(),(long long)provider,(long long)client,instance,text_scope?"explicit":"denied");
    close_pipe(request.read_token);close_pipe(request.write_token);close_pipe(response.read_token);close_pipe(response.write_token);
    process_status client_status{},provider_status{};
    const auto cw=sdk::wait(client,client_status);
    std::printf("SSG_SESSION consumer_wait=%lld outcome=%u code=%lld\n",(long long)cw,unsigned(client_status.outcome),(long long)client_status.code);
    if(provider<0){std::printf("SSG_SESSION provider_spawn=FAIL code=%lld\n",(long long)provider);return 2;}
    const auto pw=sdk::wait(provider,provider_status);
    std::printf("SSG_SESSION provider_wait=%lld outcome=%u code=%lld\n",(long long)pw,unsigned(provider_status.outcome),(long long)provider_status.code);
    return cw==0 && pw==0 && client_status.outcome==process_outcome::exited && client_status.code==0 && provider_status.outcome==process_outcome::exited && provider_status.code==0?0:1;
}
