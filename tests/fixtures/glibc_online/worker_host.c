/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <tls.h>
#include <ldsodefs.h>
#include "xos_static_worker.h"
#include "xos_thread_entry.h"
#include "xos_thread_exit.h"
#include "xos_thread_tls.h"

size_t dl_tls_static_size = 512 + sizeof(struct pthread), dl_tls_static_align = 64;
struct pthread *online_mock_self;
static _Alignas(64) unsigned char tls_region[4096];
static _Alignas(64) unsigned char stack_region[65536];
static struct xos_thread_start_parameters started;
static int prepare_fail, start_fail, allocate_fail, callback_fail;
static int live_dtvs, releases, retired_releases, aborts, leaving, cleanup_done;
static int begin_result, last_called;
static void *final_dtv;
static jmp_buf finished;

static void *new_dtv(void) {
  dtv_t *p = calloc(18, sizeof(*p)); assert(p); p[0].counter = 16;
  ++live_dtvs; return p + 1;
}
static void free_dtv(void *p) {
  assert(p && !leaving); free((dtv_t *)p - 1); --live_dtvs;
}
void *_dl_allocate_tls(void *p) {
  struct pthread *pd = p;
  assert(pd->header.self == pd && !pd->header.dtv);
  if(allocate_fail) return NULL;
  pd->header.dtv = new_dtv(); return p;
}
void _dl_deallocate_tls(void *p, bool free_tcb) {
  assert(!free_tcb && !leaving);
  free_dtv(((struct pthread *)p)->header.dtv); ++releases;
}
void __xos_dl_release_worker_dtv(void *p) {
  /* Native reaping poisoned the TCB; only the independent heap pointer is valid. */
  assert(!leaving); if(final_dtv) assert(p == final_dtv);
  free_dtv(p); ++retired_releases;
}
xos_i64 __xos_thread_test_call(xos_u64 n, xos_u64 a, xos_u64 b) {
  assert(!leaving);
  if(n == 38) {
    if(prepare_fail) return -5;
    *(struct xos_thread_reservation *)(uintptr_t)b = (struct xos_thread_reservation){
      .tid=23, .stack_bottom=(uintptr_t)stack_region,
      .stack_top=(uintptr_t)(stack_region+sizeof(stack_region)),
      .tls_begin=(uintptr_t)tls_region, .tls_end=(uintptr_t)(tls_region+sizeof(tls_region))};
    return 0;
  }
  if(n == 39) {
    const struct xos_thread_start_request *p = (const void *)(uintptr_t)a;
    if(start_fail) return -2;
    started=(struct xos_thread_start_parameters){p->entry,p->argument,p->stack,p->thread_pointer};
    online_mock_self=(void *)(uintptr_t)p->thread_pointer; return 0;
  }
  assert(n == 40 && a == 23 && live_dtvs == 0); ++aborts; return 0;
}
long __xos_thread_test_trap(unsigned long n, unsigned long a) {
  if(n == 42) { assert(cleanup_done && !a && !leaving); leaving=begin_result==0; return begin_result; }
  if(n == 43) {
    assert(leaving && a == 0xabcdeful && live_dtvs == 1);
    memset(tls_region,0xed,sizeof(tls_region)); leaving=0; longjmp(finished,1);
  }
  assert(n == 2 && a == 127); longjmp(finished,2);
}
void __xos_thread_entry(const struct xos_thread_entry_args *p) { p->run(p->argument); abort(); }
static xos_i64 prepare(struct pthread *pd,const struct xos_thread_reservation *r,void **arg) {
  assert(r->tid==23 && pd->header.dtv && *arg==(void *)42);
  *arg=(void *)43; return callback_fail ? -5 : 0;
}
static void *run(void *p) {
  assert(p==(void *)43 && !cleanup_done);
  /* A runtime lookup grows/replaces the setup-time array. */
  free_dtv(online_mock_self->header.dtv);
  online_mock_self->header.dtv=new_dtv(); final_dtv=online_mock_self->header.dtv;
  return (void *)0xabcdeful;
}
static void cleanup(void) { assert(!leaving && live_dtvs==1); cleanup_done=1; }
static void last_exit(void) {
  assert(!leaving && cleanup_done && live_dtvs==1);
  assert(online_mock_self->header.dtv==final_dtv); ++last_called; longjmp(finished,1);
}
static const struct xos_thread_worker worker={run,(void *)42,cleanup,last_exit,prepare};
static void capacity(void) {
  int slots[4]; for(int i=0;i<4;++i) { slots[i]=__xos_thread_tls_reserve(); assert(slots[i]>=0); }
  assert(__xos_thread_tls_reserve()==-1);
  for(int i=0;i<4;++i) __xos_thread_tls_cancel(slots[i]);
}
int main(void) {
  struct xos_thread_launch_result result;
  capacity();
  prepare_fail=1; assert(__xos_shared_worker_launch(sizeof(stack_region),0,&worker,&result)==-5);
  assert(!result.tid && !aborts && !live_dtvs); prepare_fail=0; capacity();
  allocate_fail=1; assert(__xos_shared_worker_launch(sizeof(stack_region),0,&worker,&result)==-17);
  assert(!result.tid && aborts==1 && releases==0 && !live_dtvs); allocate_fail=0; capacity();
  callback_fail=1; assert(__xos_shared_worker_launch(sizeof(stack_region),0,&worker,&result)==-5);
  assert(!result.tid && aborts==2 && releases==1 && !live_dtvs); callback_fail=0; capacity();
  start_fail=1; assert(__xos_shared_worker_launch(sizeof(stack_region),0,&worker,&result)==-2);
  assert(!result.tid && aborts==3 && releases==2 && !live_dtvs); start_fail=0; capacity();
  assert(__xos_shared_worker_launch(sizeof(stack_region),0,&worker,&result)==0 && result.started);
  begin_result=0; if(!setjmp(finished)) __xos_thread_entry((void *)(uintptr_t)started.argument);
  assert(live_dtvs==1 && retired_releases==0);
  __xos_thread_tls_drain(); assert(!live_dtvs && retired_releases==1); final_dtv=NULL; capacity();
  cleanup_done=0;
  assert(__xos_shared_worker_launch(sizeof(stack_region),0,&worker,&result)==0 && result.started);
  begin_result=1; if(!setjmp(finished)) __xos_thread_entry((void *)(uintptr_t)started.argument);
  assert(last_called==1 && live_dtvs==1 && retired_releases==1);
  capacity(); free_dtv(final_dtv); final_dtv=NULL;
  for(int i=0;i<100;++i) {
    int slot=__xos_thread_tls_reserve(); assert(slot>=0);
    __xos_thread_tls_retire(slot,new_dtv());
  }
  __xos_thread_tls_drain(); assert(!live_dtvs && retired_releases==101); capacity();
  puts("ONLINE_WORKER_TLS_PASS capacity rollback_prepare_alloc_callback_start retire_final_dtv dead_tcb last_preserved recycle_100");
}
