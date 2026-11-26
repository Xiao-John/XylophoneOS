# Static glibc ncursesw serial probe

Source commit `0d88a7fc086cfab276d223f78f48a5f165e535ad` from
`d056849620bdb93ba447acbb2fcc805e7ea8df23`. The opt-in probe builds the
pinned ncursesw 6.5 archive against a verified glibc C SDK and links the
five existing terminal consumers. The earlier
[newlib acceptance](0187_w1_final_acceptance.md) remains the newlib baseline.

```sh
python3 scripts/probe_ncursesw.py --archive "$NCURSES_ARCHIVE" \
    --sdk "$GLIBC_SDK/sysroot" --glibc-profile "$GLIBC_PROFILE" \
    --build --no-sigwinch --xopen-source 700 --output "$PROBE"
python3 scripts/probe_ncursesw_consumers.py --probe "$PROBE" \
    --sdk "$GLIBC_SDK/sysroot" --glibc-profile "$GLIBC_PROFILE" --output "$CONSUMERS"
python3 scripts/build_ncursesw_terminfo.py --archive "$NCURSES_ARCHIVE" \
    --target-probe "$PROBE" --output "$TERMINFO" --jobs 2
python3 tests/ncurses_glibc_w1_guest.py --system "$SYSTEM" \
    --sdk-build "$GLIBC_SDK" --profile "$GLIBC_PROFILE" --probe "$PROBE" \
    --consumers "$CONSUMERS" --terminfo "$TERMINFO" --ctype "$LC_CTYPE_FILE" \
    --output "$GUEST_RESULT"
```

The configured target archive has 162 members and defines both `initscr`
and `wget_wch`. Host tic from the same pinned source generated the xterm
database. The five consumers also cross-linked against the previous
UTF-8 newlib SDK and archive after the fixture marker adjustment.

The glibc terminal runtime already contributes the read-only `.xos.tty`
marker. A second marker from the fixture created a 32-byte section and
caused the loader's executable validation to reject it with `-18`.
Each fixture now emits its explicit marker for the newlib build, while the
glibc-linked executable uses the runtime marker. The fixture operations
remain the same.

| Build input or artifact | SHA-256 |
| --- | --- |
| ncurses 6.5 source archive | `136d91bc269a9a5785e5f9e980bc76ab57428f604ce3e5a5a90cebc767971cc6` |
| D1 glibc C SDK manifest | `bf9e841c1bf27f2330ef2e91a49518ca92fbdfe48d1b7c79a566a49ab9b9caed` |
| D1 C candidate profile | `ed43f77698a47fbf9c6bd74f90df5c1b27b062d4bbb0a35909fb4c4645958d0e` |
| Target `libncursesw.a` | `51e2729be2dd7cb16f1977f054a25f56c4d5b70c4b0da2866290ea43ee25167c` |
| Target build report | `0e5bcb1ba773c0abf8ff3435be29a24d9bc8a413284716ac1aea59a5d02828b9` |
| xterm database entry | `588f74f5a9a0500697a23f8074e22ab683346bd2f62db17324ffc77f223fe1f9` |
| Generated C.utf8 LC_CTYPE | `40680545df4f92443c15e7c6f51a7fdc9154ebedd9eff1ed5c48437039add365` |

The explicit locale input was generated from the independently verified
glibc 2.44 source archive using little-endian, category-directory output
from native localedef 2.43. The same bytes were present in the Linux build
host's installed C.utf8 category. On the target, a direct diagnostic opened
and read that regular file. Read-only file-backed mmap returned ENOTSUP,
and the stock libc successfully loaded the category through setlocale.
The application probe supplies this one data file on its disposable disk.

## Guest and prerequisites

QEMU 11.1.2 ran the ordinary xsh image `12bc38baa2e6615c` and its matching
native terminal service. With an empty locale directory, all three
consumers reached `tty-run` and exited at their first locale check with
status 1. The explicit category file allowed all three probes to advance.

| Probe | Result |
| --- | --- |
| Reentry | Exit 0. Verified unknown terminal rejection, 24×80 geometry, local bounds, endwin and refresh. |
| Wide screen | Rendered CJK and its combining mark, a red cell, and the local-window marker. Reached the first key checkpoint after the initial timeout result. Left-arrow decode exited 6. |
| Locale | Reached and failed the upper Unicode scalar bound test at code 13. The earlier CJK roundtrip, split input, width/combining examples, and invalid-byte and surrogate checks passed. |

Each run returned to the same active terminal resource counts
`[129527, 4, 2]` after its fixtures. The verified status with the locale
file is `passed_subset`.

A separate diagnostic, using the same glibc SDK and tty-run, established
the missing terminal dependency. `select` on the actual terminal input fd
with a 20 ms timeout and `poll` on the same fd both returned ENOSYS. A raw
blocking read then received the delayed byte `z` and exited 0. The next
gate is genuine read readiness on the authenticated terminal descriptor
with bounded and infinite deadlines. The existing newlib path calls
`terminal::wait_readable`; the glibc SDK needs its own supported bridge.
This is enough to rebuild ncurses and exercise the timed escape sequence
path without changing its source. That diagnostic also measured stock
`mbrtowc` consuming all four bytes of `F4 90 80 80`, producing U+110000
with errno zero. The locale scalar requirement needs its own decision.

| Replay artifact | SHA-256 |
| --- | --- |
| Ordinary system manifest | `8bef624e0ba9673195b63de63c4922d4114ee8fb324e41f5ee09e788f046fc0a` |
| Ordinary ISO | `212e6b4034f8e4deced49d13fc9828b3e4eda45842758ba21796ed1032f8447e` |
| All five consumer ELFs receipt | `bbb9deadeffd8be781d39efcb71e97ca02be28c81732fedd92a5b44ef0d60f14` |
| Host terminfo receipt | `80519f0f6dab6d6bf924e0ba41a08ac8f7404f820509aa50c77782a93ae41f17` |
| Independent glibc source verification | `3787203ea4dcb06da3fc847de2706ecda5bc13848e22334dab880a7acbcabc67` |
| Guest report with C.utf8 | `6beb95a40ad40395b574fc73dc26c165cce0d3f66f265d457c350bcaeebaa439` |
| Guest serial with C.utf8 | `c69e9a6d76ba16ce5e3063615a58d5f2b0923a7300b9c5d528aae1bf93e0bda9` |
| Guest report without C.utf8 | `ae5fd1cf18644d8ab8fecdfece547ab57fef1f071ac968608f495cdbed684574` |
| Direct TTY and scalar report | `2be1d8f517bd6792f9c485f389d489c6ee6270bd4a95930884b9bcefaed43288` |
| Prior newlib SDK consumer relink report | `caebfbf90c4589063171f9faa9b3d2e69031f69d275bf90b9e49ad5cd9ff5d77` |
