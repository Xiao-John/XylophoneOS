# SPDX-License-Identifier: Apache-2.0
"""Host check: the kernel PC speaker lease outlasts the longest legal note.

Reads the real sources (src/shared/include/xos/audio_abi.hpp and
src/kernel/arch/x86_64/tasks.cpp), compiles the actual pc_speaker_lease_ns
statement from tasks.cpp against the shared audio header, and asserts:
  lease > max_note_ms, and lease >= max_note_ms + 500 ms of startup margin.
It also pins the ordering facts the expiry bug depended on: the clock only
advances in timer_entry, expire_pc_speaker_lease() runs there before
expire_waiters(), and the sys82 release path denies an owner that already
lost the speaker. A small tick model then shows that a max-length note
always lost the speaker under the old equal 2,000 ms lease and completes
under the lease derived from the current source.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "src/kernel/arch/x86_64/tasks.cpp"
AUDIO_ABI = ROOT / "src/shared/include/xos/audio_abi.hpp"
TICK_NS = 10_000_000  # xos::clock::resolution_ns, 100 Hz IRQ0
MARGIN_NS = 500_000_000


def lease_statement(tasks_text):
    match = re.search(r"constexpr u64 pc_speaker_lease_ns\s*=[^;]*;", tasks_text)
    assert match is not None, "pc_speaker_lease_ns definition missing"
    return match.group(0)


def compile_and_read_lease(statement):
    """Compile the real statement in the kernel's namespace shape, run it."""
    program = (
        "#include <xos/audio_abi.hpp>\n"
        "#include <cstdio>\n"
        "namespace xos { namespace arch { namespace {\n"
        + statement + "\n"
        "} } }\n"
        "int main() {\n"
        "    static_assert(xos::arch::pc_speaker_lease_ns > "
        "xos::u64{xos::audio::max_note_ms} * 1000000ull, "
        "\"lease must exceed the longest legal note\");\n"
        "    static_assert(xos::arch::pc_speaker_lease_ns >= "
        "xos::u64{xos::audio::max_note_ms} * 1000000ull + 500000000ull, "
        "\"lease must keep a 500 ms startup margin\");\n"
        "    std::printf(\"%llu\\n\", "
        "static_cast<unsigned long long>(xos::arch::pc_speaker_lease_ns));\n"
        "    return 0;\n"
        "}\n"
    )
    with tempfile.TemporaryDirectory(prefix="xos_s4_lease_") as temp:
        source = Path(temp) / "lease_check.cpp"
        binary = Path(temp) / "lease_check"
        source.write_text(program)
        command = ["c++", "-std=c++20", "-Wall", "-Wextra",
                   "-I", str(ROOT / "src/shared/include"),
                   str(source), "-o", str(binary)]
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        run = subprocess.run([str(binary)], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        return int(run.stdout.strip())


def check_ordering(tasks_text):
    """Pin the causal-chain ordering inside tasks.cpp."""
    assert "#include <xos/audio_abi.hpp>" in tasks_text, \
        "tasks.cpp must derive the lease from the shared audio header"
    timer = tasks_text[tasks_text.index("void* timer_entry("):
                       tasks_text.index("void* syscall_entry(")]
    assert timer.index("platform::timer_interrupt();") < \
        timer.index("expire_pc_speaker_lease();"), \
        "clock must advance before the lease is expired"
    assert timer.index("expire_pc_speaker_lease();") < \
        timer.index("expire_waiters();"), \
        "lease expiry must run before sleepers wake in the same tick"
    expire = tasks_text[tasks_text.index("void expire_pc_speaker_lease()"):
                        tasks_text.index("bool display_endpoint(")]
    assert "clock::monotonic_ns() < owner->pc_speaker_deadline_ns" in expire
    assert "release_pc_speaker(owner);" in expire
    switch = tasks_text[tasks_text.index("void switch_to("):
                        tasks_text.index("interrupt_frame* make_initial_frame(")]
    assert "pc_speaker_lease_started = true" in switch
    assert "pc_speaker_lease_ns" in switch, "lease must start at first switch_to"
    assert "if (second != 0 || current->pid != pio_speaker_owner)" in tasks_text, \
        "release must be denied once expiry cleared the owner"


def tick_model(lease_ns, max_note_ns, startup_ns):
    """Model IRQ0 ordering: expiry is processed before sleep wakeups.

    monotonic time is quantised to TICK_NS; t0 is the worker's first
    switch_to, t1 the later clock read in audio_tone. The wake deadline is
    t1 + note, the lease deadline t0 + lease. Both are handled in
    timer_entry, expiry first, so the release after the wake is denied when
    the expiry tick is not later than the wake tick.
    """
    t1 = (startup_ns + TICK_NS - 1) // TICK_NS * TICK_NS
    wake_tick = (t1 + max_note_ns) // TICK_NS
    expire_tick = (lease_ns + TICK_NS - 1) // TICK_NS
    return expire_tick <= wake_tick  # True means release denied (exit 6)


def main():
    abi_text = AUDIO_ABI.read_text()
    max_note_ms = int(re.search(r"max_note_ms\s*=\s*(\d+)", abi_text).group(1))
    max_note_ns = max_note_ms * 1_000_000
    tasks_text = TASKS.read_text()
    statement = lease_statement(tasks_text)
    lease_ns = compile_and_read_lease(statement)
    margin_ns = lease_ns - max_note_ns
    assert margin_ns >= MARGIN_NS, f"margin {margin_ns} ns below {MARGIN_NS} ns"
    check_ordering(tasks_text)

    # Old equal lease: every max-length note lost the speaker before release,
    # whatever the startup delay, because expiry is not later than the wake.
    assert all(tick_model(max_note_ns, max_note_ns, s * 1_000_000)
               for s in range(0, 5001)), \
        "model: the old equal lease must reproduce the expired bug"
    # Current lease: startup up to one tick below the margin stays safe
    # (monotonic time is quantised to the 10 ms scheduler tick).
    safe_ms = (margin_ns - TICK_NS) // 1_000_000
    assert not any(tick_model(lease_ns, max_note_ns, s * 1_000_000)
                   for s in range(0, safe_ms + 1)), \
        "model: current lease must cover max note plus startup delay"
    # Residual limit: startup reaching the margin is the documented bound.
    assert tick_model(lease_ns, max_note_ns, margin_ns), \
        "model: startup at the margin must stay the documented limit"

    print(f"PASS lease_ns={lease_ns} max_note_ms={max_note_ms} "
          f"margin_ms={margin_ns // 1_000_000}")
    print("PASS ordering: expire precedes wake, release denies lost owner")
    print(f"PASS model: old lease always expired max notes; "
          f"startup<={safe_ms}ms now safe, >={margin_ns // 1_000_000}ms not covered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
