# Static XOS glibc research SDK

This profile builds the complete static `libc.a` and `libm.a`, installs their
public C headers, and adds an XOS CRT and linker script.  The sysroot is private
to this port.  Its headers, libraries and startup objects must be used together;
the newlib SDK remains a separate build profile.

The glibc 2.44 release archive has an authenticated upstream signature. The
reviewed primary key and signing subkey are bound by GNU and Gentoo sources;
current key updates are recorded in `source_lock.json`. `build_glibc_sdk.py`
checks the archive, detached signature and pinned public key with `gpgv` before
extracting source. Expired or revoked keys and unexpected signers fail the build.
It applies every numbered patch in order and records all port inputs and tools.
It rejects source or tool mutation during a build. The XOS runtime remains a
separately qualified research profile.
The installed SDK includes upstream licenses, compiler runtime licenses, the
port sources, build scripts and a patch index.  It records the compiler runtime
objects and copies the compiler's private C headers into the SDK.

## Build and link

Use the toolchain from the `xos-glibc-sdk-preview` release.  GNU make, a native
build compiler, Python 3.12 or newer, gawk, bison, patch and gpgv are required. The
archive path and output paths are explicit; each output directory must be new.

```sh
python3 scripts/verify_glibc_source.py \
  --archive /path/to/glibc-2.44.tar.xz --output build/glibc_source_auth
python3 scripts/build_glibc_sdk.py \
  --archive /path/to/glibc-2.44.tar.xz --output build/glibc_static --jobs 8
python3 scripts/build_glibc_program.py \
  --sdk build/glibc_static/sysroot \
  --source tests/fixtures/glibc_g2/static_main.c \
  --output build/glibc_static/static_main.elf
```

The SDK build selects `make lib`, `install-headers` and `install-lib`; it installs
the just-built `libc.a` separately because upstream attaches that archive to the
full `install` target.  The public `gnu/stubs.h` comes from the real stub sections
of the installed archives, using the upstream prologue.  Unsupported entry
points remain visible as stubs.  Locale, timezone and dynamic-loader utilities
are outside this SDK installation target.

`build_glibc_program.py` verifies a completed SDK's artifact hashes and compiler
identity, links only the SDK libraries and CRT, and checks the resulting ELF.
It uses `-fno-builtin`: the preview bare-metal GCC otherwise removes allocation
calls and their errno observations using a different target runtime model.
This explicit setting preserves public libc calls until an XOS compiler target
provides the correct runtime identity and optimization contract.
Its `--diagnostic` switch allows an incomplete development SDK and labels the
output accordingly.  Such an output is useful for debugging but does not pass
the source-bound guest qualification gate.  `--define NAME[=VALUE]` may be
repeated for fixture-specific preprocessor flags.

## Startup and termination

The CRT consumes XOS startup v1/v2 data, validates bounded argument/environment
arrays, and constructs the private auxv expected by static glibc.  Program
headers refer to the real mapped executable; random bytes come from native
entropy.  glibc allocates its own TCB and static TLS, and the generic native
current-thread TLS operation installs that pointer.  TLS is available before
application constructors; the application errno state starts at zero.

G2 console I/O uses inherited kernel standard handles.  File-backed inherited
descriptors and startup v3 require the separate G3 file backend capability;
terminal handoff is supplied by the G3 terminal adapter below. Path-based spawn
redirection currently fails explicitly.
The linker preserves a per-program `.xos.exec` marker when a qualified fixture
provides one.  Ordinary G2 programs do not advertise exec restoration support.

Normal `exit` and return from `main` require other pthreads to have completed
their libc cleanup.  The exit path checks the thread count before acquiring
libc locks and crosses the native process termination barrier before running
TLS destructors, `atexit` handlers, program destructors and stdio cleanup.
If live pthreads remain, it writes a raw diagnostic and exits with status 127.
This bounded failure avoids hanging on a dead worker's allocator or FILE lock;
normal active-worker exit remains an implementation gap.  Fatal libc failures
also use raw diagnostics without allocator or stdio locks.

## Qualification scope

Run `tests/glibc_static_guest.py --help` for the source-bound guest suite.  It
checks real startup, TLS/errno, malloc/calloc/realloc/aligned allocation, stdio,
constructor/exit ordering, status propagation and resource recovery.  The
system image must include the current-thread TLS contract and implementation.

G3 thread and file suites are separate modules.  Dynamic loading, resolver/DNS,
signals, asynchronous cancellation, process-shared/robust synchronization,
fork/exec from a glibc parent and general POSIX conformance remain outside this
G2 qualification.  Their current stub or unsupported behavior must not be
interpreted as a successful implementation.

## G3 authenticated terminal adapter

`libxos_terminal.a` contains the existing terminal v2 client and a freestanding
adapter compiled only against glibc and native `xos/` headers. The SDK builder
records its inputs and licenses and rejects C++ constructor/runtime dependencies.
Link it inside the same archive group as libc; `build_glibc_program.py` does this.
The actual adapter supplies `.xos.tty` v1, startup v2 authorization and v3 sequence
restoration, and one retained terminal object for aliased FDs. Terminal I/O releases
the file-table lock and serializes complete requests on an independent wait lock.
The public subset includes tcgetattr/tcsetattr/tcdrain/TCIFLUSH and the documented
TCGETS/TCSETS/FIOCLEX ioctl family. Unsupported modes and O_NONBLOCK changes fail
explicitly. Details and the still-deferred outgoing terminal inheritance are in
`docs/contracts/glibc_terminal_v1.md`; host and real guest qualification use
`tests/glibc_terminal_host.py` and `tests/glibc_terminal_guest.py`.
