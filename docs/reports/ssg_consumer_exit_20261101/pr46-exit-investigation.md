# P1 consumer exit investigation

The prior integrated build emitted a denied Browser response but did not report
the consumer exit. The original serial output is retained in
`pr46-original-exit-failure.serial.log.gz`.

An isolated diagnostic build added the logging in `pr46-exit-diagnostic.patch`
to the original QThread watchdog. Three Browser-only repetitions passed; the
fourth reproduced the timeout. Its serial output, retained in
`pr46-instrumented-exit-failure.serial.log.gz`, shows that the watchdog worker
returned and QThread's wait returned, but the consumer was not reclaimed. This
locates the failure after that wait; it does not establish the exact cause.

This branch now uses the existing native-join watchdog implementation from
commit `c9ff0bce050a6777b5f1777c714f9443a23e3ee4`, already present in later
SSG branches. The four P1 programs were rebuilt and the complete targeted
single-guest run passed 17/17 checks with resource restoration, including the
previously failing denied Browser scenario. Its serial output is retained in
`pr46-native-watchdog-full.serial.log.gz`. A passing rerun and the native join
do not by themselves prove the root cause or exclude rare future failures.
The separate later Notes shutdown failures also remain unresolved.

In an additional single-guest stress run, 10/10 denied Browser requests were
followed by normal consumer and provider exits and resource restoration. Its
serial output is `pr46-native-watchdog-stress.serial.log.gz`; the repeatable
runner is `tests/ssg_consumer_exit_stress.py`. This is scoped evidence, not a
claim about other workloads or physical hardware.

On the later snake_case source, a separately rebuilt consumer completed 5/5 denied-exit repetitions with resource restoration. The serial and runner outputs are retained. Overall review status remains PARTIAL; this control does not establish the original root cause.
