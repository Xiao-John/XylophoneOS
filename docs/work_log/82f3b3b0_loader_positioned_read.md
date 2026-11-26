# Pinned executable positioned reads

Source commit `82f3b3b0b1ff22448a5e19fe44ded540c6689ab3`, based on
`5d912c708e707baa0d617e59ae25654f260ff76c`.

The loader uses the existing files v2 `read_at` operation on the read-only
handle pinned through ELF inspection and mapping. It tries the historical
seek/read path once per open if the initial well-formed positioned request
receives the legacy empty `invalid` reply or the explicit `not_supported`
reply. New services leave the open-description cursor untouched. The native
client checks the error envelope before accepting either fallback signal.

## Host checks

```sh
c++ -std=c++17 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined \
    -fno-sanitize-recover=all -Isrc/shared/include -idirafter src/user/include \
    tests/loader_file_reader.cpp src/user/loader/load.cpp src/user/loader/elf.cpp \
    src/user/sdk/file_client.cpp src/user/sdk/text.cpp src/user/arch/x86_64/tls.cpp \
    -o build/loader_file_reader
build/loader_file_reader
python3 tests/glibc_files_extra_host.py --sanitize --output build/loader_files_host
```

The public spawn fixture passed with simulated kernel and file transport. It
covered both legacy fallback replies, matched mapped bytes and zero-fill,
verified the pinned handle lifecycle and image receipt SHA-256, and exercised
short reads and the maximum native file size. It also checked EOF, malformed
success/error metadata, and errors after successful positioned I/O. These
failures kept the child from starting and released the pin. The existing
glibc and file-service fixture passed all eight integration groups against
real FatFs and simulated kernel transport under ASan/UBSan.

## Existing Mobius session guest

One A/B case used the signed glibc C/C++ SDK manifest
`7eee04884a96ced6de12d20794af6809f544e3f15bc4e409b4197e58b1583d7a`,
the previously booted system ISO
`64230b48317bb327fcac03651982381b98912da10a3256e98b73d7d3091fa1f5`,
and the unchanged desktop ELF
`9fdacb77d2dc935a83150d68f6275cc355f50cd3c8b693b7eb2e7529a612a413`.
Each run started the instrumented Mobius session from xsh through
`exec-driver` on QEMU 11.1.3 (TCG, 512 MiB, one vCPU). The wrapper counted
operations at the existing glibc session exchange and summed the time those
exchanges spent on the guest monotonic clock. Host wall time ends at desktop
readiness and includes the full session startup after the command.

| Measurement | Previous loader | Positioned loader |
| --- | ---: | ---: |
| File exchanges | 18,077 | 12,051 |
| Seek | 6,026 | 0 |
| Read | 12,047 | 0 |
| Positioned read | 0 | 12,047 |
| Sum of guest exchange times | 184.760 s | 124.370 s |
| Host time to ready | 192.836 s | 131.100 s |

The baseline loader sources and headers match the baseline commit above.
Both runs produced the same two scanout SHA-256 values after genuine display
and input operations.

- Midnight `ae9d9abd47d64a26e27429256222eb86b0d3f923b5cd07226fdc63bb0b8308c6`.
- Daybreak `909414608f0bc155a9ab9f78cb5ee6eb41ecde40135081036d7e834c90c3e052`.

After the desktop closed, guest resource counts returned to the graphics
baseline `[121635, 5, 3]`. After the graphics services stopped, they returned
to the booted baseline `[129711, 3, 1]`.

| Evidence | SHA-256 |
| --- | --- |
| Previous instrumented session | `7782c5eef7e88c39af0f554dacee6f6d539f3e01b4f16ab3bb9282b9dcab0f9e` |
| Positioned instrumented session | `6b9b45c4931e21ff2afaccd0128c6d6409207586717f0e034e62ea9806104628` |
| Previous guest report | `1068f7f3677f8b5661c08fc61066723f421a173987d172f282e4d42d7fbbe65d` |
| Positioned guest report | `9c4d5cf9c6183f409d44a9a6dc9216555f240e8d67460e0c350ef55c7430cedc` |
| Positioned guest serial | `27c81f1ac3efd3df5beccd795971aa91c3d7b88aa9557ffdc6a81dd23f8b993e` |
| Local comparison index | `c0e21a23053b7713b933e31dd28f555f3c8bfa41cd912d393df305cbba783067` |

The timings are individual runs on the inherited image. The previous file
service response was exercised through the host fixture. The guest result
uses a freshly linked loader inside the Mobius session ELF on the existing
system and SDK.
