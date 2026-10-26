/* SPDX-License-Identifier: Apache-2.0 */
#ifndef C3_EXEC_COMMON_H
#define C3_EXEC_COMMON_H
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#define STACK_PROBE (0x80000000ul - 36ul * 4096ul + 4096ul + 64ul)
struct c3_info { unsigned version,size; unsigned long reserved,pid,tid,bottom,top,tp; };
struct c3_stats { unsigned version,size; unsigned long reserved; unsigned processes,threads,reservations,waiting,results,free_pages,user_pages,kernel_pages; };
struct c3_entry { unsigned long entry,stack,startup; };
struct c3_mapping { unsigned long address,source; unsigned length,permissions; };
static long c3_call(unsigned long number,unsigned long a,unsigned long b,unsigned long c) {
    long result;
    __asm__ volatile("int $0x80":"=a"(result):"a"(number),"D"(a),"S"(b),"d"(c):"memory");
    return result;
}
static void c3_log(const char *text) {
    unsigned long length=strlen(text);
    while(length) { unsigned long amount=length>256?256:length; long n=c3_call(11,1,(unsigned long)text,amount); if(n<=0)break; text+=n;length-=(unsigned long)n; }
}
static void c3_check(int good,const char *label) {
    if(good)return;
    c3_log("C3_EXEC_FAIL ");c3_log(label);c3_log("\n");
    c3_call(2,94,0,0);for(;;){}
}
static struct c3_info c3_info(void) { struct c3_info value={0};c3_check(c3_call(41,(unsigned long)&value,0,0)==0,"thread-info");return value; }
static struct c3_stats c3_stats(void) { struct c3_stats value={0};c3_check(c3_call(50,(unsigned long)&value,0,0)==0,"thread-stats");return value; }
static void c3_resource_log(const char *label,struct c3_stats value) {
    char line[256];snprintf(line,sizeof(line),"C3_EXEC_RESOURCES %s free=%u processes=%u threads=%u reservations=%u waiting=%u results=%u user_pages=%u kernel_pages=%u\n",label,value.free_pages,value.processes,value.threads,value.reservations,value.waiting,value.results,value.user_pages,value.kernel_pages);c3_log(line);
}
static int c3_same_resources(struct c3_stats a,struct c3_stats b) {return a.free_pages==b.free_pages && a.processes==b.processes && a.threads==b.threads && a.reservations==b.reservations && a.waiting==b.waiting && a.results==b.results && a.user_pages==b.user_pages && a.kernel_pages==b.kernel_pages;}
#endif
