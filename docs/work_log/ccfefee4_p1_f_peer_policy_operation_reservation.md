# ccfefee4 P1 F peer policy operation reservation

The P1-F renderer lifecycle needs to reclaim a bounded Net2 denial record only
after the controller has confirmed process retirement. During parallel work,
PR #444 claimed operations 19/20 and optional revision-2 capability flags for
P1-H. This document-only reservation assigns operation 21 to P1-F instead.
It preserves the already merged H/K1 claims and all existing capabilities.

The explicit request and response each occupy 16 bytes and carry their own
revision 1 and size. Only the kernel-authenticated bootstrap controller may
query or release. Successful wait/reap, or positive never-started plus abort-zero
loader evidence, is required at the trusted caller. Unknown outcomes cannot be
converted into confirmed retirement. Old services fail the optional discovery
query honestly; no renderer is silently granted raw network authority.

The base is `69ad06c15cfb435d4742e10fb888d9b34173d796`. Changed files are the ABI
registry, Net2 contract and this work log. No source constant, capability claim,
syscall allocation, runtime behavior or qualification report is added.

Actual validation: `python3 tests/abi_doc_consistency.py` passed; the staged
public-evidence path and whitespace gates passed. Real controller, Net2 service,
renderer, loader-abort and repeated-navigation tests remain in the implementation
PR. This allocation is coordination, not completion of P1-F.
