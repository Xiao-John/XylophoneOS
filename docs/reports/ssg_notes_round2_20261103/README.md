# Notes Range on current main

Real QEMU with main `48882c9` and current #47: ordinary long-Unicode Range
and cleanup 2/2, Qt Range boundaries 13/13, and the ordinary no-log control
passed. An independent verifier passed all five instrumented live cases:
edit, no edit, authority revocation, protected document and protected ancestor.
Those cases use synthetic Notes and consumer fixtures; ordinary binaries
remain separate. The [result](round2_guest.json) binds each case to its tested
image and payloads. The serial records are kept alongside it.

The complete cross-process suite was last rerun on #46's separate build;
this run qualifies only the Notes cases listed above. Previous reports and
their lineage are retained.
