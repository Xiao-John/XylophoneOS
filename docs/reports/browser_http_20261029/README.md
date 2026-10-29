# URL/HTTP parser preparation — scoped evidence

2026-10-29. **Parser PASSED; networking NOT_RUN.** This report is separate from
liteHTML rendering and from N1 Ethernet device qualification. It proves no TCP,
DNS, user-mode network service, browser HTTP loading or HTTPS capability.

The same pure C++ source passed198 assertions,4096 deterministic malformed buffers,
and every single-byte value mutation of a complete response on the host under
AddressSanitizer/UndefinedBehaviorSanitizer. Target GCC independently compiled it
with `-Werror -Wconversion -Wshadow`; static stack frames are saved in
`target_parser.su` (largest single frame4832 bytes).

Three actual XOS processes then ran the vectors and exited0; free pages/tasks/
completions returned exactly to baseline each time. `guest-report.json` records
the ELF, source, SDK manifest and actual system image hashes and QEMU invocation.
The initial final-parser run uses the frozen GPU qualification system from
`XylophoneOS-virtio-gpu2d/build/virtio_gpu/latest_system/xos.img`, not a claimed
rebuild of the browser branch. The application ran with default `-nic none`.
Raw serial is `guest-serial.log.gz`. Larger ELF/object files remain private.

The first direct stack-measurement compilation selected macOS's assembler because
the compiler needs explicitly isolated target as/ld paths. This tooling failure
did not occur in the SDK-driven successful guest build. Reusing the SDK's target
tool isolation fixed it; target command/result is in `target-build.json`. Earlier
parser iterations and guest logs remain in the private build directories, not
silently rebound to this final source. No fake POSIX functions or error suppression.

Reproduction from this worktree:

```sh
python3 tests/browser_http_test.py
python3 tests/browser_http_guest.py --sdk /absolute/verified/sdk \
  --image /absolute/xos.img --output build/NEW_parser_run
```

Set PATH to the pinned target toolchain and QEMU to the working private11.1.2
binary as recorded in the receipt. Parser API/subset and remaining transport
requirements: [component README](../../../src/ports/browser_http/README.md).
Actual network reception, redirect requests, resource fetching, all transport
timeouts/disconnects and HTTPS remainNOT_RUN; the browser UI must retain that
boundary until network service qualification.
