"""Build Aurora using the same SDK/Qt arguments as build_widgets_fixture.py."""
from pathlib import Path
import subprocess
import sys
import hashlib
import json

root = Path(__file__).resolve().parent
shell = root / 'shell'
subprocess.run([sys.executable, shell / 'prepare_assets.py'], check=True)
command = [sys.executable, root.parent / 'build_widgets_fixture.py',
           '--source', root / 'desktop_shell.cpp', '--resource-qrc', shell / 'shell.qrc']
for name in ('background', 'docker', 'applicationbrowser', 'windowedge', 'status'):
    command += ['--extra-source', shell / (name + '.cpp'), '--moc-header', shell / (name + '.h')]
subprocess.run([*command, *sys.argv[1:]], check=True)
output = Path(sys.argv[sys.argv.index('--output') + 1]).resolve()
receipt_path = output.with_suffix('.receipt.json')
receipt = json.loads(receipt_path.read_text())
receipt['inputs'].update({str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [Path(__file__), *shell.rglob('*')]
                         if p.is_file() and '__pycache__' not in p.parts})
receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
