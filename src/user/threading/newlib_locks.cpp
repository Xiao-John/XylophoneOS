// SPDX-License-Identifier: Apache-2.0
#include <pthread.h>
#include <stdlib.h>
#include <xos/sdk.hpp>
#include <sys/lock.h>
struct __lock { pthread_mutex_t mutex; };
#define RECURSIVE_LOCK(name) struct __lock name = {PTHREAD_RECURSIVE_MUTEX_INITIALIZER_NP}
extern "C" {
RECURSIVE_LOCK(__lock___sinit_recursive_mutex);
RECURSIVE_LOCK(__lock___sfp_recursive_mutex);
RECURSIVE_LOCK(__lock___atexit_recursive_mutex);
RECURSIVE_LOCK(__lock___at_quick_exit_mutex);
RECURSIVE_LOCK(__lock___malloc_recursive_mutex);
RECURSIVE_LOCK(__lock___env_recursive_mutex);
RECURSIVE_LOCK(__lock___tz_mutex);
RECURSIVE_LOCK(__lock___dd_hash_mutex);
RECURSIVE_LOCK(__lock___arc4random_mutex);
void __retarget_lock_init(_LOCK_T* lock) {
    auto* value = static_cast<__lock*>(malloc(sizeof(__lock)));
    if (!value) { xos::sdk::exit(127); }
    pthread_mutexattr_t attr;
    pthread_mutexattr_init(&attr); pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_RECURSIVE);
    pthread_mutex_init(&value->mutex, &attr); *lock = value;
}
void __retarget_lock_init_recursive(_LOCK_T* lock) { __retarget_lock_init(lock); }
void __retarget_lock_close(_LOCK_T lock) {
    if (!lock || pthread_mutex_destroy(&lock->mutex) != 0) { xos::sdk::exit(127); }
    free(lock);
}
void __retarget_lock_close_recursive(_LOCK_T lock) { __retarget_lock_close(lock); }
void __retarget_lock_acquire(_LOCK_T lock) {
    if (!lock || pthread_mutex_lock(&lock->mutex) != 0) { xos::sdk::exit(127); }
}
void __retarget_lock_acquire_recursive(_LOCK_T lock) { __retarget_lock_acquire(lock); }
int __retarget_lock_try_acquire(_LOCK_T lock) { return lock && pthread_mutex_trylock(&lock->mutex) == 0; }
int __retarget_lock_try_acquire_recursive(_LOCK_T lock) { return __retarget_lock_try_acquire(lock); }
void __retarget_lock_release(_LOCK_T lock) {
    if (!lock || pthread_mutex_unlock(&lock->mutex) != 0) { xos::sdk::exit(127); }
}
void __retarget_lock_release_recursive(_LOCK_T lock) { __retarget_lock_release(lock); }
}
namespace { pthread_mutex_t file_session_mutex = PTHREAD_RECURSIVE_MUTEX_INITIALIZER_NP; }
extern "C" void xos_file_session_lock() {
    if (pthread_mutex_lock(&file_session_mutex)) { xos::sdk::exit(127); }
}
extern "C" void xos_file_session_unlock() {
    if (pthread_mutex_unlock(&file_session_mutex)) { xos::sdk::exit(127); }
}

namespace { xos::u32 next_file_request_id; }
extern "C" xos::u32 xos_file_request_id() {
    // All Client instances share one process session. Never reuse an ID after
    // a timeout or Client::init, so a late response cannot satisfy a new call.
    if (next_file_request_id == 0xffffffffu) { return 0; }
    return ++next_file_request_id;
}
