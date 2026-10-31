# Upstream synchronization of Browser fragment observation

The branch merged the synchronized SSG consumer branch `59b14da7f2b466a663fdabe86f7467f799c2fd40`, which includes upstream main `8ec04891f18d2c7bfa8629f25e2d1fd39233712f`. This retains the Browser fragment implementation and the upstream snake_case API.

The rebuilt Browser passed 7 scoped QEMU checks. A separately rebuilt geometry fixture passed 6 checks. The first geometry guest invocation failed before guest startup because the Core-only build receipt lacked the `inputs` field expected by the runner; the unchanged fixture passed after using the Widgets builder, and the failed local log is retained. Guest image SHA-256: `972f3a67012576022b67525da90c654a23b273b82cc0f1619fb6c529805ccd41`; Browser ELF SHA-256: `ffb763a9c69cfb9c2f65205a4c630b7d05ac8466ace4dd1cafba7655014e1865`.

Six historical report/log files exposed host-specific paths. Sanitized versions and a raw/exported hash receipt are included; originals remain local. Older Git commits may still contain original paths, so this does not claim historical erasure. The current proposed diff passed the path/identity scanner. This does not establish a production Broker, desktop-wide visibility, physical-hardware behavior or distribution qualification.
