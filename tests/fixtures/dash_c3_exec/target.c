/* SPDX-License-Identifier: Apache-2.0 */
#include "common.h"
static volatile unsigned char image_slot[4096] __attribute__((section(".exec_probe_slot"),used));
static __thread unsigned tls_cookie=0x7777;
#ifdef C3_HUGE_TARGET
static volatile unsigned char large_bss[254ul*1024*1024];
#endif
int main(int argc,char **argv) {
    if(argc==2 && !strcmp(argv[1],"hold")) {c3_log("C3_EXEC_HOLD\n");for(;;)__asm__ volatile("":::"memory");}
#ifdef C3_HUGE_TARGET
    large_bss[0]=1;large_bss[sizeof(large_bss)-1]=2;c3_log("C3_EXEC_HUGE_UNEXPECTEDLY_STARTED\n");return 96;
#endif
    unsigned mxcsr;__asm__ volatile("stmxcsr %0":"=m"(mxcsr));
    const unsigned long new_break=(unsigned long)sbrk(0);
    c3_check(argc==14 && !strcmp(argv[0],"target-label") && !strcmp(argv[1],"success"),"argv-count-label");
    unsigned long pid=strtoul(argv[2],0,10),tid=strtoul(argv[3],0,10),old_break=strtoul(argv[4],0,10);
    c3_check((unsigned long)getpid()==pid && c3_info().tid==tid,"exec-keeps-pid-and-tid");
    c3_check(new_break>=0x60000000ul && new_break<old_break,"new-heap-reset");
    c3_check(image_slot[0]==0 && tls_cookie==0x7777 && mxcsr==0x1f80,"new-image-tls-fpu");
    for(unsigned i=0;i<64;++i)c3_check(((volatile unsigned char*)STACK_PROBE)[i]==0,"new-stack-zeroed");
    c3_check(!strcmp(argv[11],"") && !strcmp(argv[12],"line\nwith\ttab"),"exact-argument-bytes");
    if(getenv("C3_LONG_ARG") && !strcmp(getenv("C3_LONG_ARG"),"1")) {
        c3_check(strlen(argv[13])==1024,"long-argument-length");
        for(unsigned i=0;i<1024;++i)c3_check(argv[13][i]==(char)('A'+i%26),"long-argument-byte");
        c3_log("C3_EXEC_LONG_ARGUMENT bytes=1024 exact_bytes=ok PASS\n");
    } else c3_check(!strcmp(argv[13],"space value"),"space-argument-bytes");
    char cwd[64];c3_check(getcwd(cwd,sizeof(cwd)) && !strcmp(cwd,"/tmp/work"),"exec-cwd");
    c3_check(getenv("C3_ENV") && !strcmp(getenv("C3_ENV"),"value line\nwith\ttab"),"exec-environment-bytes");
    long child=c3_call(16,0,0,0);
    if(getenv("C3_EXPECT_SPAWN") && !strcmp(getenv("C3_EXPECT_SPAWN"),"1"))c3_check(child>0 && c3_call(19,(unsigned long)child,0,0)==0,"generic-exec-keeps-spawn-authority");
    else c3_check(child==-1,"generic-exec-does-not-add-authority");
    int data=(int)strtol(argv[5],0,10),alias=(int)strtol(argv[6],0,10),clo=(int)strtol(argv[7],0,10),only=(int)strtol(argv[8],0,10),reader=(int)strtol(argv[9],0,10),writer=(int)strtol(argv[10],0,10);
    c3_check(data>=3 && alias>=3 && fcntl(data,F_GETFD)==0 && fcntl(alias,F_GETFD)==0,"nonstandard-descriptor-inheritance");
    c3_check(fcntl(clo,F_GETFD)==-1 && errno==EBADF && fcntl(only,F_GETFD)==-1 && errno==EBADF && fcntl(writer,F_GETFD)==-1 && errno==EBADF,"close-only-cloexec-descriptors");
    c3_check(fcntl(30,F_GETFD)==-1 && errno==EBADF && fcntl(31,F_GETFD)==0 && fcntl(29,F_GETFD)==0,"descriptor-boundary-and-console-alias");
    char value;
    c3_check(lseek(data,0,SEEK_CUR)==2 && read(data,&value,1)==1 && value=='2' && read(alias,&value,1)==1 && value=='3',"same-open-instance-offset");
    c3_check(write(alias,"XY",2)==2 && lseek(data,0,SEEK_CUR)==6,"shared-offset-write");
    for(int fd=9;fd<=28;++fd)c3_check(fcntl(fd,F_GETFD)==0 && lseek(fd,0,SEEK_CUR)==6,"full-table-shared-open-instance");
    c3_check(lseek(31,0,SEEK_CUR)==6,"highest-fd-shares-offset");
    char piped[16];c3_check(read(reader,piped,10)==10 && !memcmp(piped,"pipe-token",10) && read(reader,piped,1)==0,"inherited-pipe-and-cloexec-EOF");
    c3_check(write(1,"stdout-target\n",14)==14 && lseek(2,0,SEEK_CUR)==14 && write(2,"stderr-target\n",14)==14 && lseek(1,0,SEEK_CUR)==28,"stdout-stderr-shared-offset");
    char line[256];snprintf(line,sizeof(line),"C3_EXEC_TARGET pid=%lu tid=%lu old_heap=%lu new_heap=%lu argv_env_cwd_fd_alias_cloexec_pipe_stack_tls_fpu=ok PASS\n",pid,tid,old_break,new_break);c3_log(line);
    return 37;
}
