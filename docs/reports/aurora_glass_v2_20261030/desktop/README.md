# G1 single-Surface desktop/session

Wallpaper, two native compositions, Dock/rail, Home/Apps/Studio/Settings/Quality,
panel hide/restore, real standard controls and local notices all run in XOS.
Midnight Current is the user-selected refinement direction; aesthetic approval
is pending. Larger-mode layout, full animation/optics, global dialogs/files,
window manager/task switcher and cross-process theme migration are not qualified.

The explicitly authorized ordinary session parent starts the shell, waits for it
to close/release the Surface, starts Notes/Browser/independent Studio as separate
GUI processes and returns to the shell after each ends. Notes' actual unsaved guard
is respected. All three handoffs and final resource return pass. A standalone shell
is an honest preview and explains why it needs the session for launch.

An independent second process still receives connect=-16, and ordinary direct
present is denied (-1). Desktop kill, display loss with exit 72, serial survival,
service restart, new desktop, non-Aurora legacy binary and exact resource return pass.
These are G2-Scout failure/compatibility facts, not a multiprocess compositor.
No application sees another application's RAM, scanout or DMA. The proposed generic
transport, identity, revocation and copy protocol requires separate review first.
