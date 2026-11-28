# Current P0-R3 public runtime qualification

Rebuilt public GNU libc/rtld, shared GCC, the C/C++/thread/pipe generations and
the four-root launcher using the verified Preview 2 environment. The native
system is `ec96cc19110d9906`; the outer static dash came from the current
packaged SDK candidate and remained unchanged during execution.

All nine ordinary public-runtime cases passed in one full round. Each returned
the exact 129693/3/1 resource baseline. The runner rechecked all 3352 inputs
after execution; the exporter checked them again. No production correction
was required and no command failed in this runtime build/run chain.

The [report](../reports/p0_public_runtime_closure_20261128/README.md) contains
actual per-case results, source/artifact/SDK identities, public source mapping,
replay commands and explicit retained limits. 399 source files were
independently checked against the public producer revision. Raw receipts keep
their original identities and build-only status; the new guest result is
separate. No historical acceptance result was moved to these bytes.

This closes R3's bounded public startup, ordinary spawn/same-PID exec, pipe,
C++ and thread entry gate. The R2 volatile generation and R1 packaged pipe
reports are separate; full R1 distribution and network combinations remain
owned by their integration modules. Persistent/global authorization, online
library loading and the other documented P1 compositions are not claimed.
