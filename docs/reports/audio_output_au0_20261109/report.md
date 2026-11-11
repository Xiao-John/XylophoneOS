# Audio output AU0 reconnaissance and probe

Date: 2026-11-09
Branch: `codex/audio-output-au0`
Input plan: [`docs/plans/audio_output.md`](../../plans/audio_output.md)
Scope: AU0 reconnaissance and a standalone QEMU PC Speaker route probe. No XOS audio implementation, syscall, or service protocol was added.

## Source findings

- `src/kernel/platform/pc/interrupts.cpp::timer_init()` programs PIT channel 0 at 100 Hz through control port `0x43` and data port `0x40`. PIT channel 2 uses its own counter at `0x42`; selecting channel 2 through `0x43` does not require rewriting channel 0's divisor. The probe preserved channel 0 and used BIOS tick updates as an independent time reference while channel 2 sounded.
- `src/kernel/include/xos/platform.hpp` keeps hardware addresses out of common kernel code. ISA port instructions are in `src/kernel/arch/x86_64/io.hpp`.
- The TSS I/O bitmap denies all ports by default. `sys_pio_grant` (82) currently grants only the fixed COM1 range `0x3f8..0x3ff` to an authenticated supervisor's building direct child; other resource IDs are rejected. `sys_device` (112) explicitly excludes PIO. Neither existing contract grants speaker access or imposes a speaker output lease.
- The QEMU v11.1.2 source tag defines the machine alias `pcspk-audiodev` in `hw/i386/pc.c`. Runtime verification used the Debian sid QEMU 11.1.3 package because the locally built 11.1.2 image could not be launched within the Docker VFS storage budget. QEMU 11.1.3 is one patch release newer. Its `pc-i440fx-10.0` machine accepted the alias and routed PC Speaker output to WAV.

## Probe and result

The standalone real-mode probe in [`probe/pcspk_boot.asm`](probe/pcspk_boot.asm) programs PIT channel 2 mode 3 with divisor 238, enables the speaker gate, waits 18 BIOS PIT0 ticks, clears only bits 0 and 1 at port `0x61`, waits 18 more BIOS ticks, then halts. It does not change channel 0's control word/divisor. The QEMU runner is [`probe/run_probe.sh`](probe/run_probe.sh); its Debian sid image is pinned to the QEMU package version in [`probe/dockerfile`](probe/dockerfile).

Runtime arguments used:

```text
-machine pc-i440fx-10.0,pcspk-audiodev=audio0
-audiodev wav,id=audio0,path=/out/pcspk-raw.wav
-accel tcg -smp 1
```

QEMU 11.1.3 reported the `wav` audio driver. `-machine pc-i440fx-10.0,help` did not list the dynamic speaker alias, but the actual invocation with `pcspk-audiodev=audio0` started and completed successfully. QEMU's `wav` backend left RIFF and data lengths as zero after process quit. The raw capture is preserved under ignored `build/audio_output_au0/pcspk-raw.wav`; the probe creates `pcspk.wav` as a derived copy that changes only those two length fields using the closed file's actual size, then verifies and analyzes it.

Four repeated runs:

- QEMU: `11.1.3 (Debian 1:11.1.3+ds-1)`; machine: `pc-i440fx-10.0`; accelerator: TCG; one CPU.
- WAV: 44.1 kHz, 16-bit stereo; 41,245–42,968 frames (0.935–0.974 s).
- Zero-crossing estimate: 5,013.47–5,013.70 Hz; requested PIT output is `1193182 / 238` = about 5,013.37 Hz.
- Signal was present in each 100 ms window. The file ends when QEMU deactivates the PC Speaker voice after the guest clears the gate. QEMU does not append zero-valued frames once this voice becomes inactive, so this probe establishes that captured output terminates with the gate, but does not produce a trailing block of explicit silence samples.
- The BIOS tick wait continued during the tone, supporting channel-0/channel-2 isolation in QEMU. This is not an XOS scheduler or guest-kernel timer acceptance.
- No host speaker was used; no audible-output claim is made.

## AU0 decisions for AU1

1. Keep tone generation, note sequences, validation, and service policy in user space. Do not give a process IOPL or arbitrary PIO access.
2. Extend the existing PIO resource contract only through a separately specified fixed PC Speaker resource for ports `0x42`, `0x43`, and `0x61`. Preserve the current authenticated supervisor-to-building-child authority chain; COM1 ownership is not speaker permission.
3. The speaker needs a kernel-enforced lease because user-space `sleep_until` cannot silence hardware after a stuck service. Use the existing monotonic deadline domain and a maximum 2,000 ms hardware lease, matching the planned maximum duration of one tone. On lease expiry, process exit/fault, explicit revoke, or grant invalidation, a narrow PC platform safety hook must clear only speaker gate/data-enable bits while preserving other `0x61` bits. A stuck service is therefore bounded to at most one lease; normal owner exit stops immediately. AU1 must justify this safety-stop mechanism under C20/C28 and test all teardown paths before implementation.
4. Do not start the audio service or claim client cancellation semantics until the PIO extension, lease owner, request/client disconnect behavior, and old-handle invalidation are frozen against actual IPC lifecycle behavior.
5. QEMU's audio WAV backend is usable with the planned machine alias. Its output file needs a post-exit RIFF-length repair for analysis because the backend left both length fields zero in this run. The run script preserves raw bytes and repairs only the header in a separate derived file. The capture ends at speaker voice deactivation rather than including trailing zero samples; AU1/AU2 must retain this limitation in waveform acceptance or select a capture path that records explicit silence.

## AU0 status

**PASS WITH PATCH-VERSION SUBSTITUTION AND CAPTURE LIMITS.** Source review plus a QEMU 11.1.3 runtime probe confirms the `pc-i440fx-10.0` PC Speaker audio alias, WAV routing, a measured PIT channel-2 tone, and continued PIT0 ticks during the tone. QEMU v11.1.2 source confirms the alias exists at the plan's target tag; its binary was not run. The temporary probe is not XOS guest acceptance. AU1 remains unimplemented and must not be inferred from this report.

No public ABI, service protocol, kernel source, default QEMU command, or default device topology changed.
