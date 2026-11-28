# Public runtime recovery checkpoint

This source checkpoint reconstructs the public native dynamic loader after the
previous execution filesystem disappeared. It depends on the recovered launch
controller and pinned closure/catalog checkpoints. No old runtime, C++, shell,
or generation test result qualifies these new bytes.

The reconstructed code connects ordinary SDK file inspection/spawn through weak
optional hooks, carries a read-only approved-generation capsule into a native
bootstrap, maps the exact transferred open descriptions, enters the GNU rtld
stack, and authenticates READY after constructors. The shared libc adopts the
native Files session and approved roots; real exec preserves the process identity
and explicit control/terminal channels. The new libc exec adapter snapshots the
v3 FD representation and retains the original image until kernel commit.

ELF preflight covers native identity, bounded LOADs, dynamic tags, exact SONAME and
DT_NEEDED edges, symbol/version tables, supported relocation destinations, TLS,
RELRO, and non-executable stack policy. GNU OSABI 3 is accepted only with the exact
native read-only XOS identity, for GNU IFUNC/unique-symbol objects. The early rtld
heap has a fixed 8 MiB bound at 0x1fff00000000, separate from object mapping budgets.

Validation at this checkpoint: strict freestanding host C++ compilation of ELF
preflight, static loader adapter, native bootstrap, and dynamic spawn succeeded;
the new GNU dl-init patch applied in a dry run to the authenticated glibc 2.44
source. Full SDK target build, public GNU `make lib`, actual C/C++ execution,
same-PID exec, FD behavior, shell entry, adversarial ELF cases and resource
qualification are still pending. This is a recoverable source checkpoint, not a
completed P0 gate or a public release approval.
