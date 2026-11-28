# Current P0-R2 generation qualification

Rebuilt the public GNU startup runtime with the verified Preview 2 tools and
independently anchored C SDK, then built the real C application, an explicit
three-root controller and the native generation probe. No production source
change was required.

The new system `ec96cc19110d9906` passed three complete rounds: 21
generation checks and 12 actual GNU launches, each round restoring 129793/2/0.
The exact source revision, SDK anchors, artifact identities, commands, results
and retained boundaries are recorded in the
[report](../reports/p0_generation_closure_20261128/README.md). All 392 unique
producer/runner sources were checked against Git before export; GNU artifacts
and input receipts were also rechecked. Build-only receipts retain their
original status. No failing command occurred in this module's fresh run.

The independent host closure suite passed 46 ordinary/sanitized cases. Its
original source identity is retained and its source equality to the final
producer is explicit. Its modeled Files outcomes are not guest fault injection.

This closes the current volatile-controller R2 gate. Public C++/thread/shell
entry, the complete R1 distribution and network combinations have separate
reports. Durable policy and descendant-wide revocation remain P1.
