# Holder-local bulk grant release qualification

The native SDK caller passed **nine scenarios in three rounds** on system
`195d5d46abcdd9e3`, with QEMU 11.1.3. The caller linked the matching exported
SDK and thread core; no libc socket adapter or Net2 service supplied these
results. The kernel release implementation is the independently reviewable
`fcb64e46` change. The system also contains unqualified network work; this
report qualifies only the generic grant mechanism exercised here.

| Scenario | Actual guest observation |
| --- | --- |
| Feature and shape compatibility | Query flags 0/1 retain the old mask; flags 2/3 return the opt-in release mask; malformed release input preserves the mapping; global close still requires manage rights; a released handle is stale |
| Holder quota | Eight handles exhaust the holder limit; releasing one admits a replacement |
| Reservation preflight | Two separate mappings need two reservation slots; one free slot returns `resources` and preserves both mappings and the handle; two free slots permit atomic release |
| Pinned mapping | A real second thread blocks in notification wait with its request inside the grant mapping; process inspection observes two threads and one blocked thread; release returns `busy` without partial unmap; signal, join and retry succeed |
| Foreign process | A child cannot release the parent's undelegated handle |
| Owner releases first | The child retains its read-only mapping; object and process-tree budget charges remain with the original owner until the final reference |
| Holder releases first | The parent's two mappings remain usable; only the child's handle and mapping disappear |
| Holder exits first | Exit cleanup retires the child's mapping while preserving the parent's mappings |
| Owner exits first | The child retains its mapping after owner exit, then releases the last reference; the orphan is automatically reaped |

Every scenario in every round restored `[free pages, tasks, completions]`
exactly to `[129769, 2, 0]`. The probe additionally checks the original owner
and tree-domain accounting around the delegated object and its backing and
mapping pages. It uses the accounting syscall exported by this exact SDK;
this is not a claim that an unrelated or newer kernel was exercised.

The supplementary host preflight suite passed eight scenarios for each of
eager and COW fork admission. The old/current SDK query compatibility test
also passed. Its printed `CASES_PASSED=9` label is inherited from the earlier
test revision and is not used as the count of extended assertions here.

## Evidence and reproduction

`guest.json` records all 27 cases, artifact hashes, SDK tree and thread-core
hashes. `guest_serial.log.gz` preserves the exact serial bytes. `system.json`
binds the tested image to its source and artifact hashes. `preflight_host.log`
and `query_compat_host.log` provide supplementary host results. Host paths in
public derivatives use explicit templates; original private receipt hashes
are in `raw_receipts.json`. The flat `manifest.json` hashes every public file.

Build a system with the release implementation and current fixture sources,
then run:

```sh
python3 tests/ipc_grant_release_guest.py \
  --system build/release_system --output build/release_guest --runs 3
```

The runner rejects changed source or image hashes and compiles a fresh caller
from that system's exported SDK and thread core. Its native loader uses the
ordinary 128 KiB image limit. The test stops and waits for the installation's
network service before taking the resource baseline.

## Retained failures and limits

The first formal attempt passed feature, quota, fragmentation and pinning
cases, then failed because the child fixture expected an implicit `argv[0]`.
The native spawn API supplies exactly the arguments requested. Subsequent
diagnostics corrected three fixture issues: using the actor wait API for a
plain IPC channel, exiting the owner before the child acknowledged the final
barrier, and asking the shell to wait for an orphan it did not own. These
failed receipts and serial transcripts are retained and labeled diagnostic;
they are not counted as qualification passes. No kernel change was required
to resolve those fixture failures. A compatibility-test invocation inside the
isolated SDK environment could not access the worktree's Git metadata; its
failed log is retained, followed by the passing host invocation.

This does not qualify allocation fault injection, multicore shootdown, or a
target VM-continuation race. The host preflight test covers the VM-state
rejection branch, while the actual guest covers pinned and reservation-table
failures. The separate network readiness report must qualify its own producer
and consumer use of the generic mechanism.
