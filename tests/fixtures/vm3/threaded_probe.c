// SPDX-License-Identifier: Apache-2.0
#include <sys/mman.h>
#include <pthread.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
static void* worker(void* arg) { volatile unsigned char* p=(volatile unsigned char*)arg; p[4095]=71;return arg; }
int main(void) {
 void* p=mmap(0,4096,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(p==MAP_FAILED || mprotect(p,4096,PROT_READ|PROT_WRITE))return 1;
 pthread_t tid;void* result=0;
 if(pthread_create(&tid,0,worker,p) || pthread_join(tid,&result) || result!=p || ((volatile unsigned char*)p)[4095]!=71)return 2;
 errno=0;if(fork()!=-1 || errno!=ENOTSUP)return 3;
 if(mprotect(p,4096,PROT_NONE) || mprotect(p,4096,PROT_READ|PROT_WRITE) || ((volatile unsigned char*)p)[4095]!=71 || munmap(p,4096))return 4;
 puts("VM3_THREADED_SDK_PASS");return 0;
}
