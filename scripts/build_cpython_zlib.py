# SPDX-License-Identifier: Apache-2.0
"""Build a pinned static zlib for the CPython XOS cross build."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile

from glibc_g1_probe import clean_build_environment, select_gnu_make, tool_identity
from xypm_format import load_json, require, sha_file
from xypm_sdk_profile import metadata_snapshot, relative_file, verify_profile


ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "src/ports/cpython"
DEFAULT_ARCHIVE = ROOT / ".cache/xos_seed/cpython/sources/zlib-1.3.2.tar.xz"
DEFAULT_SDK = ROOT / "build/threading_sdk"
GLIBC_ARTIFACTS = ('include/zlib.h', 'include/zconf.h', 'lib/libz.a')
GLIBC_PROBE_PATCH = PORT / 'zlib_patches/0002_glibc_probe_libraries.patch'


def glibc_zlib_binding(prefix, sdk_binding, sdk_digest, profile_digest):
    prefix = prefix.resolve(strict=True)
    report, report_digest = metadata_snapshot(prefix.parent / 'report.json')
    lock = load_json(PORT / 'zlib_lock.json')
    require(prefix.name == 'prefix' and report['status'] == 'built' and report['runtime_family'] == 'glibc'
            and report['version'] == lock['version'] and report['source_archive_sha256'] == lock['sha256']
            and report['license_sha256'] == lock['license_sha256'] and report['sdk_binding'] == sdk_binding
            and report['sdk_manifest_sha256'] == sdk_digest and report['profile_file_sha256'] == profile_digest
            and report['inputs']['build_script_sha256'] == sha_file(__file__)
            and report['inputs']['zlib_lock_sha256'] == sha_file(PORT / 'zlib_lock.json')
            and report['inputs']['xos_patch_sha256'] == sha_file(PORT / 'zlib_patches/0001_xos_errno_header.patch')
            and report['inputs']['glibc_probe_patch_sha256'] == sha_file(GLIBC_PROBE_PATCH)
            and report['configure_checks']['vsnprintf'] is True,
            'zlib build is not bound to the selected static glibc SDK and source lock')
    artifacts = {name: sha_file(relative_file(prefix, name)) for name in GLIBC_ARTIFACTS}
    require(artifacts == {'include/' + name: digest for name, digest in report['header_sha256'].items()}
            | {'lib/libz.a': report['libz_sha256']}, 'zlib build artifacts changed')
    return {'version': lock['version'], 'source_archive_sha256': lock['sha256'],
            'license_sha256': lock['license_sha256'], 'build_receipt_sha256': report_digest,
            'builder_sha256': sha_file(__file__), 'configure_checks': report['configure_checks'],
            'artifacts': artifacts}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def executable(name):
    value = shutil.which(name)
    if value is None:
        raise FileNotFoundError(f"required cross tool not found: {name}")
    return value


def run(command, *, cwd, env, log):
    with Path(log).open("w") as stream:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, command)


def extract_source(archive, destination, expected_root):
    destination.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        roots = {Path(member.name).parts[0] for member in bundle.getmembers() if member.name}
        if roots != {expected_root}:
            raise ValueError(f"unexpected zlib archive roots: {sorted(roots)}")
        for member in bundle.getmembers():
            parts = Path(member.name).parts
            if not parts or Path(member.name).is_absolute() or ".." in parts:
                raise ValueError(f"unsafe archive member: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"archive link not admitted: {member.name}")
            relative = parts[1:]
            if not relative:
                continue
            target = destination.joinpath(*relative)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                source = bundle.extractfile(member)
                if source is None:
                    raise ValueError(f"archive member has no data: {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
            else:
                raise ValueError(f"unsupported archive member: {member.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    parser.add_argument('--glibc-profile', type=Path, help='bind an explicit static glibc SDK profile')
    parser.add_argument('--output-dir', type=Path, help='new isolated zlib build directory')
    args = parser.parse_args()

    archive = args.archive.resolve(strict=True)
    sdk = args.sdk.resolve(strict=True)
    lock = json.loads((PORT / "zlib_lock.json").read_text())
    archive_hash = sha256(archive)
    license_hash = sha256(PORT / "upstream/zlib-LICENSE")
    if archive_hash != lock["sha256"]:
        parser.error("zlib archive SHA-256 does not match zlib_lock.json")
    if license_hash != lock["license_sha256"]:
        parser.error("zlib license hash does not match zlib_lock.json")

    cc = os.environ.get("XOS_CC") or executable("x86_64-elf-gcc")
    ar = os.environ.get("XOS_AR") or executable("x86_64-elf-ar")
    ranlib = os.environ.get("XOS_RANLIB") or executable("x86_64-elf-ranlib")
    sdk_manifest = sdk / "manifest.json"
    sdk_hash = sha256(sdk_manifest)
    glibc = {}
    env = dict(os.environ)
    make = 'make'
    arflags = 'rc'
    ranlib_command = ranlib
    cflags = ['-O2', '-mno-red-zone', '-fno-pie', '-fno-pic', '-fno-stack-protector',
              '-ffunction-sections', '-fdata-sections', '-D__xos__=1']
    if args.glibc_profile:
        profile, profile_digest = metadata_snapshot(args.glibc_profile)
        binding = verify_profile(profile, 'glibc', sdk)
        metadata, _ = metadata_snapshot(sdk_manifest, profile['sdk_binding']['sdk_manifest_sha256'])
        tools = {name: tool_identity('x86_64-elf-' + name) for name in ('gcc', 'ar', 'ranlib')}
        for name, tool in tools.items():
            require(tool.get('available') and tool['sha256'] == metadata['tools']['x86_64-elf-' + name]['sha256'],
                    'zlib cross tool differs from the SDK build: ' + name)
        cc, ar, ranlib = (tools[name]['path'] for name in ('gcc', 'ar', 'ranlib'))
        env, _ = clean_build_environment(os.environ)
        env.update(CHOST='x86_64-elf', LC_ALL='C')
        make = select_gnu_make()['path']
        arflags = 'rcD'
        ranlib_command = shlex.join([ranlib, '-D'])
        sysroot = sdk / 'sysroot'
        cflags.extend(['--sysroot=' + str(sysroot), '-nostdinc', '-isystem', str(sysroot / 'usr/include'),
                       '-isystem', str(sysroot / 'usr/lib/compiler-include')])
        lib = sysroot / 'usr/lib'
        start = ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o')
        end = ('crtend.o', 'crtn.o')
        archives = ['libc.a', 'libm.a']
        archives.extend(name for name in ('libxos_terminal.a', 'libgcc.a', 'libgcc_eh.a') if (lib / name).is_file())
        env['LDFLAGS'] = shlex.join(['-nostdlib', '-static', '-no-pie', '-T', str(sysroot / 'user.ld'),
                                     '-Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096'])
        env['LIBS'] = shlex.join([*[str(lib / name) for name in start], '-Wl,--start-group',
                                  *[str(lib / name) for name in archives], '-Wl,--end-group',
                                  *[str(lib / name) for name in end]])
        glibc = {'runtime_family': 'glibc', 'sdk_binding': binding, 'profile_file_sha256': profile_digest,
                 'tool_sha256': {name: tool['sha256'] for name, tool in tools.items()}}
    else:
        cflags.extend(['-isystem', str(sdk / 'include')])
    fingerprint_inputs = {
        "archive_sha256": archive_hash,
        "build_script_sha256": sha256(__file__),
        "cc": cc,
        "ar": ar,
        "ranlib": ranlib,
        "sdk_manifest_sha256": sdk_hash,
        "zlib_lock_sha256": sha256(PORT / "zlib_lock.json"),
        "xos_patch_sha256": sha256(PORT / "zlib_patches/0001_xos_errno_header.patch"),
        **({'glibc_probe_patch_sha256': sha_file(GLIBC_PROBE_PATCH)} if glibc else {}),
        **glibc,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_inputs, sort_keys=True).encode()
    ).hexdigest()[:20]
    work = args.output_dir.resolve() if args.output_dir else ROOT / ".cache/xos_seed/cpython/zlib" / fingerprint
    require(not work.is_relative_to(sdk) and not work.is_relative_to(PORT), 'zlib output must be outside build inputs')
    if work.exists():
        report_path = work / "report.json"
        if args.output_dir is None and report_path.is_file():
            report = json.loads(report_path.read_text())
            if report.get("status") == "built" and report.get("fingerprint") == fingerprint:
                print(json.dumps(report, indent=2, sort_keys=True))
                if glibc:
                    glibc_zlib_binding(work / 'prefix', binding, sdk_hash, profile_digest)
                return
        raise FileExistsError(f"partial zlib work directory exists; inspect it: {work}")

    work.mkdir(parents=True)
    source = work / "source"
    build = work / "target_build"
    prefix = work / "prefix"
    build.mkdir()
    extract_source(archive, source, f"zlib-{lock['version']}")

    env.update(
        CC=cc,
        AR=ar,
        RANLIB=ranlib_command,
        CFLAGS=shlex.join(cflags),
    )
    run(
        [
            "patch", "-p1", "--forward", "-i",
            str(PORT / "zlib_patches/0001_xos_errno_header.patch"),
        ],
        cwd=source,
        env=env,
        log=work / "patch.log",
    )
    report = {
        "phase": "PY3-A2-zlib",
        "status": "build_started",
        "version": lock["version"],
        "fingerprint": fingerprint,
        "inputs": fingerprint_inputs,
        "source_archive_sha256": archive_hash,
        "license_sha256": license_hash,
        "sdk_path": str(sdk),
        "sdk_manifest_sha256": sdk_hash,
        "prefix": str(prefix),
        **glibc,
    }
    try:
        if glibc:
            run(['patch', '-p1', '--forward', '-i', str(GLIBC_PROBE_PATCH)], cwd=source, env=env,
                log=work / 'glibc_probe_patch.log')
        run(
            ["/bin/sh", str(source / "configure"), "--static", f"--prefix={prefix}"],
            cwd=build,
            env=env,
            log=work / "configure.log",
        )
        if glibc:
            configure = (work / 'configure.log').read_text()
            report['configure_checks'] = {
                'strerror': 'Checking for strerror... Yes.' in configure,
                'vsnprintf': 'Checking for vsnprintf() in stdio.h... Yes.' in configure,
            }
            require(report['configure_checks']['vsnprintf'], 'glibc zlib requires a working bounded vsnprintf')
        run(
            [make, "-j2", f"AR={ar}", f"ARFLAGS={arflags}", f"RANLIB={ranlib_command}", "libz.a"],
            cwd=build,
            env=env,
            log=work / "make.log",
        )
        include = prefix / "include"
        library = prefix / "lib"
        include.mkdir(parents=True)
        library.mkdir(parents=True)
        shutil.copyfile(source / "zlib.h", include / "zlib.h")
        shutil.copyfile(build / "zconf.h", include / "zconf.h")
        shutil.copyfile(build / "libz.a", library / "libz.a")
        archive_members = subprocess.check_output(
            [ar, "t", str(library / "libz.a")], text=True
        ).splitlines()
        if len(archive_members) < 10 or (library / "libz.a").stat().st_size < 1000:
            raise ValueError("libz.a does not contain the expected object members")
        if glibc:
            require(sha_file(archive) == archive_hash and sha_file(sdk_manifest) == sdk_hash
                    and sha_file(args.glibc_profile) == profile_digest
                    and verify_profile(profile, 'glibc', sdk) == binding
                    and all(sha_file(tool['path']) == tool['sha256'] for tool in tools.values()),
                    'zlib source, glibc SDK or cross tools changed during compilation')
        report.update({
            "status": "built",
            "header_sha256": {
                "zlib.h": sha256(include / "zlib.h"),
                "zconf.h": sha256(include / "zconf.h"),
            },
            "libz_sha256": sha256(library / "libz.a"),
            "libz_bytes": (library / "libz.a").stat().st_size,
            "libz_members": archive_members,
        })
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        (work / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        raise
    (work / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
