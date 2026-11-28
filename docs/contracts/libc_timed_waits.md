# libc elapsed waits and explicit interruption

This glibc profile extends the existing elapsed sleeps with a process-local
interruption mechanism. It uses the existing monotonic clock and private
wait-word syscalls 46, 48 and 49; no syscall number or kernel object is added.
The public functions are `nanosleep`, `clock_nanosleep`, and the XOS extension
declared in the installed `xos/sleep.h`. The frozen SDK remains unchanged.

## Deadlines and public results

Relative waits on `CLOCK_MONOTONIC` or `CLOCK_REALTIME` form one absolute
monotonic deadline. `TIMER_ABSTIME` on `CLOCK_MONOTONIC` uses the supplied
deadline directly; an expired deadline succeeds immediately. Absolute
`CLOCK_REALTIME` uses the existing fixed boot-RTC offset and rechecks realtime
after a translated wait. It cannot finish before the original realtime target.
Each translated segment has its own ticket; a ticket for an earlier segment
cannot interrupt a later one. Wall-clock adjustment is not supported.

Negative seconds, nanoseconds outside 0..999999999 and invalid flags are
`EINVAL`; unsupported CPU clocks are `ENOTSUP`. Nanosecond conversion and
relative addition must fit the clock's signed nonnegative 64-bit domain or
return `EOVERFLOW`. A null request is `EFAULT`. Zero duration performs no wait.
Parameter errors, native errors and successful waits leave `remaining` alone.

`clock_nanosleep` returns an error number and preserves `errno`. On a committed
explicit interruption it returns `EINTR`. For relative waits only, a non-null
`remaining` receives `max(deadline - monotonic_now, 0)` split into seconds and
nanoseconds. `TIMER_ABSTIME` never writes `remaining`. The upstream `nanosleep`
wrapper returns -1 and sets `errno` on errors, including `EINTR`.
Scheduling can delay the return; a wake does not create a new deadline.

## Ticket ABI and authority

`struct xos_sleep_ticket` is 48 bytes: four `uint32_t` fields named `version`,
`size`, `reserved`, `reserved2`, followed by four `uint64_t` fields named `pid`,
`tid`, `sequence`, `deadline_ns`. Version is 1, size is 48, both reserved fields
are zero. The monotonic deadline is finite. Sequence is process-local,
nonzero, monotonically allocated, and never wraps.

`xos_sleep_query(pthread_t target, struct xos_sleep_ticket *output)` returns a
copy of the target's active wait identity. The public `pthread_t` is the full
native TID and is never dereferenced as a TCB pointer. No matching active wait
returns `ESRCH`; target zero is `EINVAL`, output null is `EFAULT`. Failure leaves
the output untouched. A query is observational: it does not pin a wait or
ensure that the target remains blocked after the snapshot.

`xos_sleep_interrupt(const struct xos_sleep_ticket *ticket)` only affects the
matching active PID, TID, sequence and deadline in the calling process.
Malformed fields are `EINVAL`, null is `EFAULT`, another PID is `EPERM`, and
an absent/retired/mismatching ticket is `ESRCH`. An already committed interrupt
is `EALREADY`. An un-interrupted wait whose original deadline has elapsed is
`ETIMEDOUT` and remains unmodified. Both extension functions return error
numbers without changing `errno`. Same-process threads already share memory;
this API grants no cross-process observation or interruption authority.

## Races, capacity and cleanup

The table contains four active waits, matching the kernel's four-thread
process limit. A full table fails with `EAGAIN`; sequence exhaustion fails
with `EOVERFLOW`. These failures do not allocate a wait. Entries and snapshots
are serialized by a process-local lock. Interrupt stores the wake word before
the native wake; the atomic compare/enqueue in wait-word prevents a lost wake
between registration and blocking. Interrupt accepted before the original
deadline wins even if the target resumes after that deadline. Timeout wins
when the interrupt first observes an already elapsed deadline.

Wait-word may wake early or spuriously. The waiter rechecks the committed
interrupt and the monotonic deadline, then waits against that same deadline.
It retires the entry before returning. A late ticket cannot interrupt a later
sleep even on the same TID and reused table slot. No service request/reply is
sent, so there is no external late reply to adopt or replay. A failed native
wait remains an error even when the original deadline has meanwhile elapsed.
A failed native wake is reported as an error without rolling back the already visible
interrupt; the waiter still sees it at its original deadline.
An unexpected failure to acquire the private retirement lock is fatal: the
runtime cannot return while leaving an active entry behind. Process teardown
then reclaims the table and native waits instead of leaking a live ticket.

Static single-thread fork resets the child's table, lock and sequence. Ticket
PID prevents an inherited value from authorizing the child. Successful exec
replaces the entire table with the new runtime; failed exec preserves the
original process. The supported single-thread exec caller cannot itself be in
an active sleep. Process exit, kill or a fatal thread fault reclaim the whole
address space, including waits. Normal sleep completion frees its entry.

This is not POSIX signal delivery, `pthread_cancel`, asynchronous cancellation,
or a general interruptible-wait service. `pthread_cancel` continues to return
`ENOTSUP`. Other blocking APIs do not consume sleep tickets. Older SDKs retain
their original non-interruptible sleep implementation. Applications using
the new extension must be rebuilt with its matching SDK and libc.

## Qualification

The target suite observes native `thread_stats.waiting` while a captured sleep
ticket is active before delivering the interrupt. It exercises both public
sleep wrappers, relative remaining time, absolute remainder preservation,
stale and duplicate requests, invalid identity, fork reset, full thread
capacity and late requests during a later wait. Existing clock conversion
tests continue to cover invalid parameters, overflow and RTC failure.
Host fault injection tests supplement, and do not replace, the real target.
