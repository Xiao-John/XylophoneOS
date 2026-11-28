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

## Rebuilt public entry and the capsule conflict

Fresh public GNU `make lib`, shared GCC libraries and ordinary native SDK
controllers were subsequently built from recorded inputs. The exact native
system `e8b8ba5e2645c5c2` passed C startup, explicit runtime loading denial,
FD-preserving `posix_spawn`, failed-exec cancellation and real same-PID exec,
plus cross-DSO C++ exceptions/RTTI/unwinding through xsh and dash. All six
completed commands restored the initial resource baseline. These observations
qualify only their exact rebuilt bytes.

The next real `std::thread` case failed with `ENOTSUP`; the final dash thread
case did not run. The capsule occupied `0x70000000`, the first address of the
kernel worker stack/TLS reservation, so the kernel correctly rejected thread
profile opt-in. The [failed report](../reports/public_runtime_capsule_overlap_20261128/README.md)
preserves all 3,376 bound inputs, original outcomes and serial output.

The correction moves the internal version-2 capsule to `0x71000000`, checks
all reserved regions at compile time, and rejects dynamic bootstrap LOADs
that overlap the capsule or worker arena. Native identity generation now
also binds the actual dynamic ABI headers. Two genuine target-ELF negatives
relocate valid readonly-note bootstrap images into those areas: the ordinary
static inspector still accepts their legacy layouts, while the dynamic
approved closure rejects them after digest validation. A fresh native SDK,
C SDK and public GNU/C++ composition is required before the worker correction
can receive its own execution qualification. The preserved failed attempt is
not P0 completion evidence.
