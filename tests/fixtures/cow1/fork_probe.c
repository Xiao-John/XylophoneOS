// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <stdlib.h>
#include <fcntl.h>

struct vm_request {
    uint32_t version,size,operation,flags;
    uint64_t address,length,alignment;
    uint32_t protection,reserved0;
    uint64_t reserved1,reserved2;
};
static long diagnostic_at(uint32_t op, uint64_t address) {
    struct vm_request req={1,sizeof(req),op,0,address,0,0,0,0,0,0};
    long result=67;
    __asm__ volatile("int $0x80" : "+a"(result) : "D"(&req), "S"(0), "d"(0) : "memory", "cc");
    return result;
}
static long diagnostic(uint32_t op) { return diagnostic_at(op,0); }
static long kernel_call(long number, unsigned long argument) {
    __asm__ volatile("int $0x80" : "+a"(number) : "D"(argument), "S"(0), "d"(0) : "memory", "cc");
    return number;
}
static volatile uint64_t global_value=17;
static __thread volatile uint64_t tls_value=71;
int main(int argc, char** argv) {
    if (argc>1 && !strcmp(argv[1],"exec_check")) {
        puts("COW1_EXEC_IMAGE_PASS");
        return 0;
    }
    if (argc>1 && !strcmp(argv[1],"cancel")) {
        volatile unsigned char* pages=mmap(0,1024*4096,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
        if (pages==MAP_FAILED || mprotect((void*)pages,1024*4096,PROT_READ|PROT_WRITE) ||
            diagnostic(0xfff9)!=0) return 38;
        puts("COW1_CANCEL_START");
        pid_t pid=fork();
        if (!pid) _exit(0);
        return 39;
    }
    volatile uint64_t stack_value=23;
    volatile unsigned char* heap=malloc(4096);
    if (!heap) return 42;
    heap[0]=72; heap[4095]=73;
    volatile unsigned char* p=mmap(0,8192,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if (p==MAP_FAILED || mprotect((void*)p,8192,PROT_READ|PROT_WRITE)) return 1;
    p[0]=31; p[4095]=32; p[4096]=33;
    if (mprotect((void*)(p+4096),4096,PROT_NONE) || diagnostic(0xfff9)!=0) return 2;
    // Fail every page-table allocation position before the first successful
    // snapshot. The parent must remain usable and each failed child must be
    // completely reclaimed before the syscall returns.
    const long before=diagnostic(0xffff);
    int exhausted=0;
    for (uint64_t n=0;n<32;++n) {
        if (diagnostic_at(0xfffa,n)!=0) return 16;
        errno=0;
        pid_t candidate=fork();
        if (!candidate) _exit(0);
        if (candidate>0) {
            int result=0;
            if (waitpid(candidate,&result,0)!=candidate || !WIFEXITED(result) || WEXITSTATUS(result)) return 17;
            exhausted=1;
        } else if (errno!=ENOMEM) return 18;
        if (diagnostic(0xffff)!=before || p[0]!=31 || global_value!=17 || stack_value!=23) return 19;
        if (exhausted) break;
    }
    if (!exhausted) return 20;
    puts("COW1_FORK_OOM_SWEEP_PASS");
    // The parent may write after prepare succeeds but before files cloning.
    // Aborting the building child must not restore the obsolete shared PTE.
    const long abort_baseline=diagnostic(0xffff);
    const long staged=kernel_call(57,0);
    if (staged<=0) return 40;
    p[0]=61;
    if (kernel_call(19,(unsigned long)staged)!=0 || p[0]!=61 ||
        diagnostic(0xffff)!=abort_baseline) return 41;
    p[0]=31;
    puts("COW1_ABORT_AFTER_PARENT_WRITE_PASS");
    // Fail the files service ACK after it retained the open descriptions.
    // libc must abort the building child and leave the parent's FD usable.
    int fd=open("/bin/cow1.elf",O_RDONLY);
    if (fd<0) return 46;
    unsigned char signature[4];
    if (read(fd,signature,4)!=4 || signature[0]!=0x7f || signature[1]!='E') return 47;
    const long files_baseline=diagnostic(0xffff);
    if (diagnostic(0xfff5)!=0) return 48;
    errno=0;
    pid_t failed=fork();
    if (!failed) _exit(49);
    if (failed!=-1 || !errno || p[0]!=31 || lseek(fd,0,SEEK_SET)!=0 ||
        read(fd,signature,4)!=4 || signature[0]!=0x7f || diagnostic(0xffff)!=files_baseline) return 50;
    pid_t retry=fork();
    if (retry<0) return 51;
    if (!retry) {
        if (lseek(fd,0,SEEK_SET)!=0 || read(fd,signature,4)!=4 || signature[1]!='E') _exit(52);
        _exit(0);
    }
    int retry_status=0;
    if (waitpid(retry,&retry_status,0)!=retry || !WIFEXITED(retry_status) || WEXITSTATUS(retry_status) ||
        close(fd) || diagnostic(0xffff)!=files_baseline) return 53;
    puts("COW1_FILES_ACK_FAILURE_PASS");
    const long retain_baseline=diagnostic(0xffff);
    int retain_exhausted=0;
    for (uint64_t i=0;i<1024;++i) {
        if (diagnostic_at(0xfff4,i)!=0) return 54;
        errno=0;
        pid_t failed_retain=fork();
        if (!failed_retain) _exit(55);
        if (failed_retain>0) {
            int status=0;
            if (waitpid(failed_retain,&status,0)!=failed_retain || !WIFEXITED(status) ||
                WEXITSTATUS(status)!=55) return 64;
            retain_exhausted=1;
        } else if (errno!=ENOMEM) return 56;
        if (diagnostic(0xffff)!=retain_baseline || p[0]!=31 || tls_value!=71 || heap[0]!=72) return 56;
        if (retain_exhausted) { printf("COW1_RETAIN_SWEEP count=%lu\n",(unsigned long)i); break; }
    }
    if (!retain_exhausted) return 65;
    puts("COW1_RETAIN_FAILURE_PASS");
    // Hold a child alive without writing the large mapping and check that
    // fork did not eagerly allocate one physical page per committed page.
    volatile unsigned char* large=mmap(0,128*4096,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if (large==MAP_FAILED || mprotect((void*)large,128*4096,PROT_READ|PROT_WRITE)) return 21;
    for (int i=0;i<128;++i) large[i*4096]=(unsigned char)i;
    int gate[2]; if (pipe(gate)) return 22;
    const long unique_before=diagnostic(0xfff7);
    pid_t sharing=fork();
    if (sharing<0) return 23;
    if (!sharing) {
        char signal=0;
        if (read(gate[0],&signal,1)!=1 || signal!='x' || large[0]!=0 || large[127*4096]!=127) _exit(24);
        _exit(0);
    }
    const long unique_after=diagnostic(0xfff7);
    if (unique_before<0 || unique_after<0 || unique_after-unique_before>32) return 25;
    printf("COW1_SHARED_PAGES before=%ld after=%ld mapped=128\n",unique_before,unique_after);
    if (write(gate[1],"x",1)!=1) return 26;
    int sharing_status=0;
    if (waitpid(sharing,&sharing_status,0)!=sharing || !WIFEXITED(sharing_status) || WEXITSTATUS(sharing_status)) return 27;
    if (close(gate[0]) || close(gate[1]) || munmap((void*)large,128*4096)) return 28;
    // Force the first user-mode COW allocation to fail. The faulting child
    // must die without changing its parent's mapping or leaking references.
    const long fault_baseline=diagnostic(0xffff);
    pid_t fault_child=fork();
    if (fault_child<0) return 29;
    if (!fault_child) {
        if (diagnostic(0xfff6)!=0) _exit(30);
        p[0]=99;
        _exit(31);
    }
    int fault_status=0;
    if (waitpid(fault_child,&fault_status,0)!=fault_child || !WIFSIGNALED(fault_status) ||
        p[0]!=31 || diagnostic(0xffff)!=fault_baseline) return 32;
    puts("COW1_FAULT_OOM_PASS");
    volatile unsigned char* readonly=mmap(0,4096,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if (readonly==MAP_FAILED || mprotect((void*)readonly,4096,PROT_READ|PROT_WRITE)) return 33;
    readonly[0]=77;
    if (mprotect((void*)readonly,4096,PROT_READ)) return 34;
    pid_t readonly_child=fork();
    if (readonly_child<0) return 35;
    if (!readonly_child) { readonly[0]=88; _exit(36); }
    int readonly_status=0;
    if (waitpid(readonly_child,&readonly_status,0)!=readonly_child || !WIFSIGNALED(readonly_status) ||
        readonly[0]!=77 || munmap((void*)readonly,4096)) return 37;
    puts("COW1_READONLY_FAULT_PASS");
    pid_t exec_child=fork();
    if (exec_child<0) return 43;
    if (!exec_child) {
        char* arguments[]={"cow1","exec_check",0};
        char* environment[]={0};
        errno=0;
        if (execve("/bin/no-such-cow1.elf",arguments,environment)!=-1 || errno!=ENOENT || p[0]!=31)
            _exit(57);
        p[0]=62;
        execve("/bin/cow1.elf",arguments,environment);
        _exit(44);
    }
    int exec_status=0;
    if (waitpid(exec_child,&exec_status,0)!=exec_child || !WIFEXITED(exec_status) ||
        WEXITSTATUS(exec_status) || p[0]!=31 || global_value!=17 || tls_value!=71 || heap[0]!=72) return 45;
    puts("COW1_EXEC_PARENT_PASS");
    volatile unsigned char* cross=mmap(0,8192,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if (cross==MAP_FAILED || mprotect((void*)cross,8192,PROT_READ|PROT_WRITE)) return 58;
    for (unsigned i=4092;i<4100;++i) cross[i]=0x5a;
    pid_t cross_child=fork();
    if (cross_child<0) return 59;
    if (!cross_child) {
        uint64_t value=0x123456789abcdef0ull;
        __asm__ volatile("movq %1,(%0)" : : "r"(cross+4092), "r"(value) : "memory");
        if (cross[4092]!=0xf0 || cross[4099]!=0x12) _exit(60);
        _exit(0);
    }
    int cross_status=0;
    if (waitpid(cross_child,&cross_status,0)!=cross_child || !WIFEXITED(cross_status) || WEXITSTATUS(cross_status)) return 61;
    for (unsigned i=4092;i<4100;++i) if (cross[i]!=0x5a) return 62;
    if (munmap((void*)cross,8192)) return 63;
    puts("COW1_CROSS_PAGE_STORE_PASS");
    // Execute an RX snapshot, then verify that NONE and NX remain faults.
    volatile unsigned char* code=mmap(0,4096,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if (code==MAP_FAILED || mprotect((void*)code,4096,PROT_READ|PROT_WRITE)) return 66;
    code[0]=0xb8; code[1]=42; code[2]=code[3]=code[4]=0; code[5]=0xc3;
    if (mprotect((void*)code,4096,PROT_READ|PROT_EXEC)) return 67;
    pid_t executable=fork();
    if (executable<0) return 68;
    if (!executable) {
        int (*fn)(void)=(int (*)(void))(uintptr_t)code;
        _exit(fn()==42 ? 0 : 69);
    }
    int execute_status=0;
    if (waitpid(executable,&execute_status,0)!=executable || !WIFEXITED(execute_status) ||
        WEXITSTATUS(execute_status)) return 70;
    pid_t no_access=fork();
    if (no_access<0) return 71;
    if (!no_access) { volatile unsigned char value=p[4096]; (void)value; _exit(72); }
    int no_access_status=0;
    if (waitpid(no_access,&no_access_status,0)!=no_access || !WIFSIGNALED(no_access_status)) return 73;
    if (mprotect((void*)code,4096,PROT_READ|PROT_WRITE)) return 74;
    pid_t nx_child=fork();
    if (nx_child<0) return 75;
    if (!nx_child) {
        int (*fn)(void)=(int (*)(void))(uintptr_t)code;
        _exit(fn());
    }
    int nx_status=0;
    if (waitpid(nx_child,&nx_status,0)!=nx_child || !WIFSIGNALED(nx_status) ||
        munmap((void*)code,4096)) return 76;
    pid_t guard_child=fork();
    if (guard_child<0) return 77;
    if (!guard_child) { volatile unsigned char value=code[0]; (void)value; _exit(78); }
    int guard_status=0;
    if (waitpid(guard_child,&guard_status,0)!=guard_child || !WIFSIGNALED(guard_status)) return 79;
    puts("COW1_EXECUTION_PERMISSIONS_PASS");
    pid_t child=fork();
    if (child<0) return 3;
    if (!child) {
        if (global_value!=17 || stack_value!=23 || tls_value!=71 || heap[0]!=72 || heap[4095]!=73 ||
            p[0]!=31 || p[4095]!=32) _exit(4);
        global_value=41; stack_value=42; p[0]=43; p[4095]=44;
        tls_value=74; heap[0]=75; heap[4095]=76;
        if (mprotect((void*)(p+4096),4096,PROT_READ|PROT_WRITE) || p[4096]!=33) _exit(5);
        p[4096]=45;
        if (diagnostic(0xfff8)<=0) _exit(6);
        pid_t grandchild=fork();
        if (grandchild<0) _exit(7);
        if (!grandchild) {
            if (global_value!=41 || p[0]!=43 || p[4096]!=45) _exit(8);
            p[0]=55; _exit(p[0]==55 ? 0 : 9);
        }
        int status=0;
        if (waitpid(grandchild,&status,0)!=grandchild || !WIFEXITED(status) || WEXITSTATUS(status) ||
            p[0]!=43 || p[4096]!=45 || global_value!=41 || stack_value!=42 || tls_value!=74 ||
            heap[0]!=75 || heap[4095]!=76) _exit(10);
        _exit(0);
    }
    global_value=51; stack_value=52; p[0]=53; p[4095]=54;
    tls_value=77; heap[0]=78; heap[4095]=79;
    if (diagnostic(0xfff8)<=0) return 11;
    int status=0;
    if (waitpid(child,&status,0)!=child || !WIFEXITED(status) || WEXITSTATUS(status)) return 12;
    if (global_value!=51 || stack_value!=52 || tls_value!=77 || heap[0]!=78 || heap[4095]!=79 ||
        p[0]!=53 || p[4095]!=54) return 13;
    if (mprotect((void*)(p+4096),4096,PROT_READ|PROT_WRITE) || p[4096]!=33) return 14;
    if (munmap((void*)p,8192)) return 15;
    free((void*)heap);
    puts("COW1_TLS_HEAP_PASS");
    puts("COW1_FORK_PASS");
    return 0;
}
