# GCC 16.2.0 port (E08-4/5)

Private build inputs for the XOS-hosted GCC Seed. The builder is
`scripts/build_gcc.py`; it writes only under `.cache/xos_seed/gcc/` and requires an
immutable SDK manifest hash. This is a preparation artifact until a real C Seed
manifest and guest C gate exist.

Build/host/target are recorded from `config.guess` and the GCC source lock; the
host alias `x86_64-unknown-elf` is not a Linux ABI claim. The first target is
C-only; C++/libstdc++ belongs to E08-5 and is not implied by a C build.

Current status: a C Seed is built and installed in the private cache; its manifest
is copied to `src/ports/gcc/seed_manifest.json`. The host C++ closure uses real
GCC 16.2.0 libstdc++ objects and headers; target C++/exceptions/RTTI/TLS remain
E08-5 work. The primary accepted a derived C Seed after real guest fixes; the original installed
binaries remain historical inputs. The direct-ld profile does not validate collect2. See
`docs/e08.md`.
