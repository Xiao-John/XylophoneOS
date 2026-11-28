# Owned pipe status v1

`sdk::query_pipe_status(token, output)` obtains one non-consuming observation of
an already owned pipe endpoint. It supplies the native mechanism needed by the
separate P1-H descriptor polling and P1-K5 transfer work. It does not delegate an
endpoint or establish either module's complete qualification.

## ABI and ownership

The optional sys54 `sys_pipe_wait` mode uses arg2 `1ull << 63`; arg1 is either a
private pipe token held by the calling PID or its existing pipe stdio route.
Arg3 points to a readable and writable 32-byte `pipe_status_snapshot`:

| Field | Type | Request / successful response |
| --- | --- | --- |
| version, size | two u32 | 1, 32 |
| readable, writable | two u32 | Request zero; response current bytes in this endpoint's direction |
| flags | u32 | Request zero; read_end=1, write_end=2, peer_closed=4 |
| reserved, reserved2 | u32, u64 | Always zero |

Only one direction flag is set. A read endpoint reports buffered readable bytes
and zero writable bytes; a write endpoint reports the remaining 4096-byte
capacity and zero readable bytes. `peer_closed` means no opposite endpoint
references remain. Thus buffered data and EOF may coexist, and a write endpoint
may have free capacity while its next write returns EPIPE. Poll adapters must
use the flag, not infer peer liveness from the byte count.

The kernel authenticates ownership before inspecting the output pointer. A
foreign, unheld or closed token returns `process_error_denied`. Console routes,
bad output memory, an unsupported version/size and nonzero request fields return
`process_error_invalid`. A failed query does not overwrite the supplied snapshot.
The SDK wrapper uses a local request and copies it into the caller's output only
on success. A copied token value in a child is not authority.

The kernel prepares writable/COW pages and validates the complete request before
reading the live pipe in its non-preemptible syscall section. Query does not
consume bytes, block, change a route, or retain an object. This is a current
observation, not a reservation: a later read/write validates its own state.

## Compatibility and evidence

The existing arg2 byte-count modes 0–4096 retain their wait/deadline semantics.
An old kernel rejects the new mode; callers cannot treat that error as an empty
pipe. Both ordinary and threading SDK manifests record the query's mode, version,
size and ownership scope alongside the exported header and archive provenance.

[The qualified guest report](../reports/p1_pipe_status_20261128/report.json)
records three rounds of nine cases: empty direction, non-consumption, capacity,
bad output/console, reserved fields, a real foreign child, EOF, closed-token
output preservation and a broken writer. Free pages, tasks and completions
return to the same baseline after each round. The runner checks the entire
system source/artifact inventory, fixture sources, ELF and exported SDK tree
before and after the guest. The initial fixture link failure is retained in
[qualification](../reports/p1_pipe_status_20261128/qualification.json), with its
original source identity; it is not represented as a passed guest run.

Reproduce with the documented host SDK, from this source revision:

```sh
python3 scripts/build.py --output-dir build/pipe_system --quiet-demos-on-launch
python3 scripts/build_pipe_status_probe.py --sdk build/pipe_system/sdk --output build/pipe_probe
python3 tests/pipe_status_guest.py --system build/pipe_system --fixture build/pipe_probe --output build/pipe_guest
```

The probe uses the exported native SDK archives and `xos_user_main` entry. It
runs through `exec-driver` so its ownership test can create a real child.
