/* SPDX-License-Identifier: Apache-2.0
   Existing native runtime prepares a real terminal v3 exec handoff to glibc. */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <termios.h>
#include <unistd.h>
struct tty_marker { uint64_t magic; uint32_t version,size; };
__attribute__((used,section(".xos.tty"))) static const struct tty_marker marker={0x31595454534f5858ULL,1,16};
#define CHECK(value) do { if(!(value)) { printf("GLIBC_TERMINAL_PARENT_FAIL line=%d errno=%d\n",__LINE__,errno);return 82; } } while(0)
int main(int argc,char **argv) {
    CHECK(argc==2 && isatty(1)==1);
    struct termios value;CHECK(tcgetattr(1,&value)==0);
    value.c_cc[VMIN]=0;value.c_cc[VTIME]=1;
    CHECK(tcsetattr(1,TCSANOW,&value)==0 && dup2(1,9)==9);
    CHECK(close(0)==0 && fcntl(1,F_SETFD,FD_CLOEXEC)==0);
    puts("GLIBC_TERMINAL_PARENT_READY sequence=advanced mode=timed alias=9");
    CHECK(fflush(stdout)==0);
    char *arguments[]={argv[1],"inherited",NULL};
    execv(argv[1],arguments);
    CHECK(0);
    return 82;
}
