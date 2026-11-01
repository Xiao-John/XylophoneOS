# SPDX-License-Identifier: Apache-2.0
"""C4 scrub: remove the leaked author home prefix from frozen docs evidence.

Proof-style, deterministic, fail-stop. Two passes over docs/:

Phase 1 (content scrub, applied to every docs file whose git-index blob
contains the needle):
  R1 payload : runtime-injected home prefix -> b"<author-home>"
  R2 tar hdr : uname/gname runtime-injected owner -> "author"
  R3 gz      : recompress deterministically (level 9, mtime=0, no FNAME,
               i.e. gzip -n semantics)

Phase 2 (sha256 cascade): files whose INDEX bytes bind the full 64-hex digest
of a rewritten file are updated to the final digest, processed in sink-first
topological order so every digest written is the FINAL digest of its target.
  R4 digest : boundary-checked 64-hex old -> final, inside docs/ only

Fail-stop conditions: a file in an unexpected state, a self-referencing
digest, a binding cycle, or ambiguous duplicate content. The username literal
is assembled from fragments so this file (under docs/) cannot defeat the
zero-hit grep gate.
"""
import base64
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"
REPORT_PREFIX = "docs/reports/perry_host_path_scrub_20261031/"
REPORT_DIR = ROOT / REPORT_PREFIX

# Archived copy: path material removed for the public-path guard (Issue #37).
# The original inline fragments are recorded in git history of this file.
PREFIX = os.environ.get("C4_SCRUB_PREFIX", "").encode()
OWNER = os.environ.get("C4_SCRUB_OWNER", "")
PREFIX_REPLACEMENT = b"<author-home>"
OWNER_REPLACEMENT = "author"
PREFIX_HEX = PREFIX.hex()
PREFIX_B64 = base64.b64encode(PREFIX).decode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gzip_deterministic(payload: bytes) -> bytes:
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", compresslevel=9,
                       mtime=0, filename="") as gz:
        gz.write(payload)
    return out.getvalue()


def is_gzip(data: bytes) -> bool:
    return data[:2] == b"\x1f\x8b"


def try_tar_members(payload: bytes):
    try:
        t = tarfile.open(fileobj=io.BytesIO(payload), mode="r:")
        members = t.getmembers()
        return members if members else None
    except Exception:
        return None


def tar_payloads(payload: bytes):
    t = tarfile.open(fileobj=io.BytesIO(payload), mode="r:")
    for m in t.getmembers():
        if m.isfile():
            yield t.extractfile(m).read()


def payloads(raw: bytes):
    """All searchable byte surfaces of a docs file."""
    yield raw
    if is_gzip(raw):
        try:
            dec = gzip.decompress(raw)
        except Exception:
            return
        yield dec
        if try_tar_members(dec):
            yield from tar_payloads(dec)


def scrub_blob(raw: bytes):
    """Phase-1 transform of one file's raw bytes. Returns
    (new_raw, kind, hits_payload, hits_owner, rules)."""
    if is_gzip(raw):
        dec = gzip.decompress(raw)
        members = try_tar_members(dec)
        if members is not None:
            hits_c = sum(m.count(PREFIX) for m in tar_payloads(dec))
            hits_o = sum(1 for m in members
                         if OWNER in ((m.uname or "").encode() +
                                      (m.gname or "").encode()))
            if not (hits_c or hits_o):
                return raw, "tar.gz", 0, 0, []
            src = tarfile.open(fileobj=io.BytesIO(dec), mode="r:")
            out_tar = io.BytesIO()
            with tarfile.open(fileobj=out_tar, mode="w",
                              format=tarfile.GNU_FORMAT) as dst:
                for member in src.getmembers():
                    new = tarfile.TarInfo(member.name)
                    new.mtime, new.mode = int(member.mtime), member.mode
                    new.type, new.linkname = member.type, member.linkname
                    new.uid, new.gid = member.uid, member.gid
                    new.uname, new.gname = member.uname, member.gname
                    if (member.uname or "").encode() == OWNER:
                        new.uname = OWNER_REPLACEMENT
                    if (member.gname or "").encode() == OWNER:
                        new.gname = OWNER_REPLACEMENT
                    if member.isfile():
                        data = src.extractfile(member).read()
                        data = data.replace(PREFIX, PREFIX_REPLACEMENT)
                        new.size = len(data)
                        dst.addfile(new, io.BytesIO(data))
                    else:
                        new.size = 0
                        dst.addfile(new)
            rules = []
            if hits_c:
                rules.append("R1")
            if hits_o:
                rules.append("R2")
            return gzip_deterministic(out_tar.getvalue()), "tar.gz", hits_c, hits_o, rules
        hits = dec.count(PREFIX)
        if not hits:
            return raw, "gz", 0, 0, []
        new_dec = dec.replace(PREFIX, PREFIX_REPLACEMENT)
        return gzip_deterministic(new_dec), "gz", hits, 0, ["R1", "R3"]
    hits = raw.count(PREFIX)
    if not hits:
        return raw, "text", 0, 0, []
    return raw.replace(PREFIX, PREFIX_REPLACEMENT), "text", hits, 0, ["R1"]


