# Static glibc ncursesw serial replay with terminal select

Source `2a31b409145ff28fd9fff6fcfd01e1aab8889cc7`.
This local composition includes the W1 glibc probe, the native glibc terminal
select implementation, and the strict UTF-8 codec. This build predates
renumbering the UTF-8 patch to slot 0025. The patch payload is identical
and the low-level lock patch is outside this composition.

The signed glibc 2.44 C SDK and ordinary XOS system were freshly built
from the composition. The Linux arm64 compiler host was
`sha256:a71fb65026ab764d7883067a05a6a63a3fc5c3b8abaf6226e5cd0997831cdcc2`.
GCC was 16.2.0 and the ordinary system used the pinned lwIP source.
The ncursesw 6.5 probe detected `select` and reported `poll` unsupported.
Native tic built from the same pinned ncurses archive generated the
xterm database. The guest replay used QEMU 11.1.3, one CPU, the normal Xsh
`tty-run` entry and its matching native terminal service. The disposable
disk supplied the explicit C.utf8 category from verified glibc source.

The SDK, archive, consumers, terminfo and guest steps follow the commands
in the W1 glibc probe record, with this composition as the source for
the system and SDK. The guest gate passed all three selected fixtures.

| Fixture | Guest observations |
| --- | --- |
| Locale | CJK conversion, split input, width, combining characters, invalid UTF-8 and the upper Unicode bound |
| Reentry | Unknown terminal handling, 24×80 dimensions, window bounds, terminal shutdown and reentry |
| Wide screen | ANSI red and CJK plus combining characters in serial output, local window refresh, timeout return, Left and F1, split CJK input, invalid input and recovery, and combining-key input |

All fixtures exited 0 and returned to resource counts `[129514, 4, 2]`
with the terminal service active. This evidence covers the single-thread
serial profile and its three fixtures. Other terminals, resize, signals,
and multithreaded tests remain separate gates.

| Artifact | SHA-256 |
| --- | --- |
| System manifest for `27b469b7e3c35968` | `0fb5dc704f0948421be6e45ef71594175467474fbf7f13cc43be8d4d9c072fe6` |
| ISO | `ad502c5b9ba83bc1e96f33fdd56da82672c7e25feb344449b7c907d3cc8514e0` |
| SDK manifest | `4242fb246959eb95cc231b9cea45b02e190e45db02ef0ad69eb8d59db28e1f58` |
| Signed source verification receipt | `6d3b0458816667ca11a352f63b8b5f0553301cb9394060835a16124311c206a2` |
| SDK archive | `2fd5a13b62e136c865a0bcd70fe30f6960dcb896fcee184279b9a06ad5008539` |
| Candidate profile | `a4bf5a294f7f96238139c793982e090f90a761b393fcee13f8d2d0c29b3e6868` |
| Target libncursesw.a | `240307e2c0278a1ece93a2a3aa7b72b3db9c4bbe1ac6ee153e8da851764e4fc3` |
| Consumer link receipt | `e584a8b3e17b65da6f00cabab21571c80878a6bee406a75216d47ee4aaea14f9` |
| Terminfo receipt | `a3614370de60a1475aa899c4942df480bd0a186b205732ad146312688d18754d` |
| C.utf8 LC_CTYPE | `40680545df4f92443c15e7c6f51a7fdc9154ebedd9eff1ed5c48437039add365` |
| Guest report | `77c80c7a2d6f7ef791899de8b06820bf1a3576e787f604f3e8a91818b2a7d604` |
| Guest serial | `eb5d4bc39fbad716aeac8e62456d13f3e8a355e6bc995b7432172042cb770c2b` |
