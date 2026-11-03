> **Evidence version:** This checkout is a path-sanitized derivative, not byte-identical raw evidence. Original and exported hashes are recorded in [the Issue 37 lineage](../../evidence_exports/issue37/aurora_standard_button_dash_lineage.json). Historical input hashes still identify the original run; template roots require manual configuration.

# Standard Qt control fixture under xsh and dash

On the frozen one-core/512 MiB XOS guest, the same final Qt fixture ran once
from xsh and once as a child of the actual dash executable. Both runs passed
the icon, explicit-palette and painted-palette checks; Escape closed the GUI,
and display and process resources returned exactly. `report.json` records
checks, image/payload/dash SHA-256 and the actual QEMU command. Raw serial and
QEMU output are compressed here. This is bounded fixture evidence, not a full
third-party application or assistive-technology qualification.
