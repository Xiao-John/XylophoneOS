# Scoped semantic transport experiment

Base `3377dbf35bdb43d850c9a2b8e8076da3be146f3d`. The image SHA-256 is
`165686bb0de0b0b2f33645ede2cf10c2badb25ea363f3ef57ed74641503b0b08`.
The real one-core/512 MiB QEMU guest ran a deliberately synthetic two-process
request/reply through two existing pipes. xsh with explicitly delegated spawn
authority passed 12 checks; a dash-launched child without its own delegation
returned the expected `-1` denial and status 2. Resource counters were exactly
`[130279, 2, 0]` before and after. `report.json` records the actual QEMU command
and payload/image/dash hashes; compressed serial output preserves the events.

Build with the matching frozen E17 SDK (the SDK's `compile.py` validates its
manifest) and run:

```
python3 ../XylophoneOS-qt6-e17/build/qt_e17/sdk/compile.py tests/fixtures/semantic_pipe_probe.cpp -o build/semantic-pipe/semantic-pipe.elf
QEMU=/path/to/qemu-system-x86_64 python3 tests/semantic_pipe_guest.py --image /path/to/xos.img --payload build/semantic-pipe/semantic-pipe.elf --dash /path/to/dash.runtime --output build/semantic-pipe/guest
```

This establishes only a session-parent-created, prewired child channel and
bounded queue behavior. It is not a real SSG provider, a broker, authenticated
dynamic service discovery, a user permission system, or a session-wide action
transport. The serial output is test evidence, never the production channel.
