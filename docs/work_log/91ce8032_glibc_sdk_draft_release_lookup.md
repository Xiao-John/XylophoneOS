# glibc SDK draft release lookup

[Manual run 46110344041](https://github.com/Xiao-John/XylophoneOS/actions/runs/46110344041)
at source `8b2dee22a3272692603e9d01534c9b648375d04f` passed the Ubuntu 22.04
and Python 3.12 host preflight, authenticated GNU source builds, C/C++ SDK
composition, native system build, 10-item license audit and final-archive
consumer qualification. The installed SDK built and packed both applications,
then ran the package payloads in the supplied ISO; real-guest/resource checks
passed. The native system build ID was `4a379155cac2fbbf`.

The publication step checked all four entries in `SHA256SUMS`, created the
requested tag at that same source commit, and uploaded the five intended assets
to draft release `461317287`. It then failed with HTTP 404 while querying the
published-release-by-tag endpoint. The authenticated release collection and
numeric release endpoint can read this draft; the public tag endpoint cannot.
The run therefore remains failed at publication, despite successful building,
consumer qualification and uploads.

The workflow now queries the authenticated, paginated release collection for
the exact requested tag and requires one numeric ID. No match or multiple
matches fail the numeric-ID check. It then reads the raw release by ID, checks
the returned tag again, and retains the draft/prerelease, five-asset name/size/
SHA-256, actual Git ref and qualification-source checks before publishing.
It still creates a new tag atomically and never updates an existing tag or
overwrites an existing release. This fix does not rerun, delete or publish the
already uploaded draft.

Validation: YAML and all shell blocks parse; exact-tag selection was exercised
against the observed draft response, with empty and duplicate matches rejected.
The numeric release endpoint returned the same draft and all five uploaded
assets. The public evidence path scan is clean. The first run's local
`sha256sum -c` output recorded `OK` for each file, not digest values; independent
text-asset cross-checking remains a separate publication verification step.

## Explicit recovery of the original draft

The same workflow now offers a `recover_existing` boolean, default false.
Recovery reads the one matching prerelease draft and requires the fixed five
assets, then downloads their original bytes through the authenticated asset API.
It verifies all five server digests/sizes, the four checksum entries, package
and original qualification bindings, and the existing tag's actual source
commit. The recovery workflow commit is recorded separately from that source.

The fresh consumer helper now returns a report without changing input assets.
Recovery uses it in a token-free step to verify the downloaded SDK's file
manifest and actually build/package/run C and C++ again. It preserves the five
downloaded files and writes a separate recovery report. Before publishing by
numeric release ID, it hashes the originals again and re-reads the remote draft,
asset IDs/names/sizes/digests/states and tag ref. Any mismatch stops publication.
The recovery path never builds new SDK components or changes a tag or asset.
After the publication request it also compares the returned asset set and
rechecks the tag before reporting success. These separate API calls cannot
prevent all concurrent changes by another writer; a post-check failure means
the release may already be public and is not reported as verified success.

This path is intended to finish the already qualified `8b2dee22` draft, not to
bind those bytes to a newer source revision. The original failed run remains
the publication-failure record; the recovery run must supply its own real
consumer and publication results.

Recovery code checks passed locally: 14 unit tests exercise original-file
preservation, different artifact/workflow commits, API digest/checksum/source
mismatches, guest/resource failures, token rejection and remote asset/ref
changes before publication, changed assets in the publication response and a
changed tag after publication. YAML checks verify the default-false mode,
separate normal/recovery steps and token-free consumer step; all shell blocks
parse. The staged six-file public-path scan reports zero findings. These are
code/gate checks; the original draft's download and fresh consumer execution
still require the explicit recovery workflow run.

The documented update-release permission requirement for targets with workflow
differences remains an actual-run check: the recovery path uses `GITHUB_TOKEN`
and does not alter the old target or source identity to evade any permission
rejection.

## Workspace recovery

The local workspace was reset before the recovery changes reached the remote
repository. These six files were reconstructed from the retained code review
and the committed `6096eab` baseline, then checked again. This is a new
implementation revision; it does not claim restoration of the lost local Git
objects. The published SDK draft and its original source identity are unchanged.
