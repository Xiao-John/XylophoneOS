/* SPDX-License-Identifier: Apache-2.0 */
/* Two real spawned writers share an inherited kernel stdout pipe route. */
#include <errno.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;
enum { record_bytes=512, records_per_writer=64, pipe_bytes=4096 };
static unsigned char raw_buffer[7777];
struct pipe_pair { unsigned reader,writer; };
struct resource_counts { unsigned version,size; unsigned long reserved; unsigned processes,threads,reservations,waiting,results,free_pages,user_pages,kernel_pages; };
static long raw(unsigned long number,unsigned long a,unsigned long b,unsigned long c) {
    long result;
    __asm__ volatile("int $0x80":"=a"(result):"a"(number),"D"(a),"S"(b),"d"(c):"memory");
    return result;
}
static void log_text(const char *text,int fd) {
    unsigned long length=strlen(text);
    while(length) { unsigned long amount=length>256?256:length;long n=raw(11,(unsigned long)fd,(unsigned long)text,amount);if(n<=0)break;text+=n;length-=(unsigned long)n; }
}
static void check(int good,const char *label) {
    if(good)return;
    log_text("PIPE_ATOMIC_FAIL ",2);log_text(label,2);log_text("\n",2);
    raw(2,97,0,0);for(;;){}
}
static struct resource_counts counts(void) {
    struct resource_counts value={0};check(raw(50,(unsigned long)&value,0,0)==0,"resource-query");return value;
}
static int equal_counts(struct resource_counts a,struct resource_counts b) {
    return a.processes==b.processes && a.threads==b.threads && a.reservations==b.reservations &&
        a.waiting==b.waiting && a.results==b.results && a.free_pages==b.free_pages &&
        a.user_pages==b.user_pages && a.kernel_pages==b.kernel_pages;
}
static void report_counts(const char *phase,struct resource_counts value) {
    char text[256];snprintf(text,sizeof(text),"PIPE_ATOMIC_RESOURCES %s free=%u processes=%u threads=%u reservations=%u waiting=%u results=%u user_pages=%u kernel_pages=%u\n",phase,value.free_pages,value.processes,value.threads,value.reservations,value.waiting,value.results,value.user_pages,value.kernel_pages);log_text(text,1);
}
static void raw_minimum_checks(void) {
    struct pipe_pair pair={0};
    check(raw(30,(unsigned long)&pair,0,0)==0,"raw-pipe-create");
    check(raw(54,pair.writer,512,0)==0 && raw(54,pair.writer,0,0)==0,"writer-ready-for-minimum");
    check(raw(54,pair.reader,1,0)==-2 && raw(54,pair.writer,4097,0)==-2 &&
          raw(54,pair.writer,512,1)==-2 && raw(54,12345,0,0)==-1,"wait-minimum-validation");
    /* Requests larger than PIPE_BUF retain the explicit short-write contract. */
    check(raw(32,pair.writer,(unsigned long)raw_buffer,sizeof(raw_buffer))==4096,"large-write-remains-short");
    check(raw(31,pair.reader,(unsigned long)raw_buffer,257)==257,"release-only-257-bytes");
    check(raw(54,pair.writer,0,0)==0,"legacy-minimum-one-ready");
    check(raw(32,pair.writer,(unsigned long)raw_buffer,512)==-3,"small-write-cannot-partially-consume-space");
    check(raw(31,pair.reader,(unsigned long)raw_buffer,255)==255,"release-complete-512-space");
    check(raw(54,pair.writer,512,0)==0 && raw(32,pair.writer,(unsigned long)raw_buffer,512)==512,"minimum-ready-whole-write");
    check(raw(33,pair.writer,0,0)==0,"raw-close-writer");
    check(raw(31,pair.reader,(unsigned long)raw_buffer,sizeof(raw_buffer))==4096 &&
          raw(31,pair.reader,(unsigned long)raw_buffer,1)==0,"raw-drain-and-eof");
    check(raw(33,pair.reader,0,0)==0,"raw-close-reader");
    log_text("PIPE_ATOMIC_RAW minimum_validation=ok insufficient_space=EAGAIN whole_512=ok large_7777_short_4096=ok PASS\n",1);
}
static int writer(const char *name) {
    check(name && (name[0]=='A' || name[0]=='B') && !name[1],"writer-label");
    unsigned char record[record_bytes];memset(record,name[0],sizeof(record));
    for(unsigned i=0;i<records_per_writer;++i) {
        const ssize_t result=write(1,record,sizeof(record));
        if(result!=sizeof(record)) {
            char text[160];snprintf(text,sizeof(text),"PIPE_ATOMIC_FAIL writer=%c index=%u write_return=%ld expected=512 errno=%d\n",name[0],i,(long)result,errno);log_text(text,2);return 98;
        }
    }
    char text[96];snprintf(text,sizeof(text),"PIPE_ATOMIC_WRITER %c records=64 write_each=512 PASS\n",name[0]);log_text(text,2);
    return 0;
}
static pid_t spawn_writer(const char *path,int reader,int writer_fd,char *label) {
    posix_spawn_file_actions_t actions;
    check(posix_spawn_file_actions_init(&actions)==0,"actions-init");
    check(posix_spawn_file_actions_adddup2(&actions,writer_fd,1)==0 &&
          posix_spawn_file_actions_addclose(&actions,reader)==0 &&
          posix_spawn_file_actions_addclose(&actions,writer_fd)==0,"actions-wire-stdout-and-close");
    char *args[]={"pipe_atomic","writer",label,0};pid_t pid=0;
    const int result=posix_spawn(&pid,path,&actions,0,args,environ);
    check(posix_spawn_file_actions_destroy(&actions)==0,"actions-destroy");
    check(result==0 && pid>0,"spawn-writer");return pid;
}
int main(int argc,char **argv) {
    if(argc==3 && !strcmp(argv[1],"writer"))return writer(argv[2]);
    check(argc==1,"parent-arguments");
    /* Warm formatting before the exact per-process resource snapshot. */
    report_counts("warmup",counts());
    const struct resource_counts baseline=counts();report_counts("baseline",baseline);
    raw_minimum_checks();
    check(equal_counts(baseline,counts()),"raw-probe-resource-rollback");
    int pair[2];check(pipe(pair)==0,"libc-pipe-create");
    pid_t children[2];
    children[0]=spawn_writer("/tests/pipe_atomic",pair[0],pair[1],"A");
    children[1]=spawn_writer("/tests/pipe_atomic",pair[0],pair[1],"B");
    check(close(pair[1])==0,"parent-close-write-after-both-starts");
    unsigned char input[257],record[record_bytes];unsigned offset=0,record_a=0,record_b=0;
    unsigned long total=0,read_calls=0;
    for(;;) {
        const ssize_t got=read(pair[0],input,sizeof(input));check(got>=0,"parent-read");
        if(!got)break;
        ++read_calls;
        for(ssize_t i=0;i<got;++i) {
            record[offset++]=input[i];++total;
            if(offset==record_bytes) {
                const unsigned char expected=record[0];check(expected=='A' || expected=='B',"record-tag");
                for(unsigned j=1;j<record_bytes;++j)check(record[j]==expected,"interleaved-small-write-record");
                if(expected=='A')++record_a;else ++record_b;
                offset=0;
            }
        }
        /* 257 freed bytes cannot admit a 512-byte writer. Let both writers
           run in that window instead of immediately draining another chunk. */
        raw(3,0,0,0);
    }
    check(offset==0 && record_a==64 && record_b==64 && total==65536,"exact-record-counts-and-eof");
    check(close(pair[0])==0,"parent-close-reader");
    for(unsigned i=0;i<2;++i) {int status=0;check(waitpid(children[i],&status,0)==children[i] && WIFEXITED(status) && WEXITSTATUS(status)==0,"writer-final-status");}
    const struct resource_counts final=counts();report_counts("final",final);
    check(equal_counts(baseline,final),"children-pipes-completions-return-to-baseline");
    char text[192];snprintf(text,sizeof(text),"PIPE_ATOMIC_PARENT child_a=%ld child_b=%ld records_A=%u records_B=%u bytes=%lu read_calls=%lu read_chunk=257 eof=1 resource_baseline=ok PASS\n",(long)children[0],(long)children[1],record_a,record_b,total,read_calls);log_text(text,1);
    return 0;
}
