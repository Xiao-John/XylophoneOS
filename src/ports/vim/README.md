# Vim source identity and dependency inventory

`source_lock.json` pins Vim 9.1.0000 and the hash of a locally generated
`git archive --format=tar HEAD`. This is a source identity, not a GitHub
release tarball hash or an accepted target build. See [dependency inventory](DEPENDENCIES.md)
and [the Vim plan](../../../docs/plans/vim.md). The upstream license is
retained in `LICENSE.upstream`; bundled member review and the full target
feature matrix remain open. This old baseline does not claim current fixes.
