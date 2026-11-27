import argparse, json, sys
from pathlib import Path
from tempfile import TemporaryDirectory
from glibc_release_packages_guest import boot, command
from glibc_release_xypm_relink import guest
from make_work_disk import create_fat32
from xypm_image import Disk
from xypm_format import sha_file

proof, old, release=map(Path,sys.argv[1:])
candidate=json.loads((release/'release_manifest.json').read_text())
original, replacement=old/'original.elf',old/'replacement.elf'
assert sha_file(original)==candidate['xypm_sha256']
assert sha_file(replacement)=='37d2a4b5540ea06672aafe4ce55f79266662f52fb142ba2f40e06ff50b78c622'
installer=release/'images/xos-install-dash.iso'
assert sha_file(installer)==candidate['installer_iso']['sha256']
with TemporaryDirectory(dir=proof) as folder:
    work=Path(folder)
    disk=work/'from_current_installer.img'
    create_fat32(disk,512)
    kit=boot(installer,disk,proof,'xypm_current_installer',candidate['system']['build_id'])
    try:
        command(kit,'sync',b'[files] sync=ok')
    finally:
        kit.close()
    with Disk(disk,work,read_only=True) as view:
        assert sha_file(view.export('/usr/bin/xypm'))==candidate['xypm_sha256']
    guest(argparse.Namespace(release=release,original=original,replacement=replacement,
                             installed_disk=disk,installed_disk_sha256=sha_file(disk),
                             output=proof/'xypm-current-guest'))
print('PASS current installer and ordinary release ISO')
