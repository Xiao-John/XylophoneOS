# Interactium review fixes

PR #90 head `c83900e04f839ba877bbd10a29d4e7532145f7cf`; local, uncommitted review follow-up.

- Stage tile writes separately and copy them to the visible surface only on an accepted commit. Beginning a frame preserves the previous pixels; cancelling leaves them unchanged.
- Keep a disconnected channel until the acknowledgement is consumed, then close it and release the service slot. A peer that closes early is also reclaimed.
- Make the two-window guest test use native paths and the PATH QEMU on POSIX hosts.

Validation on macOS, isolated worktree:

- `python3 scripts/build.py`: passed, build ID `d45d5ac03d5ae44c`.
- Host C++ model and transport tests: passed, including staged pixels, cancellation, and acknowledgement-drain lifecycle.
- `QEMU=qemu-system-x86_64 python3 tests/interactium_guest.py`: passed, including IPC probe, two-window display, pointer drag, and demo exit. Screenshots are in `build/interactium_demo*.png`.
- `python3 tests/abi_doc_consistency.py`: passed.

Not run: Aurora Qt desktop guest test requires a disk containing its built desktop ELF and Python Pillow; neither was prepared for this run. The model and demo results do not establish desktop qualification. The added staging buffers increase the service's static memory consumption; no resource-pressure qualification was performed.
