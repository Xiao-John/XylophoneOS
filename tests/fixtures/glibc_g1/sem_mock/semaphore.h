/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TEST_SEMAPHORE_H
#define TEST_SEMAPHORE_H
#include <stdint.h>
typedef union { char bytes[32]; long align; } sem_t;
#endif
