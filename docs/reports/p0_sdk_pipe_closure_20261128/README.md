# Packaged SDK pipe qualification

The newly packaged glibc C/C++ kit passed all four real pipe scenarios on
native system `ec96cc19110d9906`. The probe used `--sdk-loader`: it linked the
kit's verified `libxos_terminal.a` and did not substitute a loader object.

One complete round exercised routed reads/writes, descriptor aliases and
shared flags, CLOEXEC exclusion, final-close EOF while the child remained
alive, inheritance after closing the original stdio descriptor, explicit
unrouted-pipe rejection without changing the parent, and EPIPE. The fixture
performed four actual child executions and restored exactly **129793 free
pages / 2 tasks / 0 completions**. All 2035 bound inputs were rechecked after
execution and immediately before this summary was written.

`qualification.json` records the exact source, system, native SDK, packaged
SDK, linked archives and probe identities, actual results and replay commands.
The producer receipt remains `built_not_run`; the distinct guest observation
is `passed`. Digests of the original local receipts identify their origin.
This report was generated from a fresh run; historical reports are unchanged.

The public summary contains the necessary source/artifact identities and
results, without raw host inventories or serial transcripts. Its flat
`manifest.json` binds the two exported leaves. Replay uses caller-selected
`XOS_*` paths inside the verified Preview 2 SDK environment and requires the
listed immutable inputs.

The fixed routing bound remains one input and two output routes. This result
does not qualify arbitrary independent pipe-object transfer, additional routes,
terminal-actor dynamic exec or physical hardware.

## Public source mapping

The recorded local producer `1b8b0ae1cc1fc29bfde69b4f0d69f49a9b8a39d0` and
[public source `0056c9fa`](https://github.com/Xiao-John/XylophoneOS/commit/0056c9fad097dddfeede319ff7c63b3ebd2bfcd5)
have the identical complete Git tree `3c67a6f4ce7ee0061af3ef743c07b9d6757f1fb1`.
This publishes a reproducible source location without changing the original
receipt's source identity. The mapping was checked against GitHub's commit
tree and the local Git object.
