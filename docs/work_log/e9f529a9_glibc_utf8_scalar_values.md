# Unicode scalar values in the XOS glibc UTF-8 codec

The W1 probe found that upstream glibc 2.44 converted
`F4 90 80 80` to U+110000 with errno zero. The terminal service
accepts bytes from the authenticated foreground client. The
[ncursesw plan](../plans/ncursesw.md) assigns the direct C conversions
and character widths to libc. The existing locale consumer expects
the same upper bound as the [UTF-8 definition](https://www.rfc-editor.org/rfc/rfc3629.html).
The fix lives in glibc's built-in UTF-8 codec and applies to locale
conversion and built-in UTF-8 iconv routes. The ncurses source,
terminal service, kernel, SDK default, locale lookup, and data are
outside the change. The newlib baseline is recorded in
[W1 acceptance](0187_w1_final_acceptance.md).

The converter checks lead bytes and first continuation bounds before
marking a prefix incomplete. The same loop handles split and
complete sequences. The reverse path accepts U+10FFFF and rejects
larger and surrogate values through the existing error path.
The converter and built-in transform records cap conversions
at four bytes. The staged upstream locale file still advertises its
original buffer bound via `MB_CUR_MAX`.

## Independent static SDK and guest

Implementation `e9f529a963a8abe9efdafba8428cbcdaa5e5546f`.
Direct regression fixture `c40dd20a3b6ff3fbaef128abe48734bd95ece901`.
The recorded SDK used the patch's original number 0024. The current
path is `0025-strict-utf8-scalar-values.patch` to give the low-level lock
patch its assigned slot. The scalar patch bytes have the same SHA-256
under both names.
The SDK builder verified the source signature and built with GCC
16.2.0 in native Linux arm64 host image
`sha256:a71fb65026ab764d7883067a05a6a63a3fc5c3b8abaf6226e5cd0997831cdcc2`.
The independent SDK still lists `__stub_select`.

```sh
python3 scripts/build_glibc_sdk.py --archive "$GLIBC_ARCHIVE"     --output "$CODEC_SDK" --jobs 2
python3 scripts/create_xypm_profile.py create --runtime-family glibc     --sdk-build "$CODEC_SDK" --id xos-x86_64-glibc-utf8-scalars --output "$PROFILE"
python3 scripts/build_glibc_program.py --sdk "$CODEC_SDK/sysroot" --profile "$PROFILE"     --source tests/fixtures/ncursesw/wide_locale_probe.c --output "$LOCALE_ELF"
python3 scripts/build_glibc_program.py --sdk "$CODEC_SDK/sysroot" --profile "$PROFILE"     --source tests/fixtures/glibc_g2/utf8_scalars.c --output "$SCALAR_ELF"
```

QEMU 11.1.3 booted the inherited, byte-bound ordinary XOS image
`12bc38baa2e6615c`. The disposable FAT disk contained that image's
native terminal service, the two ELF files, and the original
C.utf8 LC_CTYPE category generated from independently verified glibc
2.44 source with native localedef. The Xsh `tty-run` entry ran
both programs, and both exited 0. The W1 locale fixture stayed
unchanged and covered CJK round trip and split input, width and
combining checks, error returns, and a supplementary character.
The direct fixture verified the one-to-four-byte boundaries,
U+10FFFF, invalid and split prefixes, recovery after reinitializing
the caller's conversion state, both conversion directions,
the C locale and the neighboring UCS-4LE iconv route.
Resources returned to `[129527, 4, 2]` with the terminal service active.
The source-bound wide-screen replay requires the separate terminal
readiness change.

| Input or evidence | SHA-256 |
| --- | --- |
| Authenticated upstream glibc archive | `37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667` |
| SDK manifest | `3b2611b45aba251945dcb1089081833879a2b0201b6bcdb99f1de9a5e6cfcc6b` |
| SDK libc.a | `aa292462366a30e6217f4a8a10f2164f51e56d398344167f156d20b8fff99e13` |
| Exported SDK archive | `77cad1fa92bc3b9293ff811f8d8c6b0a49865bf36052285212fa3577308a2546` |
| Candidate profile | `93a3690de7ce884ed3932a9c1280fc0251d944d65793f418d42b7d3097618a4b` |
| C.utf8 LC_CTYPE | `40680545df4f92443c15e7c6f51a7fdc9154ebedd9eff1ed5c48437039add365` |
| Ordinary system manifest | `8bef624e0ba9673195b63de63c4922d4114ee8fb324e41f5ee09e788f046fc0a` |
| Ordinary ISO | `212e6b4034f8e4deced49d13fc9828b3e4eda45842758ba21796ed1032f8447e` |
| W1 locale fixture ELF | `a90a5ecdb8a6696c4731360371ddff5368d5367f768956b6a8a8f2c751723b78` |
| Scalar fixture ELF | `df538d16581251a42f877d4bdc232dea94a091a2d2424dd39aa7ca9c9f1601a4` |
| Guest report | `6eba3685dd855223fe15137412a5746542dc5dd2660447519ce8d12f319ac3b8` |
| Guest serial | `3cf34cabc0ca0f562de531e082ada3d9c87e67fd912af675dba52796fe05ddb7` |
