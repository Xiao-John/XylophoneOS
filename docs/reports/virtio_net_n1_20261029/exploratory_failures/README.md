# Exploratory failures retained separately from qualified inputs

None of these attempts is counted as qualified. Final source/SDK/image inputs are
in ../inputs and qualification.json; early exploratory source manifests/images were
not frozen before rebuild, so the early logs cannot provide a complete reproducible
source identity. Their actual guest output and raw tool errors are retained.

- First compilation stopped at -Werror misleading-indentation; braces corrected,
  warning flags retained. No suppression.
- `echo_01`: private relocated QEMU binary failed before guest boot: missing
  `_cs_close` dynamic symbol. Working pre-existing qemu-prefix binary was used;
  no application, proxy, TUN or daily environment setting changed.
- `echo_02`/`echo_03`: actual PCI slot3/IRQ11 and16 TX completions; noMRG modern
  headers were all zero in actual RX, strict num_buffers=1 validation rejected18
  packets, so echo failed. The final implementation negotiates MRG_RXBUF and keeps
  strict one-buffer count/MTU checks. It does not silently accept zero.
- lwIP probe01: actual newlib ssize_t is long; upstream fallback typedef int
  conflicted because SSIZE_MAX absent. The arch glue includes the real types and
  defines SSIZE_MAX to LONG_MAX for this x86-64 SDK.
- probe02: relocated target GCC invoked host assembler; explicit private
  COMPILER_PATH target as/ld binding corrected this, matching the system builder.
- probe03: upstream lightweight-protection default needed sys_prot_t. The deliberate
  NO_SYS single userspace event loop sets SYS_LIGHTWEIGHT_PROT=0 and must not call
  lwIP from an IRQ/thread concurrently; no dummy multithreaded lock was added.
- probe04: the probe read headers while this worktree's build regenerated that SDK,
  so _ansi.h was transiently absent. Final build/probe were sequential against an
  immutable qualified SDK. This was a setup race, not a supported missing header.
- fixture_final_gates: optional isolation setup requested128MiB FAT32, below the
  actual512MiB test helper floor; failed before QEMU, corrected to512MiB sparse disk.
- fixture_final_gates_v2: guest really faulted vector14, but trace-disabled Xshell
  printed `program faulted` while the harness waited for the trace-only wait record.
  Final runner enables trace and quiets bootstrap demo tasks before measuring
  process resources; both vector14 and13 then pass on the final qualified image.

Preliminary successful echo/matrix attempts remain privately under build/network;
only the final qualified_system/qualified_quota gates are claimed in this report.

Root regression adapters also preserve two setup failures: leaked target
COMPILER_PATH made later host-clang links fail; restoring the environment after
target probes fixed it. An E04 no-workdisk boot reached the existing maintenance
guard; a dedicated512MiB FAT32 disk restored the actual intended fixture. Both
original logs/reports remain, and the corrected final21-suite matrix is separate.
