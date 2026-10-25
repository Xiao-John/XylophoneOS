/* SPDX-License-Identifier: Apache-2.0 */
/* C2 is qualified only by running this probe in a real XOS guest. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static volatile int private_memory = 7;
static unsigned char buffer[1777];
static int all_write(int fd, const void *data, size_t count) {
    const unsigned char *cursor = data;
    while (count) {
        ssize_t n = write(fd, cursor, count);
        if (n <= 0) return -1;
        cursor += n; count -= (size_t)n;
    }
    return 0;
}
static unsigned char pattern(unsigned long position) {
    return (unsigned char)('A' + position % 26u);
}
static int text(unsigned long length) {
    unsigned long position = 0;
    while (position < length) {
        size_t amount = length - position < sizeof(buffer) ? (size_t)(length - position) : sizeof(buffer);
        for (size_t i = 0; i < amount; ++i) buffer[i] = pattern(position+i);
        if (all_write(1, buffer, amount)) return 10;
        position += amount;
    }
    return all_write(1, "\n\n\n", 3) ? 11 : 0;
}
static int stream(int verify, unsigned long expected) {
    unsigned long position = 0;
    for (;;) {
        ssize_t n = read(0, buffer, sizeof(buffer));
        if (n < 0) return 12;
        if (!n) break;
        if (verify) {
            for (ssize_t i = 0; i < n; ++i) if (buffer[i] != pattern(position+(unsigned long)i)) return 13;
        } else if (all_write(1, buffer, (size_t)n)) return 14;
        position += (unsigned long)n;
    }
    if (verify) {
        if (position != expected) return 15;
        printf("C2_TEXT bytes=%lu eof=1\n", position);
    }
    return 0;
}
struct child_report { int pid, parent, memory, local, fd, cwd, env, cloexec; };
static int fork_check(const char *path) {
    int local = 17, pipe_fd[2], status;
    char cwd[256], parent_cwd[256], data[8] = {0};
    const int parent = getpid();
    if (setenv("C2_FORK_ENV", "parent", 1) || chdir("/tmp") || !getcwd(parent_cwd,sizeof(parent_cwd))) return 20;
    int fd = open(path, O_CREAT|O_TRUNC|O_RDWR, 0600);
    if (fd < 3) return 21;
    int duplicate = fcntl(fd, F_DUPFD, 10);
    if (duplicate < 10 || fcntl(duplicate, F_SETFD, FD_CLOEXEC)) return 22;
    if (all_write(fd, "abcdef", 6) || lseek(fd, 0, SEEK_SET) != 0 || pipe(pipe_fd)) return 23;
    pid_t child = fork();
    if (child < 0) { perror("C2_FORK fork"); return 24; }
    if (!child) {
        struct child_report report;
        close(pipe_fd[0]); private_memory = 99; local = 31;
        report.pid = getpid(); report.parent = parent;
        report.memory = private_memory; report.local = local;
        report.fd = read(fd, data, 2) == 2 && !memcmp(data,"ab",2) &&
                    lseek(duplicate, 0, SEEK_CUR) == 2 && all_write(duplicate,"X",1) == 0;
        report.cloexec = fcntl(duplicate,F_GETFD) == FD_CLOEXEC;
        report.cwd = chdir("/") == 0 && getcwd(cwd,sizeof(cwd)) && !strcmp(cwd,"/");
        report.env = setenv("C2_FORK_ENV","child",1) == 0 && !strcmp(getenv("C2_FORK_ENV"),"child");
        if (all_write(pipe_fd[1],&report,sizeof(report))) _exit(25);
        _exit(23);
    }
    close(pipe_fd[1]);
    if (waitpid(child,&status,0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 23) return 26;
    struct child_report report;
    size_t used = 0;
    while (used < sizeof(report)) {
        ssize_t n = read(pipe_fd[0],(unsigned char *)&report+used,sizeof(report)-used);
        if (n <= 0) return 27;
        used += (size_t)n;
    }
    if (read(pipe_fd[0],data,1) != 0) return 28;
    if (report.pid != child || report.pid == parent || report.parent != parent ||
        report.memory != 99 || report.local != 31 || !report.fd || !report.cwd ||
        !report.env || !report.cloexec || private_memory != 7 || local != 17) return 29;
    if (!getcwd(cwd,sizeof(cwd)) || strcmp(cwd,parent_cwd) ||
        strcmp(getenv("C2_FORK_ENV"),"parent") || lseek(fd,0,SEEK_CUR) != 3 ||
        read(fd,data,3) != 3 || memcmp(data,"def",3)) return 30;
    if (close(pipe_fd[0]) || close(duplicate) || close(fd)) return 31;
    puts("C2_FORK memory=isolated pid=distinct fd=shared_offset cloexec=inherited cwd=isolated env=isolated eof=1 PASS");
    return 0;
}
#ifndef XOS_REFERENCE
static long call(unsigned long number, unsigned long a, unsigned long b, unsigned long c) {
    long value;
    __asm__ volatile("int $0x80" : "=a"(value) : "a"(number),"D"(a),"S"(b),"d"(c) : "memory");
    return value;
}
/* The 48-byte ABI below mirrors xos/thread_abi.hpp without exposing C++
 * headers to this C/newlib consumer. One allocation, one failed fork, no loop
 * of repeated resource exhaustion. free() need not shrink newlib's arena. */
