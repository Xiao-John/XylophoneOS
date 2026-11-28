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

## Use the matching P0-R1 release bundle

The P0-R1 media and application kit have a separate qualification and package
profile from this host SDK. Its profile is `xos-x86_64-glibc-p0-20261128`, with
SHA-256 `437926bf43578493f38ea3c4834e98babebf797ef4e504a914dbbd93bdd9080d`,
and its system build is `7c8c59058be0b5f1`. Check the current delivery state in
the [publication receipt](p0_glibc_preview_3_delivery.json).

Once the R1 assets are available, download both
`p0-r1-glibc-release-20261128.tar` and its `.tar.sha256` file into the extracted
host SDK directory. The tar is 430,346,240 bytes, with SHA-256
`492c7b311431132398b84f62ff9357f516983039094559d41d4159e3e7e19ff4`.
From that directory, use a new consumer directory:

```sh
sha256sum -c p0-r1-glibc-release-20261128.tar.sha256
mkdir r1-consumer
tar -xf p0-r1-glibc-release-20261128.tar -C r1-consumer

./xos-sdk --workdir r1-consumer /bin/bash -c '
  set -eu
  cd /work/p0-r1-glibc-release-20261128
  sha256sum -c BUNDLE-CHECKSUMS.sha256
  sha256sum -c CHECKSUMS.sha256
  tar -xzf application-sdk.tar.gz
  tar -xzf images.tar.gz
  tar -xzf packages.tar.gz
  ./application-sdk/xos-app init r1_app --id example.r1 --language cpp
  ./application-sdk/xos-app build r1_app
  ./application-sdk/xos-app check r1_app
  ./application-sdk/xos-app pack r1_app --output r1_app.xpk
'
```

Use `--language c` for a C project. The result is an XPK bound to the R1
application profile. Keep the original archives and manifests together.
The explicit `application-sdk/xos-app` path selects R1's own profile and SDK;
the bare `xos-app` command selects the host SDK's independently built default
kit under `/opt/xos/glibc`. Their profiles are not interchangeable. Each wrapper
checks its recorded tool identities. Keep profile, sysroot, runtime libraries
and package disk as a matched set; do not edit their identities to force a match.

Start the R1 installer image and matching writable work disk with:

```sh
./xos-sdk --workdir r1-consumer \
  python3 /work/p0-r1-glibc-release-20261128/images/launch.py
```

This launcher uses `images/xos-install-dash.iso` and `images/work_disk.img`,
QEMU TCG and a serial console on the current terminal. It uses the extracted R1
media, not the host SDK's default ISO. Retain the original tar for a fresh disk;
the extracted work disk is writable. `images/launch.py --help` describes the
image-directory, QEMU and display options.

The R1 bundle contains component sources and five relink archives. The new
GCC 16.2.0 C++ runtime source archive, signature and public keyring accompany
the host SDK `*-sources.tar.zst` asset; R1's historical GNU Seed sources are not
a substitute. The [R1 release evidence](../reports/p0_release_final_20261128/README.md)
retains its qualification and exact bindings separately from the host SDK consumer.
SDK `SHA256SUMS` binds the original SDK assets; R1 has its own outer checksum
and the two checksum files inside its bundle.

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
marking it Latest. A failure before publication leaves no public release; a failed upload can leave
an unpublished draft that must be reviewed before choosing another tag.

### Recover an uploaded draft

If publication stopped after uploading the complete draft, dispatch the same
workflow with its exact tag and `recover_existing: true`. The default is false;
normal builds continue to refuse existing tags and releases.

Recovery accepts one prerelease draft with exactly the five SDK assets. It
downloads those original bytes with the authenticated release-asset API and
checks every API size/SHA-256, all four `SHA256SUMS` entries, package/qualification
bindings and the actual tag commit. Its source commit remains the original
artifact's commit even when the recovery workflow runs at a later revision.

A separate step, without a GitHub token, freshly extracts the downloaded binary
SDK and runs its installed C/C++ consumer smoke with only the empty consumer
directory mounted. The five downloaded files remain unchanged. A separate
recovery report records both the original source commit and the workflow commit.
The final step rechecks the remote draft, exact asset IDs/names/sizes/digests and
tag ref before publishing that numeric release ID. It does not rebuild the SDK,
move or create a tag, upload replacements or change the original qualification.
It also compares the publication response's assets and reads the tag again
before reporting success. These API calls are not an atomic transaction across
the release, assets and ref; a concurrent writer can still cause a post-publication
check to fail after the release has become public.

GitHub's [update-release permission rules](https://docs.github.com/en/rest/releases/releases#update-a-release)
can require workflow-write permission when the existing target commit changes
workflow files relative to the default branch. `GITHUB_TOKEN` cannot receive
that permission. If GitHub rejects publication, the workflow fails and leaves
the existing target, tag and assets untouched; it does not change the source
binding to avoid that restriction.
