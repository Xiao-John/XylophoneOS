# Frozen local Aurora Browser qualification

`qualification.json` binds exact target source, ELF/static libraries, system,
Qt/SDK/compiler inputs, five real guest suites and paired VBE/VirtIO scanout.
`browser.receipt.json` contains actual cross-build commands and tool hashes.
`system.manifest.json` preserves build `3fb1bb7d6b9e7bf9` and all inputs/artifacts.
Final browser ELF SHA256:
`86044be0fe0f4016fb1d98ffa5e1321e0928706e312e85fad2111dc4f33286dd`.

- `final-interactive`:10 checks; real PS2 link, address/history/refresh/scroll,
  in-window tab histories, session bookmark, BMP/UTF8 and exact teardown.
- `final-negative`:17 checks; missing/malformed/deep/huge HTML, whitespace
  attribute bypass, oversized dimensions, CSS exponent/import/quotas/external
  rejection, corrupt BMP, valid recovery and exact teardown.
- `final-lifecycle`:7 checks; repeated launches, kill, Display Service failure,
  restart/new browser, exact resources and file/serial rescue.
- `final-no-display`:3 checks; explicit QPA startup failure/reclamation/rescue.
- `final-virtio`:same10 interactive checks with real GPU device and VBE disabled;
  backend_execution.json captures the unchanged-runner adapter/commands/hashes.

The paired initial scanouts are identical across1,440,000 RGB bytes. Images in
these directories are actual QEMU guest screenshots, not host UI mockups. Their
sources are the committed `src/ports/aurora_browser/pages` HTML/CSS/BMP fixtures.
Raw serial/QEMU logs are losslessly gzip-compressed. `iterations` preserves both
actual failures and the first overly weak runner's misleading PASSED report;
visual QA rejected its unstyled page before final qualification. No evidence was
rewritten to conceal that failure.

B0/B1 pass only for the admitted local subset in the contract. B2 has no qualified
network service; HTTPS/JavaScript/Internet and complete static distribution are
not supported/qualified. Process memory is sampled; absolute peak/long stress
remain NOT_RUN. See work_log0083 and contracts/aurora_browser.md for boundaries.
