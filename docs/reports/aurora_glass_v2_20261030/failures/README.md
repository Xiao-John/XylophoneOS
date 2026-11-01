# Original failures and corrections

Raw attempts are retained with their original statuses; none is relabeled passing.

- First compile lacked the explicit thread-stats header; a missing host Python
  executable was worked around with the bundled Python 3.12.14 without repairing
  or modifying the user's global Python installation.
- Initial UI harness captured the old layout and clicked stale coordinates after
  theme switching. Final tests wait for rendered state, check actual theme JSON
  and pixels, and use live control positions.
- Full SSG traversal hit its real 30ms budget before reaching the requested content.
  Capped output was never complete; targeted document/body queries now avoid that
  work while retaining the cap and explicit partial status.
- The semantic harness parsed a partially received serial JSON line. Final parsing
  waits for a complete framed line, while the guest state/action verification stays.
- Session testing assumed Escape always quits a new note. The actual unsaved guard
  correctly appeared; the final synthetic test explicitly chooses Discard.
- Browser's merged candidate path logged a pre-commit/pre-layout anchor position
  (outside the screen). Final instrumentation obtains visible real render fragments
  after layout in its existing sample callback; actual pointer/link behavior passes.

True allocator OOM, wedged device faults, production permission brokering, arbitrary
hostile app stress, hardware/SMP and final aesthetic approval remain unqualified.
