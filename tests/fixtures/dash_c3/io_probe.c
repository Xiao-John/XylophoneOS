/* SPDX-License-Identifier: Apache-2.0 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#ifndef XOS_REFERENCE
extern int xos_open_anonymous(void);
#endif
static char data[3503];
static int send_all(int fd,const void *raw,size_t length) {
    const char *p=raw;
    while(length){ssize_t n=write(fd,p,length);if(n<=0)return -1;p+=n;length-=(size_t)n;}
    return 0;
}
static int copy(int fd) {
    for(;;){ssize_t n=read(0,data,sizeof(data));if(n<0)return 10;if(!n)return 0;if(send_all(fd,data,(size_t)n))return 11;}
}
#ifndef XOS_REFERENCE
static int anonymous_test(void) {
    for(int round=0;round<2;++round){
        int fds[16];
        for(int i=0;i<16;++i){fds[i]=xos_open_anonymous();if(fds[i]<0)return 20;}
        errno=0;int extra=xos_open_anonymous();
        if(extra>=0||errno!=EMFILE)return 21;
        for(int i=0;i<16;++i){
            char got[5];
            if(send_all(fds[i],"anon!",5)||lseek(fds[i],0,SEEK_SET)!=0||read(fds[i],got,5)!=5||memcmp(got,"anon!",5)||close(fds[i]))return 22;
        }
    }
    errno=0;if(open("/XOS00000.TMP",O_RDONLY)>=0||errno!=EINVAL)return 23;
    errno=0;if(open("/XOS00000.TMP",O_WRONLY|O_TRUNC)>=0||errno!=EINVAL)return 24;
    errno=0;if(unlink("/XOS00000.TMP")!=-1||errno!=EINVAL)return 25;
    int keep=open("/out/c3_keep.txt",O_CREAT|O_TRUNC|O_WRONLY,0600);
    if(keep<0||send_all(keep,"keep",4)||close(keep))return 26;
    errno=0;if(rename("/out/c3_keep.txt","/XOS00000.TMP")!=-1||errno!=EINVAL)return 27;
    puts("C3_ANON slots=16 extra=EMFILE rounds=2 paths=reserved PASS");return 0;
}
static int anonymous_share(void) {
    int fd=xos_open_anonymous(),start[2],done[2],status;
    if(fd<0||send_all(fd,"shared",6)||lseek(fd,0,SEEK_SET)!=0||pipe(start)||pipe(done))return 30;
    pid_t child=fork();if(child<0)return 31;
    if(!child){
        close(start[1]);close(done[0]);char ch,got[6];
        if(read(start[0],&ch,1)!=1||read(fd,got,6)!=6||memcmp(got,"shared",6)||close(fd)||send_all(done[1],"Y",1))_exit(32);
        _exit(0);
    }
    close(start[0]);close(done[1]);
    if(close(fd)||send_all(start[1],"X",1)||close(start[1]))return 33;
    char ch;if(read(done[0],&ch,1)!=1||ch!='Y'||read(done[0],&ch,1)!=0||close(done[0]))return 34;
    if(waitpid(child,&status,0)!=child||!WIFEXITED(status)||WEXITSTATUS(status))return 35;
    puts("C3_ANON fork_reference_survives_parent_close last_close=clean PASS");return 0;
}
#endif
int main(int argc,char **argv){
    if(argc<2)return 2;
    if(!strcmp(argv[1],"read_only")){
        errno=0;
        if((fcntl(0,F_GETFL)&O_ACCMODE)!=O_RDONLY||write(0,"X",1)!=-1||errno!=EBADF)return 15;
        int result=copy(1);if(result)return result;
        puts("C3_HEREDOC write0=EBADF bytes=unchanged");return 0;
    }
    if(!strcmp(argv[1],"copy"))return copy(1);
    if(!strcmp(argv[1],"save")){
        if(argc!=3)return 3;int fd=open(argv[2],O_CREAT|O_TRUNC|O_WRONLY,0600);if(fd<0)return 12;
        int result=copy(fd);if(close(fd))return 13;return result;
    }
    if(!strcmp(argv[1],"absent")){
        struct stat s;if(argc!=3)return 3;errno=0;
        if(stat(argv[2],&s)!=-1||errno!=ENOENT)return 14;
        puts("C3_ABSENT verified");return 0;
    }
    if(!strcmp(argv[1],"spin")){fputs("C3_SPIN_READY\n",stderr);for(;;)__asm__ volatile("":::"memory");}
    if(!strcmp(argv[1],"fault")){*(volatile char *)0x1000=1;return 99;}
#ifndef XOS_REFERENCE
    if(!strcmp(argv[1],"anonymous"))return anonymous_test();
    if(!strcmp(argv[1],"anonymous_share"))return anonymous_share();
#endif
    return 4;
}
