# Static C++ SDK recovery qualification — 2026-11-28

This report qualifies the newly restored `scripts/build_glibc_static_cxx.py`,
using Preview 2 Linux SDK SHA-256
`60df6913fe2a56517e645c93673ebd9590ba3dd90acc56030c80c3738955cac9`.
The SDK was built again from authenticated GCC 16.2.0 sources and the separate
fresh glibc 2.44 C SDK. No lost or historical C++ kit was reused.

## Observed results

- All 14 build steps completed successfully. The builder rechecked the unchanged
  C SDK, its own 15 recipe inputs, tool hashes, C++ ABI macros, POSIX gthreads,
  and the exact five-member native unwinder replacement without changing other
  libgcc members.
- An independent receiver mounted only the exported application kit and consumer
  sources, with no repository. C and C++ `xos-app build/check/pack` all passed.
- In another receiver invocation, all 15 packaged recipe inputs matched their
  original bytes and the builder's CLI loaded without repository imports. A second
  complete GCC rebuild inside that receiver was not run.
- Eleven real-system runs passed: FAT setup, stock xypm, then three repetitions
  each of C++ through Xsh, C cwd/access through Xsh, and the combined dash script.
  C++ exercises global constructors, threads, TLS, exception unwinding, stack
  bounds, and TLS destruction. All runs exited zero and restored exactly
  `free=129796, tasks=2, completions=0`; all installed executables passed FAT readback.
- System build: `5808397c580ec49c`. C++ SDK tree:
  `32b7bec6fc9e85ce2997cd3659fac0c2ecbf05ba7a84a099d9efbb637f760548`.
  GNU signature pins and all input/output identities are retained in the reports.

The builder's `guest_qualification=not_run` field describes its build-time action;
`guest_report.json` separately records the subsequent real-system qualification.
The system and FAT setup helper in this focused test use the existing newlib
system profile. This evidence does not claim the final default-glibc release,
installer, release relinks or frozen-newlib rollback are complete.

## Replay

Run from the repository root using a verified Preview 2 environment. Use new
output directories. The C SDK must first be built from its authenticated source.

```sh
python3 scripts/build_glibc_static_cxx.py --archive "$GCC_ARCHIVE" --signature "$GCC_SIGNATURE" --keyring "$GCC_KEYRING" --sdk-build "$C_SDK" --output "$CXX_SDK" --jobs 2
python3 tests/glibc_unified_sdk_guest.py --system "$SYSTEM" --kit "$APP_KIT" --consumer "$CONSUMER" --dash-receipt "$DASH_RECEIPT" --xypm-receipt "$XYPM_RECEIPT" --output build/cxx_guest
```

The existing detached-consumer recipe is
`docs/reports/glibc_unified_sdk_20261127/build_detached_consumer.sh`; this run mapped
its kit and application roots to the isolated receiver mount. Build the system,
dash and xypm against the exported kit before invoking the guest runner.

Portable `${XOS_*}` values denote this checkout, the separate C SDK checkout,
workspace, SDK build directory, detached kit/consumer/receiver, and the Preview 2
compiler prefix/Cellar. They are replay parameters, not literal executable paths.
`conversion.json` records original build input hashes and transformations;
`manifest.json` alone binds all published report leaves. Original input hashes
are not redefined as hashes of the portable exports.
