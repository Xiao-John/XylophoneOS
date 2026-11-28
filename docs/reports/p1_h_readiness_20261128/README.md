# P1-H connected-socket readiness qualification

**PASS — 43 actual guest cases on the normal kernel configuration.** The final
run includes twenty independently observed pending-poll close/reuse races;
every one returned `1` with `POLLNVAL` in 20–30 ms and restored its resource
baseline. The static GNU socket caller, Net2 service, native ownership probes,
image, compiler, SDK and profile are bound by the retained receipts.

## Final result and binding

| Item | Final observation |
| --- | --- |
| Source checkpoint | `401614a2258d8d459cda462c250dcdc13c950304`, after `8fe347fc` and `6f96f9f4` |
| System build | `a84e3828dab08a67`; VM/COW and other private fault probes disabled |
| ISO SHA-256 | `a9577afc2b4c2b9ddb2eec576bbea0c9ffa9e1af9d5e531a6d6a6496e7205258` |
| GNU SDK tree | `002f7b684bd7337a0d90a971ff21c0bab3654fe08fedbc0dcd544bd6b241e096` |
| Profile | `xos-x86_64-glibc-p1h-readiness-v7` |
| GNU caller ELF SHA-256 | `b36b9929fa99731f63d9704da3a0e7c80079f5019022579a6fb816c7d11c4f72` |
| Tools | GCC 16.2.0, glibc 2.44, QEMU 11.1.3; TCG, one virtual CPU, 512 MiB |
| Normal quiet resources | `[129769, 2, 0]` — free pages, tasks, completions |
| Two running service generations | PIDs 17 and 54; both baselines `[129596, 3, 1]` |
| Close/reuse | 20/20 observed with two threads and one blocked; 20–30 ms; no old readiness attached to the replacement FD |
| Stalled authenticated peer | Requested 40 ms, observed 40 ms; one capability and one readiness query; one-second late reply consumed once |
| Independent packet peer | Withheld SYN/ACK, buffered receive/consume, zero advertised window, 5840 queued bytes later verified, one FIN |

Every recorded case restores the corresponding baseline. After both service
lifetimes and the separate packet-peer boot, resources return exactly to the
quiet baseline. The earlier probe-enabled 43-case pass is supplementary and is
recorded separately below. The final result is in `guest.json`; the compressed
serial logs preserve complete serial CR/LF bytes and `window.pcap` retains the
independent network observation.

## Contract exercised

The implementation adds an opt-in Net2 revision-2 capability response, a
retained read-only readiness page, read shutdown, nonblocking connection
handling and explicit descriptor readiness. The shared page uses existing
sys88 bulk grants and the separately qualified holder-local release action.
No new networking syscall or POSIX cancellation-delivery mechanism is added.

An even seqlock only establishes a coherent snapshot. A negative `poll(0)`
result additionally requires a sample strictly later than call entry; an equal
coarse clock tick, old page or in-progress writer returns `EAGAIN`. Endpoint
identity and session generation are checked, and every record is bound to the
original connection handle. Consumed read data cannot remain positively ready
on the same serialized description. Write readiness remains a capacity hint.

A finite poll keeps one caller deadline across transport and descriptor work.
It first scans every descriptor without waiting, so a stalled socket cannot
hide a later ready file or pipe. An accepted read-only query can remain pending
after timeout, but its late reply is consumed at most once. Both successful and
timed-out queries recheck the original FD/open-description identity. A close
or reuse produces `POLLNVAL` instead of transferring old readiness to a new FD.

