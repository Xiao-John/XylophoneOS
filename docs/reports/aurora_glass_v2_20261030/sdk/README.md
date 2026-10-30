# Native Aurora UI SDK v2

Real native tokens/palette/materials, dark/light layouts, contrast/transparency/motion
policies and High/Balanced/Low/Safe/full-glass-off modes. Optional public API; no
style is installed in another process. See the design and work log 0102.

The final render gate uses the same scene and 16 actual PS/2 characters in each of
11 runs. Each run has 32 recorded QWidget update spans containing successful QPA
presents. At the **10ms clock quantum**, all median spans occupy the zero bin;
p95/max are 10ms. Zero-bin input delivery means below one clock quantum, not zero
latency. The scope includes synchronous widget paint + present, not vblank, startup
exposure paths, moving independent windows, sustained animation or a GPU workload.

| Requested mode | Effective | Image caches | Cache generation | Sampled pages |
|---|---:|---:|---:|---:|
| High | High | 3,840,000 B | 270ms | 6986 |
| Balanced (three runs) | Balanced | 3,840,000 B | 250/260/250ms | 6664 |
| Low | Low | 3,840,000 B | 250ms | 6662 |
| Safe | Safe | 1,920,000 B | 220ms | 6210 |
| Glass off | ordinary opaque | 1,920,000 B | 200ms | 6210 |
| Explicit zero budget | Safe | 0 B | 0ms | 5715 |
| Aurora opaque (three runs) | opaque | 1,920,000 B | 200ms each | 6189 |

Balanced adds **1,945,600 sampled bytes** over matched Aurora-opaque in all three
interleaved pairs. These samples are not an absolute allocation peak. Typing never
regenerates wallpaper/blur caches. Two idle flushes/second in these samples are
consistent with Qt's caret; no new permanent animation timer is added.

The blur's clamped edges, separable rounding and premultiplied channel invariant
match 396 independent direct-neighborhood vectors; six malformed calls reject.
The real zero-budget gate is admission denial, not genuine allocator OOM injection.
High/Balanced/Low retain actual sampled glass; opaque/Safe are not called full-glass
performance successes. Their image differences are recorded in performance_summary.json.

The native semantic fixture has 25 actual assertions: discovery is not authority,
one-shot grants, stale/revoked/expired/changed proposal refusal, read-only/password
refusal, UNKNOWN/no replay, destroyed target, content/password protection, hidden
and locally occluded nodes, resource denial, diff and node removal. An independent
host mock chooses an actual guest SSG target; the guest fixture's explicit local
authorization button changes and verifies the real QLineEdit. An old-process
proposal is rejected after restart, then the populated SSG process is killed and
resources return exactly. This is not cross-process OS action authority.

The independent Studio uses standard Widgets and public headers/archive, with real
editing, theme switch and an in-surface menu. The non-Aurora legacy probe is exactly
byte-identical to the archived E17 ELF (`f52b1bb2…`), and still runs/cleans up.
