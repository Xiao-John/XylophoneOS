# Standard Qt button and explicit palette regression

SDK base `758dde49d312277135fb2fa51887c2b4a94d6761`; real XOS guest image
SHA-256 `165686bb0de0b0b2f33645ede2cf10c2badb25ea363f3ef57ed74641503b0b08`.
The xsh-launched Qt ELF renders an ordinary enabled `QPushButton` with a magenta
icon and an explicitly colored `QLineEdit`, and captures QEMU scanout.

- `before`: three checks fail: button icon has zero matching pixels; the theme
  overwrites the explicit palette; the requested base color is not painted.
- `initial-fix`: two state/icon checks passed, but its screenshot still showed
  an incorrectly dark field. This incomplete check is retained, not claimed as
  a complete fix.
- `final`: three checks pass: 576 icon pixels, the explicit palette survives a
  theme application, and 34,952 pixels use the explicit field background. Exact
  guest resource counts return to `[130279, 2, 0]` after service shutdown.

The final change retains Aurora's panel, delegates standard button label layout
to Qt (including the icon and mnemonic path), and uses the effective widget Base
palette for line-edit fill. These checks do not qualify all Qt controls, menus,
accessibility technologies, disabled states or full third-party applications.
The original SDK screenshot/performance gate remains historical; the combined
Desktop/Notes/Browser regression must be run on the new source combination.

`report.json` files include actual QEMU invocations, hashes and check results;
original PPM scanouts and serial logs are compressed alongside PNG derivatives.
Build receipts and `evidence.json` preserve commands and SHA-256 inputs.
