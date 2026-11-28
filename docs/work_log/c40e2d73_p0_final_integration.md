# P0 final integration

This integration keeps the verified Preview 2 SDK as the development environment.
Its QEMU is 11.1.3 with a Debian packaging suffix. The tool lock now pins that
exact upstream version, and the kernel smoke accepts only that version with an
optional packaging suffix. It does not accept a different upstream version.

The corrupt-stage boot test previously queried CPU registers immediately after
the UART error marker. That marker precedes the final CLI/HLT instructions, so
a valid rejected boot could be observed in that short interval. The test now
requires the complete marker and polls for the real halted state for at most
two seconds. It still rejects a missing halt or any subsequent normal prompt,
and retains the last register observation.

The recovery run retained the original boot-race failure, the unavailable host
compiler-runtime failure, and the ptrace-incompatible LeakSanitizer attempt.
After supplying the authenticated host compiler runtime, the ordinary smoke
passed with ASan/UBSan enabled and LeakSanitizer explicitly not run. These are
baseline observations, not qualification of later production inputs.

The final source, application SDK, installer, package and receiver/relink gates
are being collected separately. Neither this checkpoint nor opening its PR
closes P0-R1/P0-I. Their exact results and remaining scope will be recorded before
the final integration is merged. No release tag or release asset is published
by this campaign.
