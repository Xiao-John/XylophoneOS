# P2 diagnostic on current main

Real QEMU Browser contract run: **PASSED** (7 checks).
Both the Browser and system image were rebuilt with main `48882c9` and
the current P1 layer. [Results and diagnostic observations](round2_guest.json)
and [serial](round2_guest.serial.log.gz) bind this run to its ELF and image.

The [original large-page diagnostic](../ssg_p2_diagnostic_20261030/README.md)
remains incomplete. A passing contract check permits a capped observation
only when diff requests a reset; this does not qualify complete large-page
semantics, pagination, or the complete cross-process suite on this build.