struct c2_thread_stats {
    uint32_t version, size; uint64_t header_reserved;
    uint32_t processes, threads, reserved, waiting, results, free_pages;
    uint32_t process_user_pages, process_kernel_stack_pages;
};
_Static_assert(sizeof(struct c2_thread_stats)==48, "thread_stats ABI size");
static int get_stats(struct c2_thread_stats *value) {
    memset(value,0,sizeof(*value));
    return call(50,(unsigned long)value,0,0)==0 && value->version==1 && value->size==48;
}
static void show_stats(const char *phase,const struct c2_thread_stats *value) {
    printf("C2_OOM_COUNTERS %s free=%u processes=%u threads=%u reserved=%u waiting=%u results=%u user_pages=%u kernel_stack_pages=%u\n",
        phase,value->free_pages,value->processes,value->threads,value->reserved,value->waiting,
        value->results,value->process_user_pages,value->process_kernel_stack_pages);
}
static int oom_check(const char *path,unsigned long mebibytes) {
    struct c2_thread_stats initial,held,failed,after_free;
    int fd,status,error;
    if (mebibytes<200 || mebibytes>254) return 50;
    fd=open(path,O_CREAT|O_TRUNC|O_RDWR,0600);
    if (fd<3 || all_write(fd,"before",6)) return 51;
    puts("C2_OOM_BEGIN one_allocation_one_fork");fflush(stdout);
    if (!get_stats(&initial)) return 52;
    size_t bytes=(size_t)mebibytes*1024u*1024u;
    unsigned char *memory=malloc(bytes);
    if (!memory) { printf("C2_OOM_SETUP_FAIL malloc_mib=%lu errno=%d\n",mebibytes,errno);close(fd);return 53; }
    for (size_t offset=0;offset<bytes;offset+=4096u) memory[offset]=(unsigned char)((offset/4096u)^0x5au);
    memory[bytes-1]=0xa5u;
    if (!get_stats(&held)) {free(memory);close(fd);return 54;}
    pid_t child=fork();error=errno;
    if (!child) _exit(92);
    if (child>0) {
        waitpid(child,&status,0);free(memory);close(fd);
        puts("C2_OOM_UNEXPECTED_FORK_SUCCEEDED");return 55;
    }
    if (error!=ENOMEM || !get_stats(&failed)) {free(memory);close(fd);return 56;}
    show_stats("initial",&initial);show_stats("held",&held);show_stats("failed",&failed);
    if (memcmp(&held,&failed,sizeof(held)) || held.process_user_pages<=initial.process_user_pages ||
        held.free_pages>=initial.free_pages) {free(memory);close(fd);return 57;}
    for (size_t offset=0;offset<bytes;offset+=4096u)
        if (memory[offset]!=(unsigned char)((offset/4096u)^0x5au)) {free(memory);close(fd);return 58;}
    if (memory[bytes-1]!=0xa5u || lseek(fd,0,SEEK_CUR)!=6 || all_write(fd,"after",5)) {
        free(memory);close(fd);return 59;
    }
    char expected[11];
    if (lseek(fd,0,SEEK_SET)!=0 || read(fd,expected,sizeof(expected))!=sizeof(expected) ||
        memcmp(expected,"beforeafter",11)) {free(memory);close(fd);return 60;}
    free(memory);
    if (!get_stats(&after_free)) {close(fd);return 61;}
    show_stats("after_free",&after_free);
    if (close(fd)) return 62;
    printf("C2_OOM fork_errno=ENOMEM malloc_mib=%lu partial_child_resources=baseline parent_memory=valid parent_fd=valid PASS\n",mebibytes);
    return 0;
}
static int denied(void) {
    if (call(57,1,0,0) != -2 || call(57,0,0,0) != -1 ||
        call(58,0,0,0) != -1 || call(59,0,0,0) != -1) return 40;
    puts("C2_FORK denied=EPERM arguments=EINVAL commit_without_child=denied service_auth=denied PASS");
    return 0;
}
static int profile_reject(void) {
    struct { unsigned version,size; unsigned long reserved; } header = {1,16,0};
    if (call(52,(unsigned long)&header,0,0) != 0) return 41;
    if (call(57,0,0,0) != -18) return 42;
    errno = 0;
    if (fork() != -1 || errno != ENOTSUP) return 43;
    puts("C2_FORK thread_profile=ENOTSUP PASS");
    return 0;
}
#endif
int main(int argc, char **argv) {
    if (argc < 2) return 2;
    const char *mode = argv[1];
    unsigned long count = argc > 2 ? strtoul(argv[2],NULL,10) : 0;
    if (!strcmp(mode,"text")) return text(count);
    if (!strcmp(mode,"copy")) return stream(0,0);
    if (!strcmp(mode,"check")) return stream(1,count);
    if (!strcmp(mode,"echo")) { for (int i=2;i<argc;++i) printf("<%s>\n",argv[i]); return 0; }
    if (!strcmp(mode,"exit")) return (int)count;
    if (!strcmp(mode,"fork")) return argc==3 ? fork_check(argv[2]) : 3;
    if (!strcmp(mode,"spin")) { fputs("C2_SPIN_READY\n",stderr); for (;;) __asm__ volatile("" : : : "memory"); }
    if (!strcmp(mode,"fault")) { *(volatile unsigned char *)0x1000 = 1; return 99; }
    if (!strcmp(mode,"threaded_reject")) {
        errno=0; if (fork()!=-1 || errno!=ENOTSUP) return 44;
        puts("C2_FORK threaded_libc=ENOTSUP PASS"); return 0;
    }
#ifndef XOS_REFERENCE
    if (!strcmp(mode,"oom")) return argc>=3 ? oom_check(argv[2],argc>3?strtoul(argv[3],NULL,10):254) : 3;
    if (!strcmp(mode,"denied")) return denied();
    if (!strcmp(mode,"profile")) return profile_reject();
#endif
    return 4;
}
