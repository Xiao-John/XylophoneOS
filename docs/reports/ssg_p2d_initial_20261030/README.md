# Browser P2D: preliminary experiment — NOT QUALIFIED

The unchanged #8 frozen browser fixture was loaded by the actual XOS Browser;
a separate XOS Consumer used the prewired pipe. It received five responses,
32 distinct IDs and a final `complete=true`: page node counts were 8, 8, 8,
8, 0; response sizes were 3610, 4094, 3768, 3983, 342 bytes. The consumer
checks identity, revision, page sequence, cursor advancement and duplicates.
This is an initial observation, not proof of a complete semantic baseline:
no independent completeness or parent/text oracle was applied. The 20 ms
readings have coarse guest-clock precision and do not establish GUI latency.
Resource counters before launch and after both child processes exited matched
(the display service remained running). The QEMU command, original serial
log and exact IPC frames are preserved here. Temporary work-disk paths in the
recorded command are no longer live; the probe script reconstructs the disk.

The first Browser build failed due to indexed access to a liteHTML list; its
log is retained. The rebuilt Browser and Consumer cross-compiled successfully.
The unchanged preexisting large-page regression remains failed and intact.

NOT RUN: larger fixture; complete node/parent/text and fragment/hit oracle;
replayed cursor, permission revocation and reload; PS/2 input during paging;
scroll invalidation and full resynchronization; bounded paged baseline and
real subsequent Diff; Notes PR #9 IPC safety cases. Page Diff reports
`RESET_REQUIRED_NO_PAGED_BASELINE`; this is not a successful Diff. The existing
SceneStream remains separate and cannot adopt these pages as a complete tree.
The existing nonpaged API remains unchanged. This prototype is not a production
broker and must not be marked P2D complete.
