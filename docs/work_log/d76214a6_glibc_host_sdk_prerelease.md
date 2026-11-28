# glibc host SDK prerelease delivery

The host SDK recipe composes a new distribution from the checksum-pinned
Preview 2 host root and an authenticated static glibc C/C++ application kit.
Host files outside the explicit XOS target subtree must remain byte-identical.
The default `xos-app` and `XOS_SDK` select glibc; the former newlib SDK has a
separate legacy location. The binary includes a new ISO, profile/source/license
bindings, a file manifest and a self-contained consumer smoke. The matching
source asset contains current glibc/GCC upstream archives and their signature
material together with the corresponding XOS source and recipes.

The consumer gate freshly extracts the completed archive, verifies every
manifest entry and mounts only an empty consumer directory alongside the SDK.
It runs C/C++ init/build/check/pack, extracts verified XPK ELF payloads, executes
them in QEMU TCG, and checks output, exit status, resource recovery and preserved
user data. The report binds that run to its own archive/profile/ISO identities.

The manual-only workflow builds all target components inside Preview 2 and
requires the system license audit and consumer gate before creating a new tag.
Tag creation is atomic and refuses existing names. Uploads go to a draft;
publication follows exact asset-name/size/digest checks. The workflow supplies its
token only to the release preflight/publication steps. No normal push or pull
request publishes a release.

Initial implementation checks: all three Python entry points compile; the
actual staged public-path scan has zero findings. A fresh native system build
inside Preview 2 produced `3a3e74a54efe5374`; its 10-item license audit passed
with no open item. Both the relocated zlib lock URL and its updated registry
digest are included. Completed-archive consumer results are recorded separately
after running the new recipe; no success is inferred from compilation alone.

Independent review found that the source snapshot needed the licensing
register's evidence closure and had to exclude untracked workspace files.
The recipe now captures committed Git objects, carries the commit and file
binding into the isolated build tree, and rechecks every built source against
that binding when packaging. The independent cropped-tree license audit passed
all 10 materials with zero open items after restoring the evidence inputs.
The release upload gate also checks GitHub's independently computed SHA-256
digest for every uploaded asset before publication.
