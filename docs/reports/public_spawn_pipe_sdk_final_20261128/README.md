# Final SDK archive: public spawn pipe qualification

The actual C SDK support archive passed **4 groups / 4 real child executions**
in one complete guest round. The selected mode was `--sdk-loader`: there was
**no loader object override** in the link. The builder verified that both the
SDK input record and the loader source shipped in the SDK matched the selected
source, then used the archive already covered by the independent full-SDK
anchors. The ELF, object, source, full copied SDK and tool identities were
rechecked before and after execution, and all 1154 input hashes were rechecked
again for this export.

| Real public API case | Result |
|---|---|
| Pipe input/output, stdio and extra-FD aliases, shared status flags and CLOEXEC | Passed |
| Nested `posix_spawn` reads an extra alias after POSIX fd0 closes | Passed; shared stream consumed DA then TA and EOF |
| Parent observes last-close EOF while the child is still alive | Passed before the release gate allows child exit |
| Extra kernel write alias survives parent stdout closing before spawn | Passed; the child keeps fd1 closed |
| Unrouted pipe rejection | ENOTSUP; parent endpoints remain usable |
| Reader closes before child writes | Child receives EPIPE |
| Resource recovery | Exact 129778 pages / 2 processes / 0 completions |

## Exact final inputs

- Source: `08c97e1c9a9f3ee4a03cae24ad02214809786782`.
- Native build: `eeb192efd1422062`.
- C SDK manifest: `737c00f7a6ca7e16d93fc2b0e3057ac1bb6fdfef46f8273a225cdfcd435cefc1`.
- Complete C SDK sysroot tree: `27d2c45b8f6c64fc1a0a7cd54e858577cab7f1a595b62dbfd9f63c866f616466`.
- Delivered loader source: `7b9bc97c98fd7cdf66fd94d24f5c01137327efa70d3549270d03ca8f43644888`.
- Actual fixture ELF: `22828dae798a3e6a3997c1b993fe296008e88bcba52a594e8b1bafaa4e1ed6fa`.

The old SDK was also presented with its correct independent SDK anchors to the
new archive-only mode. It was rejected because its loader source did not match;
no ELF was created. `stale_sdk_rejection.json` records that separate negative.

`build.json` preserves `built_not_run`; `guest.json` records actual execution.
`${XOS_SOURCE_08}` identifies the full frozen source and its native build;
`${XOS_CSDK_BUILD}` identifies the independently anchored C SDK. Preview2
variables identify the selected tools and temporary/workspace roots.
`conversion.json` preserves the raw receipt/report and local serial-log hashes.
Only the summarized observations and raw-log identities are published here.

The earlier finite object-override diagnostic remains a separate report. Its
passing result is not transferred to this SDK archive. Shared GNU dynamic
entry, including a further real pipe scenario, is qualified separately against
its own newly built interpreter, libc, application and approved-root bytes.
