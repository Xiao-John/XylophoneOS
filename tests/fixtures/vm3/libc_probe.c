// SPDX-License-Identifier: Apache-2.0
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
int main(int argc, char** argv) {
 if(argc>1) {
  void* f=mmap(0,4096,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
  if(f==MAP_FAILED)return 20;
  volatile unsigned char* b=(volatile unsigned char*)f;
  if(!strcmp(argv[1],"none")) { puts("VM3_FAULT_NONE");return b[0]; }
  if(mprotect(f,4096,PROT_READ|PROT_WRITE))return 21;
  b[0]=0xc3;
  if(!strcmp(argv[1],"readonly")) {
   if(mprotect(f,4096,PROT_READ))return 22;
   puts("VM3_FAULT_READONLY");b[0]=0;return 23;
  }
  if(!strcmp(argv[1],"rwexec")) {
   puts("VM3_FAULT_RWEXEC");return ((int (*)(void))f)();
  }
  return 24;
 }
 errno=0;
 if(mmap(0,4096,PROT_READ,MAP_PRIVATE|MAP_ANONYMOUS,-1,0)!=MAP_FAILED || errno!=ENOTSUP)return 1;
 void* p=mmap(0,8192,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(p==MAP_FAILED || mprotect(p,8192,PROT_READ|PROT_WRITE))return 2;
 volatile uint64_t* v=(volatile uint64_t*)p; v[0]=17;v[512]=23;
 if(mprotect((char*)p+4096,4096,PROT_NONE))return 3;
 pid_t child=fork();
 if(child<0)return 4;
 if(!child) {
  if(mprotect((char*)p+4096,4096,PROT_READ|PROT_WRITE) || v[0]!=17 || v[512]!=23)_exit(5);
  v[0]=91;_exit(0);
 }
 int status=0;
 if(waitpid(child,&status,0)!=child || !WIFEXITED(status) || WEXITSTATUS(status))return 6;
 if(mprotect((char*)p+4096,4096,PROT_READ|PROT_WRITE) || v[0]!=17 || v[512]!=23)return 7;
 if(munmap(p,8192))return 8;
 puts("VM3_LIBC_PASS");return 0;
}