| Target scenario | Required observation |
| --- | --- |
| Live stalled peer | Old consistent negative page returns `EAGAIN`; a 40 ms poll times out before the peer's delayed one-second reply; the next poll consumes that reply without repeating capability/readiness requests |
| Mixed descriptors | A socket before a ready Files FD and both ready pipe directions cannot delay their positive result until its service deadline |
| Page rights and ownership | Read mapping succeeds; write mapping, redelegation, foreign mapping and manage-only global revoke are denied; repeated bind retains the same session identity |
| Page quotas and lifetime | Filling client grant handles rejects bind atomically; releasing one permits bind; client detach/exit and producer exit preserve the other holder's safe reference and reclaim it at final release |
| Deferred local release | Actual VM reservation-fragment pressure makes release temporarily fail; the retained retired handle blocks a replacement connection with `EAGAIN`; freeing a fragment permits cleanup and reconnect |
| Real TCP transfer | Independent random nonce/challenge exchanges, short writes, FIN/EOF, descriptor duplicates and repeated service lifetimes complete |
| Nonblocking connect | Deliberately withheld SYN/ACK yields real `EINPROGRESS` and `EALREADY`; poll/SO_ERROR observe completion; refused connections report their error |
| Read and combined shutdown | SHUT_RD discards/ACKs input while writes survive; SHUT_RDWR preserves successful first-step effects and handles clean transport retirement between its two requests |
| Shutdown authorization | A separate live process cannot shut down or query the owner's TCP handle; own UDP read-shutdown is unsupported; the owner still exchanges a fresh challenge and closes normally |
| Pending close/reuse | Twenty independent real pthread polls are each observed through process inspection with two threads and one blocked; another thread closes and reuses the exact FD; old poll reports `POLLNVAL`, unrelated Files I/O survives and late peer data cannot attach to the new description |
| Write pressure | The packet peer advertises a zero TCP window; the caller fills its 5840-byte send buffer to EAGAIN; reopening/ACKing the window restores finite and immediate write readiness |
| Pipe readiness | Empty/full buffers, readable data, EOF/HUP, no-reader ERR/EPIPE and stale descriptors are checked through the generic non-consuming pipe query |

## Scope and boundaries

This is a **static GNU outbound IPv4 TCP** and named descriptor subset. It does
not establish complete POSIX sockets or `poll`, UDP through the GNU socket API,
listen/accept/bind, arbitrary socket options, terminal-actor or console
readiness, physical NIC behavior, or a newly assembled dynamic runtime.
Nonblocking socket operations do one bounded service exchange; they are not a
promise that IPC delivery itself is wait-free. `pthread_cancel` remains
`ENOTSUP`.

Target descriptor cases directly exercise regular Files descriptors and
independent native pipe ends. Pipe-backed stdio uses the generic query path;
this report adds no separate qualification of inherited stdio routing. An immediate mixed result reports
observed positives; it does not certify negative freshness for an unreported
unknown socket. An all-negative immediate connected-socket result still
requires fresh negatives for every socket. Old services without the page
capability retain the explicit unsupported immediate path. Legacy Net2 and
sys88 feature discovery retain their existing opt-in compatibility rules.

The page producer has read/write/delegate rights and no manage right. Neither
peer can globally revoke the other's mapping. Only the holder-local release
operation retires its own handle and mappings; deferred cleanup retains at most
one invalidated page and does not allocate replacement sessions over it.
The separate generic grant report covers pinned mappings, aggregate unmap
preflight, budget ownership, both release orders and both process-exit orders.

## Reproduction and evidence

Build the system with the locked lwIP archive and installation input:

```json
{"revision":1,"pci_instance":41,"resolver":"10.0.2.3"}
```

Use the pinned SDK tool environment and new private output directories. The
reservation-fragment fixture uses the ordinary public VM reserve/unmap API;
the final image enables no additional VM diagnostic entry points.

```sh
XOS_LWIP_SOURCE_ARCHIVE=build/inputs/lwip-2.2.1.tar.xz python3 scripts/build.py \
  --output-dir build/p1h_system_v13 --net-static-profile build/inputs/static_profile.json
python3 scripts/build_glibc_sdk.py --archive build/inputs/glibc-2.44.tar.xz \
  --output build/p1h_glibc_sdk_v7 --jobs 1
python3 scripts/create_xypm_profile.py create --runtime-family glibc \
  --sdk-build build/p1h_glibc_sdk_v7 --id xos-x86_64-glibc-p1h-readiness-v7 \
  --output build/p1h_profile_v7.json
XOS_QMP_TRANSPORT=pipe python3 tests/glibc_net2_tcp_guest.py \
  --system build/p1h_system_v13 --sdk build/p1h_glibc_sdk_v7 \
  --profile build/p1h_profile_v7.json --output build/p1h_guest_v7
```

The runner verifies current source hashes, SDK/profile identity, all system
artifacts and C/C++ wire layouts before compiling a fresh caller. The socket
caller uses the rebuilt libc; the grant and ownership callers use the same
system's native SDK. A second boot uses an independently implemented packet
peer for handshake and TCP-window barriers. No stale SDK or mismatched image
is promoted by the final result.

