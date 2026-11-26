# XOS loader reader license registration

The ordinary replay of `d24f9d1c` passed 79 runtime checks and stopped at
the license materials test. The extracted `src/user/loader/image_reader.hpp`
had retained the combined MIT and Apache-2.0 identifier from
`src/user/loader/load.cpp`. The audit had no explicit registration for the
new path.

The registry now lists the reader's exact source path, existing combined
identifier and both notice files. The published fix is
`8a711e4e1ba375db2e92a444f0d5de4a5c144cd7` (Git tree
`46901bd57a9a2425c7336d317be89ab4263eeb0e`).

This tree rebuilt with the locked cross toolchain and lwIP input. Its
SDK received the new registry through the normal build. The fresh image
`44c70a3a2d86ce48` passed 79 runtime checks, 10 license materials checks,
and the ABI table check with QEMU 11.1.2.

| Evidence | SHA-256 |
| --- | --- |
| System manifest | `f69c7233ffc6a67eb81c658119635fc085ca6607063ab3fced04ddf85f764fae` |
| System ISO | `6ddb4198b39dc7c0a04311ab27abb2a34ed162fe882aead0a8a6d01cc991537e` |
| Original replay output | `b715f54091eecbe63f423ea57f4b15232e2d71bafc6cb4f50b4db8f3d86069f0` |
| Materials report | `6a4340184308461f2d86de8739106afb96eec8ffc49d170f27b14c2202174dfa` |
| ABI results | `e2e4c52a0306922418b0917ef17cc47d9eba2bec406bbb9f4f1387b8c86eb301` |
