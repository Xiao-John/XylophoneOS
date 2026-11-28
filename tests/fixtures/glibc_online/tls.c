/* SPDX-License-Identifier: Apache-2.0 */
extern int __cxa_thread_atexit_impl (void (*) (void *), void *, void *);
static void *dso_identity = &dso_identity;
static int *events;
static int constructed;
static __thread int value = 31;
static __thread int registered;
static void __attribute__ ((constructor)) begin (void) { ++constructed; }
static void __attribute__ ((destructor)) end (void)
{
  if (events) __atomic_add_fetch (&events[1], 1, __ATOMIC_SEQ_CST);
}
static void tls_end (void *argument)
{
  if (argument == &value && events)
    __atomic_add_fetch (&events[0], 1, __ATOMIC_SEQ_CST);
}
void online_bind (int *state) { events = state; }
int online_constructors (void) { return constructed; }
int online_touch (int amount)
{
  if (!registered)
    {
      if (__cxa_thread_atexit_impl (tls_end, &value, &dso_identity) != 0)
        return -1;
      registered = 1;
    }
  return value += amount;
}
