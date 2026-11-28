# P1-H/K5 owned pipe status

The sys54 optional query mode, claimed in PR #444 before implementation, now
returns the live direction, byte count and peer-close state of an owned pipe
without consuming data. The kernel rejects foreign/unheld endpoints before
touching output; malformed requests and console routes remain explicit errors.
The SDK exports the versioned snapshot and advertises it in both manifest
builders. Old byte-count waits retain their existing behavior.

The final ordinary SDK archive consumer passed 3 × 9 real guest cases on system
build `11a789e000461e5f`, including a distinct child's ownership denial and exact
resource return. Source, artifacts, exported SDK and fixture are checked before
and after guest execution. An earlier fixture used the wrong native entry symbol
and failed at link time; that failure and source identity remain in the report.
No production pipe implementation changed between that build failure and the
qualified build.

See [the contract](../contracts/pipe_status_v1.md) and
[qualification](../reports/p1_pipe_status_20261128/qualification.json).
Connected-socket readiness, concurrent close/revoke polling and independent pipe
transfer keep their own P1-H/K5 qualification requirements.
