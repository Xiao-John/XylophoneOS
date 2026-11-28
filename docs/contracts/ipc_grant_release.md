# Holder-local bulk grant release

`sys88` action 24, `grant_release`, releases the calling holder's reference and
all of that holder's mappings of one bulk grant. It uses the existing 40-byte
`ipc_v1_object_close` input: version 1, size 40, zero header reserved, a nonzero
owned handle and two zero reserved words. The syscall flags argument is zero.
There is no output. The SDK exposes `ipc_v1::grant_release(handle)`.

This is distinct from existing action 23, `grant_close`. Action 23 still requires
manage rights and revokes the whole object, including other holders' mappings.
Release requires only possession of the caller's handle. It never upgrades
rights or revokes another holder. A receiver with only read-mapping rights can
release its reference without obtaining authority to revoke the producer.

The feature-query extension is opt-in because older SDKs validate the known
feature mask exactly. `query_features` flags 0 and 1 retain known/supported
mask `0x1f`. New query flag `0x2` enables `grant_release` feature bit 5 (`0x20`),
returning mask `0x3f`; flag `0x3` also requests the existing direct-switch
counter. SDK callers opt in with `query_features(output, counter, true)`.
Old kernels reject the new query flag. A caller must not substitute global
manage-close when local release is unavailable.

## Atomicity and accounting

The kernel validates input shape, version and caller ownership before mutation.
It preflights every mapping belonging to that holder and grant. An active user
pin returns `busy`; insufficient reservation-table capacity for the combined
unmap returns `resources`; a VM continuation on an affected holder returns
`state`. All mappings and the handle remain intact on these failures. Foreign
holders' pins, regions and continuations do not block local release.

After successful preflight, the kernel removes only the caller's mappings and
handle. Other references and their mappings remain usable. The final reference
reclaims the grant object and backing pages. The existing `owner_pid` and
process-tree `budget_mask` remain attached to the original grant throughout
delegation and release; releasing the original owner does not transfer or
multiply budget credits. Exit cleanup and explicit release use the same final
reference rule. A released handle cannot be reused to map, delegate or release.

Malformed input returns existing `invalid_argument`; unsupported versions
return `unsupported`; a missing, stale or foreign handle returns
`invalid_handle`. No new error numbers, handle format or wire layout are added.
The release branch runs under the existing kernel object serialization, and
cannot race another mutation between preflight and commit.

Readiness pages require both bulk grant and local release features before the
service advertises page support. Their writer has read, write and delegate
rights, with no manage right. Either process can retire its own mapping while
the other retains a safe reference. Explicit service stop, client detach,
owner exit and client exit do not asynchronously remove the other reader's
mapping.

Rollback retains the prior kernel and matching SDK. A new service fails closed
for readiness-page capability on a kernel without local release; legacy finite
socket readiness remains available. Qualification reports separately identify
the host preflight checks and actual guest lifetime, quota and ownership cases.