The final evidence includes the guest receipt, both serial transcripts, TCP
packet capture, profile, SDK/system/caller receipts and host regressions.
Public derivatives substitute explicit path templates; original receipt hashes
are kept in `raw_receipts.json`. Non-UTF-8 verifier-log bytes are rendered as
hex escapes, with that transformation recorded beside the original hash. Gzip preserves serial CR/LF bytes. The flat
`manifest.json` hashes all public files directly. Hashes retained inside the
build/guest receipts describe original source artifacts; only the flat manifest
verifies the exported leaves. The SDK's own build manifest
keeps its build-time `guest_qualification: not_run`; this separate report binds
the later actual result without rewriting frozen build metadata.

## Retained failures and corrections

The initial caller compile needed `_GNU_SOURCE` for its existing `pipe2`
declaration. The first actual stalled-peer run exposed a same-clock-tick
negative snapshot being accepted; strict post-entry sampling fixed it.
A separate actual diagnostic then exposed misuse of manage-only global grant
close by peers that deliberately lacked manage rights. The generic holder-local
release extension and its independent 27-case guest report resolved that
lifetime defect.

A later real nonblocking/SHUT_RDWR case failed when the clean TCP FIN retired
its PCB between write and read shutdown. Local read shutdown now accepts the
still-owned established description and discards buffered data without touching
the retired PCB. The first host regression for this case accidentally reused a
helper that asserted one lifetime SYN across two connections; its retained
failure is followed by a separate passing scenario.

An earlier complete 23-case guest run is retained as a prior subset. Review
then found that a successful late query needed the same post-query descriptor
identity check as a timeout, and that waiting on the first socket could hide a
later ready descriptor. The final caller and host regression include those
corrections, and the final actual run adds mixed-FD and separate-process
shutdown ownership observations. The earlier pass is not reused as evidence
for the changed code.

One new SDK build using `make -j8 lib` failed while generated `Versions.defT`
and `Versions.mk` were concurrently updated. The failed manifest, full log and
generated files are retained. The final SDK is built from a new directory with
`--jobs 1`; no failed tree is patched into a passing receipt. ASan and UBSan
host checks supplement the target tests; LeakSanitizer is disabled because the
executor uses ptrace, and no LSan pass is claimed.

The next strict actual run exposed a concurrent-close failure after the earlier
17 scenarios passed. An isolated diagnostic initially passed, then its sixth
repeat returned `poll = -1`, `errno = EAGAIN`, no events, after 20 ms. The FD
identity helper correctly uses a nonblocking Files-table lock, but the new
post-query check incorrectly propagated transient contention out of a finite
poll. The correction retries identity checks within the original deadline and
discards an event until identity is confirmed. Deterministic host cases cover
contention before a query, contention after a successful late reply and FD
reuse, immediate unknown state, and a lock busy through the deadline. The final
actual runner repeats the observed-pending close/reuse case twenty times and
checks each run's own output, rather than accepting a marker from an earlier
run. Both the original strict failure and the diagnostic failure are retained.

A subsequent 43-case strict run passed with the repaired SDK, including all
twenty pending-close repetitions (20–70 ms) and 5840-byte zero-window recovery.
Its system `c86e685b8bf4c00b` had the additional `vm1_probe` build flag enabled.
The ordinary public VM API is sufficient for the fragment-pressure fixture,
so the probe-enabled result is retained separately and is not substituted for
the final normal-configuration system. Its quiet baseline was `[129704, 2, 0]`,
and both service baselines were `[129531, 3, 1]`; all recovered exactly.

## Integration handoff

The implementation depends on the separately delivered generic holder-local
grant release and generic pipe-status query. The H source commits are
`8fe347fc`, `6f96f9f4`, then `401614a2`; the generic implementation is not
repackaged as a networking change. Preserve the explicit sys88 feature opt-in
and old feature masks when integrating later kernel or SDK work. A different
SDK/runtime/image combination requires its own affected-target checks.

The path review's ambiguous temporary-path findings refer to actual guest
Files paths in the socket fixture and its retained diagnostic copy. The FAT
fixture explicitly creates that guest directory. Host paths are represented by
the named templates above.

The full repository report-manifest checker lists this H report as compliant,
but its overall run fails on 17 existing format/path entries in ten other
report directories. Their Git tree objects are identical at baseline `6332527`
and source checkpoint `401614a2`; this task does not alter those reports. The
full failure output and scope comparison are retained. The H export itself is
verified separately by its flat evidence index; no global checker pass is claimed.
