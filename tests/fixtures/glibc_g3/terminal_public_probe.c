/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

_Static_assert(sizeof(struct termios)==44 && NCCS==20 && VMIN==16 && VTIME==17,"glibc termios layout");
_Static_assert(offsetof(struct termios,c_ispeed)==36 && offsetof(struct termios,c_ospeed)==40,"glibc speed layout");
_Static_assert((CS8|CREAD|CLOCAL)==0x8b00 && B115200==115200,"glibc termios constants");
_Static_assert(TCGETS==0x5401 && FIOCLEX==0x5451,"libc-local ioctl constants");
#ifdef XOS_GLIBC_TERMINAL_EXEC_RECEIVER
/* Remove this fixture-only marker when the separately qualified process
   runtime supplies its global .xos.exec receiver marker. */
struct exec_marker { uint64_t magic; uint32_t version,size; };
__attribute__((used,section(".xos.exec"))) static const struct exec_marker receiver={0x3349424143455858ULL,3,16};
#endif
static int output_fd=1;
static unsigned checks;
static int file_progress, reader_started;

static void text(const char *value) {
    size_t at=0,length=strlen(value);
    while(at<length) { ssize_t count=write(output_fd,value+at,length-at); if(count<=0) _Exit(90); at+=(size_t)count; }
}
static void check(int passed,int line) {
    (void)__atomic_add_fetch(&checks,1,__ATOMIC_RELAXED);
    if(!passed) { char message[128]; snprintf(message,sizeof(message),"GLIBC_TERMINAL_FAIL line=%d errno=%d\n",line,errno); text(message); exit(81); }
}
#define CHECK(value) check((value),__LINE__)
static long long monotonic(void) {
    struct timespec value; CHECK(clock_gettime(CLOCK_MONOTONIC,&value)==0);
    return (long long)value.tv_sec*1000000000LL+value.tv_nsec;
}
static void pause_ms(long milliseconds) {
    pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
    pthread_condattr_t attr; pthread_cond_t condition;
    CHECK(pthread_condattr_init(&attr)==0 && pthread_condattr_setclock(&attr,CLOCK_MONOTONIC)==0);
    CHECK(pthread_cond_init(&condition,&attr)==0 && pthread_condattr_destroy(&attr)==0);
    const long long end=monotonic()+milliseconds*1000000LL;
    struct timespec deadline={(time_t)(end/1000000000LL),(long)(end%1000000000LL)};
    CHECK(pthread_mutex_lock(&mutex)==0);
    CHECK(pthread_cond_timedwait(&condition,&mutex,&deadline)==ETIMEDOUT);
    CHECK(pthread_mutex_unlock(&mutex)==0 && pthread_cond_destroy(&condition)==0 && pthread_mutex_destroy(&mutex)==0);
}
static void *read_worker(void *unused) {
    (void)unused;
    __atomic_store_n(&reader_started,1,__ATOMIC_RELEASE);
    char data[3]={0};size_t at=0;
    while(at<sizeof(data)) { ssize_t n=read(0,data+at,sizeof(data)-at); CHECK(n>0 && (size_t)n<=sizeof(data)-at); at+=(size_t)n; }
    CHECK(__atomic_load_n(&file_progress,__ATOMIC_ACQUIRE)==1);
    CHECK(memcmp(data,"\033[A",3)==0);
    return NULL;
}
static void mode_check(int fd,struct termios *value) {
    CHECK(tcgetattr(fd,value)==0 && value->c_iflag==0 && value->c_oflag==0 && value->c_lflag==0);
    CHECK(value->c_cflag==(CS8|CREAD|CLOCAL) && cfgetispeed(value)==B115200 && cfgetospeed(value)==B115200);
}

