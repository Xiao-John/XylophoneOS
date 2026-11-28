# glibc SDK CI host user namespaces

The first manual release run at `c8c5c32` failed on Ubuntu 24.04 during the
initial SDK launch: `bwrap: setting up uid map: Permission denied`. Locked
downloads had completed, but no target build or publication completed. The
failed [run 46109935710](https://github.com/Xiao-John/XylophoneOS/actions/runs/46109935710)
remains the failure record; its publication step was skipped and no tag was
created.

The workflow now selects Ubuntu 22.04 and explicitly installs Python 3.12
through `actions/setup-python@v6`, since the outer recipe uses Python's
`hashlib.file_digest`. A new early gate checks that the job runs as a non-root
user, checks the selected Python runtime, and starts a minimal Bubblewrap
process with user/PID/IPC/UTS namespaces, a read-only root and an empty environment.
This runs before downloading the large SDK archive. The SDK launcher and its
isolation, host security configuration and normal build user are unchanged.

Primary sources checked on 2026-11-28:

- [Current runner image list](https://github.com/actions/runner-images/blob/main/README.md)
  includes `ubuntu-22.04`.
- [Runner retirement announcement](https://github.com/actions/runner-images/issues/14254)
  schedules retirement for 2027-04-17; this host selection is temporary.
- [Official setup-python v6.0.0 release](https://github.com/actions/setup-python/releases/tag/v6.0.0)
  specifies Node 24 and runner 2.327.1 or newer.

Local verification covers YAML parsing, the manual-only trigger, preflight
ordering, all embedded shell blocks, and the public-path scan. The exact
Bubblewrap namespace command also exited 0 as the local unprivileged user;
this checks the invocation, not the replacement GitHub runner. The replacement
GitHub-hosted runner must still execute the full build and consumer qualification
from the newly merged public commit. Rerunning the old commit does not apply
this fix and is not a replacement qualification.
