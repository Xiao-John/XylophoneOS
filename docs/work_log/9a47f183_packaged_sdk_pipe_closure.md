# Packaged SDK archive pipe closure

The P0 closure campaign rechecked ordinary pipe inheritance through the
newly packaged glibc C/C++ SDK, using the production archive rather than a
diagnostic loader override. No production source changed in this module.

The actual Preview 2 build and guest commands, independent SDK anchors and
source/artifact identities are in
[the report](../reports/p0_sdk_pipe_closure_20261128/README.md). Four scenarios
and four real child executions passed on system `ec96cc19110d9906`, with exact
129793/2/0 resource restoration and 2035 input bindings rechecked. There were
no failed commands in this run. The SDK producer remains build-only; execution
is represented by the separate fresh guest result.

This closes the packaged SDK pipe archive gate for the identified kit. R1's
complete distribution/source/relink/rollback gates and R2/R3's generation and
public GNU matrices are separately owned and are not inferred from this test.
Independent pipe-object transfer, extra routes and terminal-actor dynamic exec
remain outside this profile.
