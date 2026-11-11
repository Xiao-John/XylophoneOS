# Interactium Architecture

Interactium is the XylophoneOS user-space window manager and CPU compositor. Its
window policy and protocol model are established. Generic IPC channels, service-name
discovery, and endpoint transport are integrated without changing the existing
single-client semantics of Display v1.

```text
Qt / native GUI clients
        | Interactium protocol (controlled IPC)
        v
Interactium service
  session / window manager / input router / compositor
        | display_client (existing sys65/66)
        v
Display Service -> VBE or VirtIO-GPU
```

## Current Code Boundaries

- `src/shared/include/xos/interactium_abi.hpp` defines fixed-width, versioned message
  headers and window, frame, tile, commit, and input payloads. Messages cannot contain
  Qt pointers or client virtual addresses.
- `src/user/interactium/window_manager.hpp/.cpp` implements the first fixed-capacity
  window table: create/destroy, owner checks, geometry, visibility, z-order, focus, hit
  testing, and frame sequencing. The table has a slot for every session slot and
  `create` enforces the per-session window quota, so one client cannot starve the
  others. When the focused window closes, hides, or its session disconnects, focus
  moves to the topmost remaining visible window instead of going dark.
- `src/user/interactium/dispatcher.hpp/.cpp` validates byte messages before forwarding
  them to the service. It checks version, length, sequence number, session identity,
  frame dimensions, tile bounds, and dirty regions.
- `src/user/interactium/transport.hpp` and `service_loop.hpp/.cpp` define the transport
  adapter boundary. An endpoint provides an authenticated owner, receives one message,
  and sends one reply. Each session-loop step handles at most one message so one client
  cannot monopolize the service loop. The loop remains bound to the endpoint supplied
  at creation; disconnects and transport errors release the session and its windows.
- `ipc_transport.hpp/.cpp` maps nonblocking SDK channel wait/recv/send operations onto
  `session_transport`. The owner is queried from the kernel endpoint. `interactiumd`
  publishes a service name and accepts clients; `ic_client` connects by name and
  completes hello/create/disconnect.
- Generic IPC channels use `sys_ipc_endpoint` to create paired, unidirectional endpoints
  with a fixed 4096-byte capacity. `sys_ipc_wait` waits for read/write readiness; only
  the bound sender or receiver process may operate on an endpoint. The creator may
  revoke the channel, and exit of either endpoint process revokes the entire channel.
  `sys_ipc_name` connect/accept automatically transfers the reverse endpoint handle to
  the target service. Direct channels still require applications to pass handles
  themselves.
- `interactiumd` is the sole Display Service client. It maintains a fixed-capacity set
  of server-side pixel surfaces, accepts `BEGIN_FRAME -> WRITE_TILE -> COMMIT_FRAME`,
  composites with CPU source-over blending, and presents the result. Input is routed
  to the owner of the hit window or focused window. A pointer crossing to another
  window also reaches the previously hit window so that window can observe the leave,
  and a key release stays with the window that took the press. When the shared input
  queue overflows, the affected window is told through a `resync` carrying the lost
  count, mirroring the display queue's own recovery event. QPA clients no longer open
  Display v1 directly.
- `src/ports/qt6/qpa/qxos.cpp` connects to Interactium through the name service. Each
  QPA window maps to a window ID, and the backing store packs dirty regions into tiles
  no larger than the endpoint capacity. Each top-level window has its own ID, pixel
  surface, lifecycle, and input polling thread. Mouse input is routed by hit testing;
  keyboard presses go to the focused window while releases return to the window that
  took the press. Qt child widgets are still drawn in
  their parent window's backing store.
- `compositor` provides z-order and CPU source-over composition. The standalone
  `interactium` demo remains available for model and input verification without Qt.
- `tests/interactium_model_test.cpp` is a host-side model test; it does not imply that
  the guest service is included in the boot image.
- `src/user/programs/interactium_demo.cpp` builds as the guest `interactium` command.
  It creates two demo sessions and windows with different simulated owners, supports
  mouse activation and title-bar dragging, and exits on Q or Escape. Both owners are
  still simulated inside one process in this visual demo.
- `interactiumd` and `ic_client` are separate-process IPC qualification programs. In
  the guest, run `spawn interactiumd`, wait for the service-ready message, then run
  `exec ic_client` twice. Each client tests name-based connection, automatic channel
  handle delivery, protocol hello, window creation, and disconnect. After killing the
  service, a new client should report that the service name is unavailable.

At the guest `xos64>` prompt, enter `run`; at `xsh>`, run `interactium-start`. The
supervisor starts Display Service and grants its service role, then starts the ordinary
user-space `interactiumd`. That service occupies the only Display client slot, accepts
QPA clients, and presents the composite. It shares the display exclusively with
`display-start` and `gfxdemo`; they cannot run simultaneously. The two-window model
demo can still be run with:

```text
demo quiet
display-start
exec interactium
```

The Aurora Qt Widgets sample source is `src/ports/qt6/aurora/interactium_showcase.cpp`.
It creates two independent top-level windows: Counter uses `QPushButton` to update a
`QLabel`; Notes uses `QLineEdit` and `QPlainTextEdit`, and clicking Add note or pressing
Enter appends text. Each window has its own close button; Escape exits the application.
The sample calls `aurora::initialize(app)` and uses `desktop_surface` and standard Qt
Widgets. Build an ELF with `build_widgets_fixture.py` using the Qt Widgets, SDK, host
moc/rcc, and target binutils that match the current profile. Import it to the work disk
as `/AURORA.ELF`; after `interactium-start`, run `exec /AURORA.ELF`. Press Escape to exit.

Windows appear on the QEMU display. Clicking a window raises it; dragging its title bar
moves it. Press Q or Escape to return to the shell. The host-side guest test command is
`python tests/interactium_guest.py`; it creates a temporary FAT work disk, sends input
through QMP, and saves initial and post-drag screenshots under `build/`.

The model test can be compiled on a Windows host with the repository's MSYS2 compiler:

```text
C:/msys64/usr/bin/bash.exe -lc 'cd ${XOS_ROOT_MSYS} export PATH=/ucrt64/bin:/usr/bin:$PATH; g++ -std=c++17 -Wall -Wextra -pedantic -Isrc/shared/include -Isrc/user/include tests/interactium_model_test.cpp src/user/interactium/window_manager.cpp src/user/interactium/service.cpp src/user/interactium/dispatcher.cpp -o build/interactium_model_test.exe && ./build/interactium_model_test.exe'
```

Transport-chain memory-queue tests are in `tests/interactium_transport_test.cpp`. They
cover two authenticated clients, handshake, window creation, and disconnect cleanup.

## First-Version Limits

Each session supports at most 8 windows. Pixel storage is a separate first-version
budget: the service owns `surface_capacity` (8) surfaces, so at most eight windows hold
drawable pixels concurrently regardless of how many windows exist. The initial profile
uses CPU source-over composition, 800x600, one outstanding frame, and a bounded number
of dirty rectangles.
Use the controlled-copy path `BEGIN_FRAME -> WRITE_TILE -> COMMIT_FRAME` first, then
design shared buffers based on measurements.

Interactium is the only GUI owner connected to Display Service. `gfxdemo` and the older
Qt QPA also require the exclusive Display v1 client slot; they cannot use the display
at the same time as Interactium.

## Follow-Up Work

1. Add guest qualification for Qt Interactium pixels, window lifecycle, and input routing.
2. Add guest stress tests for the connection queue, unauthorized publication rejection,
   and endpoint-revocation races.
3. Complete cancellable blocking input and full mouse-grab semantics.