def index_blobs():
    """path -> git index blob bytes for every tracked docs file."""
    out = {}
    listing = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "docs"], cwd=ROOT)
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        path = entry.decode()
        out[path] = subprocess.check_output(["git", "show", ":" + path],
                                            cwd=ROOT)
    return out


def main() -> int:
    blobs = index_blobs()
    report_dir_rel = REPORT_PREFIX

    # ---------- Phase 1 ----------
    changed = {}      # rel -> record
    final_sha = {}    # rel -> final sha256 (updated again in phase 2)
    node_old = {}     # rel -> pre-scrub (index) sha256
    for rel in sorted(blobs):
        if rel.startswith(report_dir_rel):
            continue
        index_raw = blobs[rel]
        new_raw, kind, hits_c, hits_o, rules = scrub_blob(index_raw)
        if new_raw == index_raw:
            continue
        current = (ROOT / rel).read_bytes()
        if current != new_raw:
            if current == index_raw:
                (ROOT / rel).write_bytes(new_raw)
            else:
                print(f"FAIL-STOP: {rel} in unexpected state "
                      f"(index {sha256(index_raw)[:12]}, "
                      f"current {sha256(current)[:12]}, "
                      f"expected {sha256(new_raw)[:12]})")
                return 1
        node_old[rel] = sha256(index_raw)
        final_sha[rel] = sha256(new_raw)
        if kind != "text":
            rules = sorted(set(rules) | {"R3"})
        changed[rel] = {"path": rel, "old_sha256": node_old[rel],
                        "new_sha256": final_sha[rel], "kind": kind,
                        "hits": hits_c + hits_o, "rules": rules}

    # ---------- Phase 2a: closure over INDEX bytes ----------
    surfaces_cache = {rel: list(payloads(blobs[rel])) for rel in blobs}
    for _round in range(10):
        digest_to_paths = {}
        for p, s in node_old.items():
            digest_to_paths.setdefault(s, []).append(p)
        alts = b"|".join(re.escape(s.encode()) for s in sorted(digest_to_paths))
        pat = re.compile(rb"(?<![0-9a-f])(" + alts + rb")(?![0-9a-f])")
        discovered = {}
        for rel in sorted(blobs):
            if rel.startswith(report_dir_rel) or rel in node_old:
                continue
            for pl in surfaces_cache[rel]:
                for m in pat.finditer(pl):
                    for target in digest_to_paths[m.group(1).decode()]:
                        discovered.setdefault(rel, set()).add(target)
        if not discovered:
            break
        for rel in discovered:
            node_old[rel] = sha256(blobs[rel])

    # edges from index bytes (binder -> bound target)
    digest_to_paths = {}
    for p, s in node_old.items():
        digest_to_paths.setdefault(s, []).append(p)
    alts = b"|".join(re.escape(s.encode()) for s in sorted(digest_to_paths))
    pat = re.compile(rb"(?<![0-9a-f])(" + alts + rb")(?![0-9a-f])")
    edges = {p: set() for p in node_old}
    for rel in sorted(node_old):
        if rel.startswith(report_dir_rel):
            continue
        for pl in surfaces_cache[rel]:
            for m in pat.finditer(pl):
                for target in digest_to_paths[m.group(1).decode()]:
                    if target == rel:
                        print(f"FAIL-STOP: self-referencing digest: {rel}")
                        return 1
                    edges[rel].add(target)

    color = {p: 0 for p in edges}
    cycles = []

    def dfs(u, stack):
        color[u] = 1
        for v in sorted(edges[u]):
            if color[v] == 1:
                cycles.append(stack[stack.index(v):] + [v])
            elif color[v] == 0:
                dfs(v, stack + [v])
        color[u] = 2

    for p in sorted(edges):
        if color[p] == 0:
            dfs(p, [p])
    if cycles:
        print("FAIL-STOP: binding cycles:", cycles)
        return 1

    order = []
    seen = set()

    def post(u):
        for v in sorted(edges[u]):
            if v not in seen:
                post(v)
        if u not in seen:
            seen.add(u)
            order.append(u)

    for p in sorted(edges):
        post(p)

    # ---------- Phase 2b: apply sink-first ----------
    cascade = []
    for rel in order:
        targets = sorted(edges[rel])
        if not targets:
            continue
        repl = {}
        for t in targets:
            digest = node_old[t]
            value = final_sha[t]
            if digest in repl and repl[digest] != value:
                print(f"FAIL-STOP: ambiguous duplicate digest in {rel}: {digest}")
                return 1
            repl[digest] = value
        d_alts = b"|".join(re.escape(d.encode()) for d in sorted(repl))
        d_pat = re.compile(rb"(?<![0-9a-f])(" + d_alts + rb")(?![0-9a-f])")
        current = (ROOT / rel).read_bytes()
        if is_gzip(current):
            dec = gzip.decompress(current)
            new_dec, n = d_pat.subn(lambda m: repl[m.group(1).decode()].encode(), dec)
            if not n:
                print(f"FAIL-STOP: {rel} expected digest hits, found none")
                return 1
            new_raw = gzip_deterministic(new_dec)
        else:
            new_raw, n = d_pat.subn(lambda m: repl[m.group(1).decode()].encode(), current)
        (ROOT / rel).write_bytes(new_raw)
        final_sha[rel] = sha256(new_raw)
        if rel in changed:
            changed[rel]["rules"] = sorted(set(changed[rel]["rules"]) | {"R4"})
            changed[rel]["new_sha256"] = final_sha[rel]
            changed[rel]["cascade_replacements"] = n
        else:
            cascade.append({"path": rel, "old_sha256": node_old[rel],
                            "new_sha256": final_sha[rel], "hits": 0,
                            "rules": ["R4"], "replacements": n,
                            "kind": "gz" if is_gzip(new_raw) else "text"})

    # ---------- Verification ----------
    residual = {"prefix": {}, "owner": {}, "digest": {}}
    d_all = re.compile(rb"(?<![0-9a-f])(" + b"|".join(
        re.escape(s.encode()) for s in sorted(node_old)) + rb")(?![0-9a-f])")
    for dirpath, _d, files in os.walk(DOCS):
        for name in sorted(files):
            path = Path(dirpath) / name
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(report_dir_rel):
                continue
            raw = path.read_bytes()
            surfaces = list(payloads(raw))
            np = max(s.count(PREFIX) for s in surfaces)
            no = max(s.count(OWNER) for s in surfaces)
            nd = sum(len(d_all.findall(s)) for s in surfaces)
            if np:
                residual["prefix"][rel] = np
            if no:
                residual["owner"][rel] = no
            if nd:
                residual["digest"][rel] = nd

    manifest = {
        "title": "C4 host-path scrub of frozen docs evidence",
        "date": "2026-10-31",
        "authorization": "user-approved clearing of the leaked author home path",
        "rule": {
            "find_hex": PREFIX_HEX,
            "find_b64": PREFIX_B64,
            "replace": PREFIX_REPLACEMENT.decode(),
            "tar_owner_field": {"replace": OWNER_REPLACEMENT},
            "gz": "recompress level=9 mtime=0 no-FNAME (gzip -n)",
            "digest_cascade": "R4: boundary-checked 64-hex old->final",
        },
        "scope": "docs/ working tree; git history objects untouched "
                 "(docs/history provenance reads git objects, not worktree)",
        "old_sha256_source": "git index blobs (git show :<path>)",
        "files": [changed[p] for p in sorted(changed)],
        "cascade_updates": cascade,
        "verification": {
            "changed_files": len(changed),
            "cascade_only_files": len(cascade),
            "closure_nodes": len(node_old),
            "residual_prefix_hits": residual["prefix"],
            "residual_owner_hits": residual["owner"],
            "residual_old_digest_hits": residual["digest"],
        },
    }
    (REPORT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps(manifest["verification"], indent=1))
    if any(residual.values()):
        print("FAIL-STOP: residual hits remain")
        return 1
    print(f"OK: {len(changed)} files scrubbed, {len(cascade)} binder-only files "
          f"cascade-updated, closure {len(node_old)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
