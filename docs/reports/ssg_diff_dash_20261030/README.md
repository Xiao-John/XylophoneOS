# SSG Diff fixture under xsh and dash

The same final XOS Qt fixture ran under xsh and under the actual dash executable
on the frozen one-core/512 MiB guest image. Each shell passed the same 12 checks,
both programs exited normally and resources returned exactly to baseline. The
dash path is `exec-driver /bin/dash /ssg-diff-dash.sh`; the dash executable SHA,
payload/image SHA, actual QEMU command, checks and resource counters are in
`report.json`. Compressed serial logs preserve the raw output. This is a test
fixture, not a separately authorized production semantic service.
