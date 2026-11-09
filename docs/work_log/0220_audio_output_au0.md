# Audio output AU0 reconnaissance

## Scope and result

Completed AU0 source reconnaissance and standalone PC Speaker-to-WAV routing probe on branch `codex/audio-output-au0`. The probe used Debian sid QEMU 11.1.3 (`1:11.1.3+ds-1`) because the plan's exact QEMU 11.1.2 source build produced a full 2.8 GB Docker image that could not be launched with the Docker VFS disk budget. QEMU v11.1.2 source was checked for the `pcspk-audiodev` machine alias; runtime evidence is from 11.1.3, one patch release newer.

The probe confirms the `pc-i440fx-10.0` speaker route and an approximately 5.0136 kHz signal captured as 44.1 kHz, 16-bit stereo WAV. The guest used PIT channel 2 and waited on BIOS PIT0 ticks while sounding; the clock advanced. This does not establish XOS scheduler behavior, audio authorization, or any implemented XOS audio feature.

## Decisions

- Tone sequencing and service policy remain user space.
- AU1 must specify a fixed authenticated PIO resource for exactly `0x42`, `0x43`, and `0x61`; current sys82 permission remains COM1-only.
- Proposed AU1 hardware lease: at most 2,000 ms per tone using system monotonic time. Expiry, owner exit/fault, revoke, or invalidation must force a narrow platform gate clear that preserves unrelated `0x61` bits. No syscall/protocol registration or implementation was made here.
- QEMU's `-audiodev wav` output had zero RIFF/data size fields after exit. The run script preserves raw WAV and repairs only the two size fields in a derived analysis file. Audio capture ends with voice deactivation and does not include explicit post-stop zeros; this limitation needs to remain visible in later audio acceptance.
- No real host speaker was used and no audible-output claim is made.

## Files changed

- `docs/plans/audio_output.md`: records AU0 outcome and links this probe report.
- `docs/reports/audio_output_au0_20261109/report.md`: source findings, architecture decision, measurements, limits, and AU0 status.
- `docs/reports/audio_output_au0_20261109/probe/dockerfile`: reproducible Debian sid/QEMU 11.1.3 probe environment.
- `docs/reports/audio_output_au0_20261109/probe/pcspk_boot.asm`: standalone BIOS test image source; not XOS code.
- `docs/reports/audio_output_au0_20261109/probe/run_probe.sh`: QEMU help/runtime probe, capture, RIFF length normalization, and signal analysis.
- `docs/reports/audio_output_au0_20261109/manifest.json`: flat SHA-256 root manifest for the new report directory.

The user-requested token remains only in ignored `.env` (mode 0600); it is not in the report manifest or Git diff.

`docs/state.md` was not changed; the development discipline reserves it for whole-project baseline/merge/release updates. The per-line work log is the handoff record.

## Verification evidence

- `docker build --file docs/reports/audio_output_au0_20261109/probe/dockerfile --tag xos-qemu-au0:11.1.3 docs/reports/audio_output_au0_20261109/probe` — PASS; Debian base is digest-pinned and QEMU package is pinned to `1:11.1.3+ds-1`.
- `docker run --rm -v "$PWD/docs/reports/audio_output_au0_20261109/probe:/probe:ro" -v "$PWD/build/audio_output_au0:/out" xos-qemu-au0:11.1.3 sh /probe/run_probe.sh` — PASS on four repeats; latest run measured 42,968 frames, 0.974 s, 5,013.70 Hz. Four runs ranged 41,245–42,968 frames, 0.935–0.974 s, and 5,013.47–5,013.70 Hz. QEMU exited 0.
- Final ignored capture SHA-256: raw `e081efaf04c20143c4874e07d97665c1bc1516dc7457e60beb6eec8ab1f6201e`; normalized `48697e9cd6927eaed1a5b1ead6c2255ad981af9f11564639089041a559eb223a`.
- `git diff --check` — PASS after documentation and probe updates.
- Full XOS build/smoke and XOS guest authorization/lifecycle tests — NOT RUN; no XOS audio implementation was added.

Raw/derived WAV captures are in ignored `build/audio_output_au0/`, not in the report manifest or public source changes. The script reproduces them.

## Next step

Begin AU1 only after specifying the fixed PIO resource and monotonic hardware lease lifecycle under C20/C22/C25/C28/C29. Exercise timeout, owner exit/fault, revoke, authorization failure, and channel-0/timer regression before any user-facing melody service. Do not interpret this AU0 probe as hardware access granted to user processes or as XOS audio implementation.
