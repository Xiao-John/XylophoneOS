# XOS glibc host SDK preview

This Linux x86-64 SDK defaults to the authenticated static glibc 2.44 C/C++
application kit. The included GCC, binutils, NASM, QEMU and Linux host files
are preserved from the checksum-pinned Preview 2 distribution. The bundled
system ISO is built from the source revision in `host-sdk.json`.

## Use the SDK

Install Bubblewrap and Zstandard with your Linux package manager. Verify the
downloaded assets with `sha256sum -c SHA256SUMS`, then extract the binary archive
with `tar --zstd -xf`. Run the launcher from its extracted directory:

```sh
mkdir consumer
./xos-sdk --workdir consumer xos-sdk-smoke
./xos-sdk --workdir consumer xos-app init hello --id example.hello --language cpp
./xos-sdk --workdir consumer xos-app build hello
./xos-sdk --workdir consumer xos-app check hello
./xos-sdk --workdir consumer xos-app pack hello --output hello.xpk
```

The launcher mounts the SDK root read-only and the selected consumer directory
as `/work`. It clears inherited environment variables. `XOS_SDK` identifies
`/opt/xos/glibc/sdk/sysroot`, and `XOS_APP_KIT` identifies `/opt/xos/glibc`.
`xos-app` selects the kit's own immutable profile and SDK. It rejects attempts
to override that selection. Use `/bin/bash -c` for shell commands; a login
shell can replace the SDK's tool search path.

The smoke uses a new `sdk-smoke` directory. It builds and verifies C and C++
XPK packages, extracts their authenticated ELF payloads, and runs those exact
bytes in the supplied ISO using QEMU TCG. It checks glibc version/file access,
C++ vector/thread/exception behavior, exit status, resource recovery and
preserved user data. Run it in a new consumer directory when repeating it.
Its minimized result is `sdk-smoke/qualification.json`; detailed logs and the
temporary work disk remain in that consumer directory.

The launcher retains Preview 2's optional `--offline` network namespace switch.
Whether that option works depends on the host's namespace policy; the standard
qualification uses the ordinary launcher. The test guest has no network device.

## Compatibility and source material

The former Preview 2 newlib SDK, ISO and smoke are retained under
`/opt/xos/legacy/newlib`; `XOS_LEGACY_NEWLIB_SDK` names its SDK. Keep existing
newlib profiles and package disks separate. This legacy copy is not the original
1024 frozen rollback distribution. The new default concerns the static C/C++
application SDK. Full glibc userland, dynamic applications and release-disk
qualification have their own distribution records.

Download the matching `*-sources.tar.zst` asset with the binary SDK. It includes
the exact glibc and GCC source archives, authenticated signatures/key material,
XOS source, patches, recipes and license records. The kit also retains its
source-verification records and target license notices. `base-preview-2` retains
the unchanged host distribution's source indexes, Debian package records and
notices; licenses and Homebrew formulas remain in the host root filesystem.

`host-sdk.json` binds the base archive, unchanged host tree, source archive,
glibc profile/kit and new ISO. `file-manifest.json` covers the extracted binary
SDK files and symlink targets. `package.json`, `qualification.json` and
`SHA256SUMS` shipped as release assets bind the final archive and its own
independent consumer run. A build-time `guest_qualification` field remains
historical metadata; the final `qualification.json` supplies the actual result.

## Maintainer build and publication

From a clean, committed checkout on Linux x86-64 with Python 3.11+, Bubblewrap,
Zstandard, tar and working user namespaces:

```sh
python3 scripts/build_glibc_host_sdk.py build \
  --tag xos-sdk-glibc-preview-3 \
  --workdir build/host-sdk-work --output build/host-sdk-release --jobs 2
```

The release workflow currently uses `ubuntu-22.04` and
[`actions/setup-python@v6`](https://github.com/actions/setup-python/releases/tag/v6.0.0)
with Python `3.12` for the outer host recipe. Before downloading the SDK, it
checks the Python version and launches a minimal Bubblewrap process with
unprivileged user, PID, IPC and UTS namespaces. The build itself runs as the
normal runner user. A host that rejects these namespaces fails this preflight.
The SDK's own read-only root and consumer-directory mounts remain in its launcher.

GitHub still lists the [Ubuntu 22.04 runner](https://github.com/actions/runner-images/blob/main/README.md)
as available. Its announced [retirement date is April 17, 2027](https://github.com/actions/runner-images/issues/14254),
so migrate to another verified host before that date. Ubuntu 24.04 rejected
the SDK's UID-map setup in the first release run; a different host must pass
the same preflight and complete consumer qualification before being selected.

Both directories must be new. The recipe snapshots committed Git object bytes;
untracked files cannot enter the build or source archive. The isolated snapshot
carries its commit and per-file hashes, which packaging verifies again against
the system and SDK input records. Downloads are hash locked. glibc and GCC are
verified using their repository-pinned signing identities and current signature
checks before building. The recipe builds the C SDK, separate C++ SDK, profile,
application kit and system inside Preview 2, packages them, removes its packing
staging tree, then freshly extracts and validates the final archive with only
the consumer directory mounted. It publishes nothing itself.

The `Glibc SDK prerelease` GitHub Actions workflow runs only through an explicit
manual dispatch. Choose a new `xos-sdk-glibc-preview-N` tag. It refuses any
existing tag or release, rebuilds from the selected commit, and completes all
consumer validation before creating a draft. It uploads the fixed five-asset
set, verifies the uploaded names/sizes/SHA-256 digests, then publishes a prerelease without
marking it Latest. A failure leaves no public release; a failed upload can leave
an unpublished draft that must be reviewed before choosing another tag.
