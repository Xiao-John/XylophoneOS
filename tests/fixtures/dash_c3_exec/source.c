/* SPDX-License-Identifier: Apache-2.0 */
#include "common.h"
#include <spawn.h>
#include <sys/wait.h>
#ifdef XOS_THREADED_RUNTIME
#include <pthread.h>
#endif
extern char **environ;
extern int _execve(const char*,char *const[],char *const[]);
static volatile unsigned char image_slot[4096] __attribute__((section(".exec_probe_slot"),used));
static __thread unsigned tls_cookie=0x1111;
static int data_fd,alias_fd,clo_alias,only_clo,pipe_fd[2];
static char label[32];
static void setup(const char *mode) {
    char path[128];strncpy(label,mode,sizeof(label)-1);
    /* Keep a console-route reference for raw diagnostics after fd 1 becomes a
       regular file. This descriptor must itself survive replacement. */
    c3_check(dup2(1,29)==29,"save-console-route");
    snprintf(path,sizeof(path),"/out/%s-stream.dat",label);
    data_fd=open(path,O_CREAT|O_TRUNC|O_RDWR,0600);c3_check(data_fd>=3,"open-data");
    c3_check(write(data_fd,"0123456789",10)==10 && lseek(data_fd,2,SEEK_SET)==2,"prepare-offset");
    alias_fd=dup(data_fd);clo_alias=dup(data_fd);c3_check(alias_fd>=3 && clo_alias>=3,"dup-file");
    c3_check(fcntl(clo_alias,F_SETFD,FD_CLOEXEC)==0,"cloexec-alias");
    snprintf(path,sizeof(path),"/out/%s-only-clo.dat",label);
    only_clo=open(path,O_CREAT|O_TRUNC|O_RDWR,0600);c3_check(only_clo>=3 && fcntl(only_clo,F_SETFD,FD_CLOEXEC)==0,"cloexec-only-object");
    c3_check(write(only_clo,"before",6)==6,"only-clo-write");
    c3_check(pipe(pipe_fd)==0 && write(pipe_fd[1],"pipe-token",10)==10,"prepare-pipe");
    c3_check(fcntl(pipe_fd[1],F_SETFD,FD_CLOEXEC)==0,"pipe-writer-cloexec");
    snprintf(path,sizeof(path),"/out/%s-combined.log",label);
    int combined=open(path,O_CREAT|O_TRUNC|O_RDWR,0600);
    c3_check(combined>=3 && dup2(combined,1)==1 && dup2(1,2)==2 && close(combined)==0,"stdout-stderr-shared-object");
    for(int fd=9;fd<=28;++fd)c3_check(dup2(data_fd,fd)==fd,"fill-descriptor-table");
    c3_check(dup2(data_fd,31)==31 && dup2(data_fd,30)==30 && fcntl(30,F_SETFD,FD_CLOEXEC)==0,"highest-fd-and-cloexec-alias");
    const char *search=!strcmp(mode,"path_invalid")?"/tests/path-invalid:/tests/path-good":!strcmp(mode,"path_legacy")?"/tests/path-legacy:/tests/path-good":"/tests";
    c3_check(chdir("/tmp/work")==0 && setenv("C3_ENV","value line\nwith\ttab",1)==0 && setenv("PATH",search,1)==0,"cwd-env");
    c3_check(setenv("C3_EXPECT_SPAWN",!strcmp(mode,"authority")?"1":"0",1)==0,"authority-expectation");
    c3_check(setenv("C3_LONG_ARG",!strcmp(mode,"long_arg")?"1":"0",1)==0,"long-argument-expectation");
    image_slot[0]=0x5a;tls_cookie=0x3333;
    for(unsigned i=0;i<64;++i)((volatile unsigned char*)STACK_PROBE)[i]=0x5a;
    c3_check(sbrk(32768)!=(void*)-1,"old-heap-allocation");
}
static void retained(unsigned long pid,unsigned long tid,unsigned long old_break) {
    c3_check((unsigned long)getpid()==pid && c3_info().tid==tid,"failed-exec-identity");
    c3_check((unsigned long)sbrk(0)==old_break && image_slot[0]==0x5a && tls_cookie==0x3333,"failed-exec-image-heap-tls");
    for(unsigned i=0;i<64;++i)c3_check(((volatile unsigned char*)STACK_PROBE)[i]==0x5a,"failed-exec-stack");
    c3_check(fcntl(clo_alias,F_GETFD)==FD_CLOEXEC && fcntl(only_clo,F_GETFD)==FD_CLOEXEC && fcntl(pipe_fd[1],F_GETFD)==FD_CLOEXEC,"failed-exec-keeps-cloexec-descriptors");
    c3_check(fcntl(30,F_GETFD)==FD_CLOEXEC && fcntl(31,F_GETFD)==0 && lseek(31,0,SEEK_CUR)==2,"failed-exec-keeps-highest-fds");
    c3_check(lseek(data_fd,0,SEEK_CUR)==2 && lseek(alias_fd,0,SEEK_CUR)==2,"failed-exec-keeps-offset");
    char data[2];c3_check(read(alias_fd,data,2)==2 && !memcmp(data,"23",2) && lseek(data_fd,0,SEEK_CUR)==4,"failed-exec-keeps-open-alias");
    c3_check(write(only_clo,"-after",6)==6 && write(pipe_fd[1],"Z",1)==1,"failed-exec-keeps-only-clo-and-pipe-writer");
}
static int raw_stage(void) {
    const struct c3_stats before=c3_stats();c3_resource_log("raw_before",before);
    long stage=c3_call(61,0,(unsigned long)"raw-stage",9);c3_check(stage>0,"unprivileged-exec-prepare");
    c3_check(c3_call(61,0,0,0)==-6,"only-one-replacement-reservation");
    unsigned char code[16]={0xbf,99,0,0,0,0xb8,2,0,0,0,0xcd,0x80,0x0f,0x0b};
    struct c3_mapping map={0x40000000ul,(unsigned long)code,sizeof(code),5};
    c3_check(c3_call(17,(unsigned long)stage,(unsigned long)&map,0)==0,"raw-map-entry");
    map=(struct c3_mapping){0x7fffb000ul,0,0,6};c3_check(c3_call(17,(unsigned long)stage,(unsigned long)&map,0)==0,"raw-map-stack");
    map=(struct c3_mapping){0x7fffc000ul,0,0,6};c3_check(c3_call(17,(unsigned long)stage,(unsigned long)&map,0)==0,"raw-map-startup");
    struct c3_entry good={0x40000000ul,0x7fffc000ul-16,0x7fffc000ul},bad={0x1000,0,0};
    c3_check(c3_call(18,(unsigned long)stage,(unsigned long)&good,0)==-6,"staging-cannot-normal-start");
    c3_check(c3_call(28,(unsigned long)stage,1,0)==-1 && c3_call(37,(unsigned long)stage,1,0)==-10,"staging-cannot-grant");
    unsigned char status[48];c3_check(c3_call(20,(unsigned long)stage,(unsigned long)status,1)==-1,"staging-has-no-completion");
    c3_check(c3_call(60,(unsigned long)stage,(unsigned long)&bad,0)==-2,"invalid-entry-rejected");
    c3_check(c3_call(60,(unsigned long)stage,(unsigned long)&good,1)==-10,"no-authority-depth-change-rejected");
    c3_check(c3_call(19,(unsigned long)stage,0,0)==0,"raw-stage-abort");
    const struct c3_stats after=c3_stats();c3_resource_log("raw_after",after);
    c3_check(c3_same_resources(before,after),"raw-stage-resource-rollback");
    return 0;
}
#ifdef XOS_THREADED_RUNTIME
static void *worker(void *value){return value;}
int main(void) {
    image_slot[0]=0;
    pthread_t tid;c3_check(pthread_create(&tid,0,worker,0)==0 && pthread_join(tid,0)==0,"thread-profile-enable");
    int pair[2];c3_check(pipe(pair)==0 && fcntl(pair[1],F_SETFD,FD_CLOEXEC)==0,"thread-profile-fd");
    char *args[]={"target","unused",0};
    c3_check(execve("/tests/target",args,environ)==-1 && errno==ENOTSUP,"threaded-execve-unsupported");
    c3_check(execv("/tests/target",args)==-1 && errno==ENOTSUP,"threaded-execv-unsupported");
    c3_check(execvp("/tests/target",args)==-1 && errno==ENOTSUP,"threaded-execvp-unsupported");
    c3_check(_execve("/tests/target",args,environ)==-1 && errno==ENOTSUP,"threaded-_execve-unsupported");
    c3_check(c3_call(61,0,0,0)==-18,"kernel-thread-profile-unsupported");
    c3_check(fcntl(pair[1],F_GETFD)==FD_CLOEXEC && close(pair[0])==0 && close(pair[1])==0,"unsupported-keeps-fd");
    c3_log("C3_EXEC_THREADED ENOTSUP unchanged_fd PASS\n");return 0;
}
#else
int main(int argc,char **argv) {
    c3_check(argc==2,"source-mode");const char *mode=argv[1];setup(mode);
    unsigned long pid=(unsigned long)getpid(),tid=c3_info().tid;
    char numbers[9][32];
    unsigned long values[]={pid,tid,(unsigned long)sbrk(0),(unsigned long)data_fd,(unsigned long)alias_fd,(unsigned long)clo_alias,(unsigned long)only_clo,(unsigned long)pipe_fd[0],(unsigned long)pipe_fd[1]};
    for(unsigned i=0;i<9;++i)snprintf(numbers[i],sizeof(numbers[i]),"%lu",values[i]);
    char *args[]={"target-label","success",numbers[0],numbers[1],numbers[2],numbers[3],numbers[4],numbers[5],numbers[6],numbers[7],numbers[8],"","line\nwith\ttab","space value",0};
    char long_argument[1025];
    if(!strcmp(mode,"long_arg")) {
        for(unsigned i=0;i<1024;++i)long_argument[i]=(char)('A'+i%26);
        long_argument[1024]=0;args[13]=long_argument;
        pid_t rejected;
        c3_check(posix_spawn(&rejected,"/tests/target",0,0,args,environ)==E2BIG,"ordinary-spawn-retains-255-byte-limit");
        c3_log("C3_EXEC_SPAWN_ARG_LIMIT E2BIG PASS\n");
    }
    char line[192];snprintf(line,sizeof(line),"C3_EXEC_SOURCE pid=%lu tid=%lu heap=%lu mode=%s\n",pid,tid,values[2],mode);c3_log(line);
    if(!strcmp(mode,"raw")) {raw_stage();retained(pid,tid,values[2]);c3_log("C3_EXEC_RAW stage_barrier invalid_entry depth_failure no_completion abort=stable PASS\n");return 0;}
    if(!strcmp(mode,"missing") || !strcmp(mode,"invalid") || !strcmp(mode,"quota") || !strcmp(mode,"oom") ||
       !strcmp(mode,"legacy") || !strcmp(mode,"path_invalid") || !strcmp(mode,"path_legacy")) {
        pid_t children[8];unsigned count=0;
        if(!strcmp(mode,"quota")) {
            char *hold[]={"target","hold",0};
            while(count<8) {pid_t child;int error=posix_spawn(&child,"/tests/target",0,0,hold,environ);if(error)break;children[count++]=child;}
            c3_check(count>0 && count<8,"fill-process-quota");
        }
        void *allocation=0;
        if(!strcmp(mode,"oom")) {
            allocation=sbrk(254ul*1024*1024);c3_check(allocation!=(void*)-1,"hold-254MiB-source-heap");
            ((volatile unsigned char*)allocation)[0]=0xab;((volatile unsigned char*)allocation)[254ul*1024*1024-1]=0xcd;
        }
        const unsigned long held_break=(unsigned long)sbrk(0);
        const struct c3_stats before=c3_stats();c3_resource_log("failure_before",before);
        const char *path=!strcmp(mode,"missing")?"/missing/target":!strcmp(mode,"invalid")?"/tests/invalid":!strcmp(mode,"oom")?"/tests/huge-target":!strcmp(mode,"legacy")?"/tests/legacy-target":"/tests/target";
        int result=(!strcmp(mode,"path_invalid") || !strcmp(mode,"path_legacy"))?execvp("candidate",args):execve(path,args,environ);
        int error=errno;
        c3_check(result==-1,"negative-exec-returned-error");
        if(!strcmp(mode,"missing"))c3_check(error==ENOENT,"missing-errno");
        else if(!strcmp(mode,"invalid") || !strcmp(mode,"path_invalid"))c3_check(error==ENOEXEC,"invalid-errno");
        else if(!strcmp(mode,"legacy") || !strcmp(mode,"path_legacy"))c3_check(error==ENOTSUP,"legacy-abi-errno");
        else c3_check(error==ENOMEM || error==EAGAIN,"resource-errno");
        const struct c3_stats after=c3_stats();c3_resource_log("failure_after",after);
        c3_check(c3_same_resources(before,after),"failed-load-fully-reclaims-stage");
        retained(pid,tid,held_break);
        if(allocation) {c3_check(((volatile unsigned char*)allocation)[0]==0xab && ((volatile unsigned char*)allocation)[254ul*1024*1024-1]==0xcd,"oom-parent-bytes");c3_check(sbrk(-(intptr_t)(254ul*1024*1024))!=(void*)-1,"oom-parent-release");}
        for(unsigned i=0;i<count;++i) {int status;c3_check(c3_call(56,(unsigned long)children[i],0,0)==0 && waitpid(children[i],&status,0)==children[i],"quota-child-cleanup");}
        snprintf(line,sizeof(line),"C3_EXEC_FAILURE mode=%s errno=%d old_pid=%lu memory_fd_cloexec=valid PASS\n",mode,error,pid);c3_log(line);return 0;
    }
    unsigned mxcsr=0x3f80;__asm__ volatile("ldmxcsr %0"::"m"(mxcsr));
    if(!strcmp(mode,"execv"))execv("/tests/target",args);
    else if(!strcmp(mode,"execvp"))execvp("target",args);
    else if(!strcmp(mode,"_execve"))_execve("/tests/target",args,environ);
    else execve("/tests/target",args,environ);
    c3_log("C3_EXEC_UNREACHABLE_AFTER_SUCCESS\n");return 95;
}
#endif