int main(int argc,char **argv) {
    struct termios value,original;
    if(argc>1 && !strcmp(argv[1],"inherited")) {
        output_fd=9;
        CHECK(isatty(9)==1 && isatty(2)==1);
        errno=0;CHECK(fcntl(1,F_GETFD)==-1 && errno==EBADF);
        mode_check(9,&value); CHECK(value.c_cc[VMIN]==0 && value.c_cc[VTIME]==1);
        CHECK(close(9)==0);output_fd=2;
        CHECK(tcdrain(2)==0 && tcgetattr(2,&value)==0);
        text("GLIBC_TERMINAL_INHERIT_PASS alias=9 cloexec=1 sequence=resumed mode=retained\n");
        CHECK(close(2)==0);
        return 0;
    }
    CHECK(isatty(0)==1 && isatty(1)==1 && isatty(2)==1);
    struct stat info;CHECK(fstat(0,&info)==0 && S_ISCHR(info.st_mode));
    mode_check(0,&value);CHECK(value.c_cc[VMIN]==1 && value.c_cc[VTIME]==0);
    if(argc>1 && !strcmp(argv[1],"warmup")) { text("GLIBC_TERMINAL_WARMUP_PASS\n");return 0; }
    original=value;value.c_lflag=ICANON;
    errno=0;CHECK(tcsetattr(0,TCSANOW,&value)==-1 && errno==ENOTSUP);
    CHECK(tcgetattr(0,&value)==0 && memcmp(&value,&original,sizeof(value))==0);
    errno=0;CHECK(tcsetattr(0,99,&value)==-1 && errno==EINVAL);
    errno=0;CHECK(tcflush(0,TCOFLUSH)==-1 && errno==ENOTSUP);
    errno=0;CHECK(tcflush(0,99)==-1 && errno==EINVAL);
    errno=0;CHECK(fcntl(0,F_SETFL,O_RDWR|O_NONBLOCK)==-1 && errno==ENOTSUP);
    CHECK(fcntl(1,F_GETFL)==O_RDWR);
    int alias=dup(1);CHECK(alias==3);
    CHECK(ioctl(alias,FIOCLEX)==0 && fcntl(alias,F_GETFD)==FD_CLOEXEC && fcntl(1,F_GETFD)==0);
    CHECK(ioctl(alias,FIONCLEX)==0 && fcntl(alias,F_GETFD)==0);
    errno=0;CHECK(ioctl(alias,0UL)==-1 && errno==ENOTTY);
    errno=0;CHECK(ioctl(32,0UL)==-1 && errno==EBADF);
    CHECK(ioctl(alias,TCGETS,&value)==0 && close(alias)==0);
    value.c_cc[VMIN]=0;value.c_cc[VTIME]=0;
    CHECK(ioctl(0,TCSETS,&value)==0);char byte=0;CHECK(read(0,&byte,1)==0);
    value.c_cc[VTIME]=1;CHECK(ioctl(0,TCSETSW,&value)==0);
    long long begin=monotonic();CHECK(read(0,&byte,1)==0);
    long long elapsed=monotonic()-begin;CHECK(elapsed>=100000000LL && elapsed<2000000000LL);
    value=original;CHECK(ioctl(0,TCSETSF,&value)==0 && tcdrain(1)==0);
    text("GLIBC_TERMINAL_MODE_PASS raw=115200 timed=100ms ioctl=translated\n");

    text("GLIBC_TERMINAL_BLOCK_READY\n");
    pthread_t reader;CHECK(pthread_create(&reader,NULL,read_worker,NULL)==0);
    while(!__atomic_load_n(&reader_started,__ATOMIC_ACQUIRE)) CHECK(sched_yield()==0);
    int file=open("/g3_terminal_file",O_RDWR|O_CREAT|O_TRUNC,0600);CHECK(file==3);
    CHECK(write(file,"file",4)==4 && lseek(file,0,SEEK_SET)==0);
    char content[4];CHECK(read(file,content,sizeof(content))==4 && !memcmp(content,"file",4));
    errno=0;CHECK(tcgetattr(file,&value)==-1 && errno==ENOTTY);
    CHECK(close(file)==0 && unlink("/g3_terminal_file")==0);
    __atomic_store_n(&file_progress,1,__ATOMIC_RELEASE);
    CHECK(pthread_join(reader,NULL)==0);
    text("GLIBC_TERMINAL_BLOCK_PASS escape=raw files=progress\n");

    char payload[600];memset(payload,'W',sizeof(payload));
    ssize_t first=write(1,payload,sizeof(payload));CHECK(first>0 && first<=256);
    size_t done=(size_t)first;
    while(done<sizeof(payload)) { ssize_t n=write(1,payload+done,sizeof(payload)-done);CHECK(n>0 && n<=256);done+=(size_t)n; }
    CHECK(tcdrain(1)==0);text("\nGLIBC_TERMINAL_WRITE_PASS bytes=600 short=bounded\n");

    text("GLIBC_TERMINAL_FLUSH_QUEUE_READY\n");pause_ms(350);
    CHECK(tcflush(0,TCIFLUSH)==0);
    text("GLIBC_TERMINAL_FLUSH_FRESH_READY\n");CHECK(read(0,&byte,1)==1 && byte=='F');
    text("GLIBC_TERMINAL_TCSA_QUEUE_READY\n");pause_ms(350);
    CHECK(tcsetattr(0,TCSAFLUSH,&original)==0);
    text("GLIBC_TERMINAL_TCSA_FRESH_READY\n");CHECK(read(0,&byte,1)==1 && byte=='N');
    text("GLIBC_TERMINAL_FLUSH_PASS discarded=QX fresh=FN\n");

    alias=dup(1);CHECK(alias==3);
    CHECK(close(0)==0 && close(1)==0 && close(2)==0);output_fd=alias;
    file=open("/g3_terminal_reuse",O_WRONLY|O_CREAT|O_TRUNC,0600);CHECK(file==0);
    CHECK(write(file,"independent",11)==11 && close(file)==0 && unlink("/g3_terminal_reuse")==0);
    char message[128];snprintf(message,sizeof(message),"GLIBC_TERMINAL_PASS checks=%u aliases=retained reused_fd=file\n",checks);text(message);
    CHECK(close(alias)==0);
    return 0;
}
