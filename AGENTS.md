# XOS agent entry point

Before working, read these files in order:

1. `docs/Discipline.md` — development and handoff rules.
2. `docs/state.md` — current state, evidence, and next task.
3. `docs/xos_plan.md` — accepted direction; distinguish C/P/O/D decisions.
4. Relevant entries in `docs/work_log/` and `docs/decisions.md`.

Before kernel or loader edits, also read `docs/architecture_and_boot.md`,
`docs/cpp_subset.md`, and `docs/toolchain.md`. Keep firmware, ISA, platform,
and common kernel code separated. The second-ISA compile check is not a port.
For task/SDK/loader work, also read `docs/e04_loader_sdk.md` and the supervisor
command pages. ELF parsing belongs to user space, not the kernel.

Use snake_case for new self-authored code and file names. The explicitly requested
`docs/Discipline.md` is a naming exception.

`localpilot/` is a separate project. Do not modify, clean, scan recursively, or
incorporate it into XOS builds. Do not use root-wide destructive cleanup commands.

Do not infer that multiple agents are active. If they are, claim non-overlapping
work in the handoff documents before editing; report conflicts rather than
overwriting another agent's work.
