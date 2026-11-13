# 定向验证重放说明

本文保留本次审计的五份一次性宿主验证脚本完整内容，供临时审计目录消失后复核。它们是审计证据，不新增生产脚本、构建流程或客体验收入口。问题编号对应[综合审计报告](README.md)。

## 运行边界

从**仓库根目录**执行下列代码块。每段独立运行，使用本仓库现有 Python、Git 和真实源码；不下载依赖、不安装工具。审计使用 CPython 3.12；B10 检查 Python 字节码，换解释器版本时若指令名改变，应先核对实际字节码，不能直接宣称产品回归。不要使用 `python -O`，这些检查依赖 `assert`。

所有需要旧实现对照的脚本固定读取基线 **`e6246faf8eefac305a99528f727b1592ee93a5b2`**，不随 `HEAD` 移动。如果当前克隆缺少该提交，应取得对应历史对象后再重放；不能换成另一个提交来让断言通过。当前实现从工作树读取，因此须应用本次对应修复后才能预期通过。未来实现结构改变时，AST 选择器可能失效，应重新审阅源码。

输出统一写入 `build/comprehensive_audit_replay/`，临时 fixture 在该目录中创建并清理。代码不会更新冻结报告或生产输入。B11 运行的是当前真实脚本的逐字副本和冻结锁的副本，二者放入临时仓库目录结构，并在执行后核对副本及原锁摘要。以下结果都**不是 Qt 全构建、QEMU 启动、真实 guest 编译或设备隔离资格**。

| 问题 | 原一次性脚本 | 实际证据范围 |
| --- | --- | --- |
| B08、B09、B10 | `verify_script_repairs.py` | 实际 receipt 序列化语句、Ninja 平台分支、`scenarios` 字节码作用域 |
| B07、B11 | `verify_failure_paths.py` | 真实构建失败入口、冻结锁拒绝入口 |
| B21 | `verify_ui_media_selection.py` | 实际复制路径赋值、Guest 后缀选择、QEMU 命令生成 |
| B24 | `verify_ui_runner_provenance.py` | 五个 runner 的实际来源记录循环、路径和 SHA-256 |
| B28、B29 | `verify_e08_post5_contract.py` | 实际参数入口、压力源生成表达式和报告文本 |
| B20 | 原证据为源码流程及语法复核，见文末 | 可选 probe 未运行时的记录位置；没有 guest 运行证据 |

## 1. B08 / B09 / B10：receipt、平台依赖和变量作用域

[Qt fixture 构建脚本](../../../src/ports/qt6/build_widgets_fixture.py)、[Qt configure 脚本](../../../src/ports/qt6/configure_widgets.py)、[P4A 运行器](../../../scripts/run_ssg_p4a_validation.py)。

执行真实 AST 语句，不执行完整构建脚本。预期 receipt 的四个追加输入由绝对路径变为模板路径；POSIX 保留 depfile / deps，Windows 保留原 workaround；P4A 读取模块级 `scenarios`。这里的两条平台分支是在宿主中对实际语句分别传入平台名，不代表已经在两种操作系统完整构建 Qt。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import ast
import dis
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace

root = Path.cwd()
BASELINE = 'e6246faf8eefac305a99528f727b1592ee93a5b2'
out = root / 'build/comprehensive_audit_replay'
out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(root / 'scripts'))
from ssg_public_paths import portable


def source(path, original=False):
    if original:
        return subprocess.check_output(['git', 'show', BASELINE + ':' + path], cwd=root, text=True)
    return (root / path).read_text()


def serialization(path, original, scratch):
    tree = ast.parse(source(path, original), filename=path)
    statements = []
    for statement in tree.body:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            call = statement.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == 'update' and ast.unparse(call.func.value) == "receipt['inputs']":
                statements.append(statement)
        elif isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'mappings' for target in statement.targets):
            statements.append(statement)
        elif isinstance(statement, ast.If) and ast.unparse(statement.test) == 'a.portable_receipt':
            statements.append(statement)
    generated = scratch / 'generated.cpp'
    qrc = scratch / 'shell.qrc'
    generated.write_text('generated receipt input\n')
    qrc.write_text('<RCC/>\n')
    values = {'receipt': {'inputs': {}, 'commands': []}, 'portable': portable,
              'sha': lambda path: hashlib.sha256(path.read_bytes()).hexdigest(), 'sys': sys,
              'sdk': scratch / 'sdk', 'qt': scratch / 'qt', 'qs': scratch / 'source',
              'host': scratch / 'host', 'binutils': scratch / 'binutils', 'out': scratch / 'probe.elf',
              'cxx': str(scratch / 'g++'), 'ar': str(scratch / 'ar'),
              'a': SimpleNamespace(portable_receipt=True,
                    extra_source=[root / 'src/ports/qt6/aurora/shell/background.cpp'],
                    moc_header=[root / 'src/ports/qt6/aurora/shell/background.h'],
                    resource_qrc=[qrc]), 'additional_sources': [generated]}
    exec(compile(ast.Module(body=statements, type_ignores=[]), path, 'exec'), values)
    return list(values['receipt']['inputs'])


with tempfile.TemporaryDirectory(prefix='script_repairs_', dir=out) as temporary:
    scratch = Path(temporary)
    before = serialization('src/ports/qt6/build_widgets_fixture.py', True, scratch)
    after = serialization('src/ports/qt6/build_widgets_fixture.py', False, scratch)
    assert len(before) == len(after) == 4
    assert all(Path(path).is_absolute() for path in before)
    assert all(path.startswith('${XOS_') for path in after)

    path = 'src/ports/qt6/configure_widgets.py'
    tree = ast.parse(source(path), filename=path)
    block = next(node for node in tree.body if isinstance(node, ast.If) and ast.unparse(node.test) == "os.name == 'nt'")
    for platform in ('posix', 'nt'):
        build = scratch / platform
        (build / 'CMakeFiles').mkdir(parents=True)
        ninja = build / 'build.ninja'
        rules = build / 'CMakeFiles/rules.ninja'
        deps = build / '.ninja_deps'
        fixture = 'rule compiler\n  depfile = $DEP_FILE\n  deps = gcc\n  command = g++\n'
        ninja.write_text(fixture)
        rules.write_text(fixture)
        deps.write_bytes(b'fixture')
        values = {'os': SimpleNamespace(name=platform), 'ninja_file': ninja,
                  'build': build, 'a': SimpleNamespace(build=build), 're': re}
        exec(compile(ast.Module(body=[block], type_ignores=[]), path, 'exec'), values)
        if platform == 'posix':
            assert ninja.read_text() == rules.read_text() == fixture and deps.exists()
        else:
            assert 'depfile =' not in ninja.read_text() and 'deps = gcc' not in rules.read_text() and not deps.exists()

path = 'scripts/run_ssg_p4a_validation.py'
codes = []
for original in (True, False):
    module = compile(source(path, original), path, 'exec')
    main = next(value for value in module.co_consts if isinstance(value, type(module)) and value.co_name == 'main')
    codes.append([(instruction.opname, instruction.argval) for instruction in dis.get_instructions(main) if instruction.argval == 'scenarios'])
assert ('LOAD_FAST', 'scenarios') in codes[0]
assert not any(name.startswith('STORE_FAST') for name, value in codes[1])
assert ('LOAD_GLOBAL', 'scenarios') in codes[1]
report = {'baseline': BASELINE, 'scope': 'actual serialization/dependency-rewrite statements and Python bytecode; no Qt build or guest execution',
          'portable_receipt_inputs': {'before_absolute': len(before), 'after_portable': len(after)},
          'dependency_rewrite': ['posix_kept', 'windows_workaround_kept'],
          'p4a_scenarios': {'before': codes[0], 'after': codes[1]}}
(out / 'script_repairs_check.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS: actual receipt statements; two dependency-rewrite paths; P4A variable scope')
PY
```

## 2. B07 / B11：真实失败入口

[SSG P1 构建脚本](../../../scripts/build_ssg_p1.py)、[来源抓取脚本](../../../scripts/modern_apps_sources.py)。

B07 只在 `x86_64-elf-g++` **确实不在 PATH** 时适用。已安装的机器记录 `NOT_RUN`，继续 B11；无需卸载、重命名编译器或改 PATH。本次审计环境满足缺编译器条件，期望子进程退出 1，产出的 manifest 为 `FAILED`，错误精确指向缺少工具。临时 SDK manifest 和 Qt cache 只用于抵达真实缺工具入口，不能证明 SDK 或 Qt 可用。

B11 在临时目录运行当前来源脚本的原样副本，冻结锁也为原文件副本；期望在创建 sources 目录和网络抓取前拒绝，副本和仓库原锁摘要均保持不变。不要改成运行基线中的未修复抓取器，也不要删除冻结锁以绕过拒绝入口。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path.cwd()
out = root / 'build/comprehensive_audit_replay'
out.mkdir(parents=True, exist_ok=True)

if shutil.which('x86_64-elf-g++') is not None:
    failure = {'check_status': 'NOT_RUN',
               'reason': 'x86_64-elf-g++ is available; missing-tool precondition is absent'}
else:
    with tempfile.TemporaryDirectory(prefix='p1_failure_', dir=out) as temporary:
        scratch = Path(temporary)
        values = {name: scratch / name for name in
                  ('sdk', 'qt-build', 'qt-source', 'host-qt', 'binutils')}
        for path in values.values():
            path.mkdir()
        (values['sdk'] / 'manifest.json').write_text('{}\n')
        (values['qt-build'] / 'CMakeCache.txt').write_text('audit fixture\n')
        command = [sys.executable, 'scripts/build_ssg_p1.py']
        for name, path in values.items():
            command.extend(['--' + name, str(path)])
        output = scratch / 'output'
        command.extend(['--output', str(output)])
        result = subprocess.run(command, cwd=root, text=True, capture_output=True)
        manifest = json.loads((output / 'manifest.json').read_text())
        assert result.returncode == 1
        assert manifest['status'] == 'FAILED'
        assert manifest['error'] == "FileNotFoundError('missing tool: x86_64-elf-g++')"
        failure = {'check_status': 'PASSED', 'returncode': result.returncode,
                   'manifest_status': manifest['status'], 'error': manifest['error']}

lock_path = Path('docs/reports/modern_apps_20261029/source_lock.json')
lock = root / lock_path
before = hashlib.sha256(lock.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='frozen_lock_', dir=out) as temporary:
    mirror = Path(temporary)
    script = mirror / 'scripts/modern_apps_sources.py'
    script.parent.mkdir(parents=True)
    shutil.copyfile(root / 'scripts/modern_apps_sources.py', script)
    mirrored_lock = mirror / lock_path
    mirrored_lock.parent.mkdir(parents=True)
    shutil.copyfile(lock, mirrored_lock)
    result = subprocess.run([sys.executable, str(script)], cwd=mirror,
                            text=True, capture_output=True)
    assert result.returncode == 1
    assert 'source lock already frozen' in result.stderr
    assert hashlib.sha256(mirrored_lock.read_bytes()).hexdigest() == before
    assert not (mirror / 'build/modern_apps/sources').exists()
after = hashlib.sha256(lock.read_bytes()).hexdigest()
assert before == after
report = {'p1_failure': failure,
          'modern_frozen_source_lock': {'check_status': 'PASSED',
              'returncode': result.returncode, 'lock_unchanged': before == after,
              'lock_sha256': after},
          'scope': 'actual failure entry points; source-lock command uses an unchanged script and lock copy in a temporary repository shape; no compiler or network fetch'}
(out / 'failure_paths_check.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
PY
```

## 3. B21：镜像后缀和实际命令选择

四个 runner：[fault probe](../../../tests/qt6_fault_probe.py)、[file errors](../../../tests/qt6_file_errors.py)、[persist probe](../../../tests/qt6_persist_probe.py)、[SDK probe](../../../tests/qt6_sdk_probe.py)。另外执行 [Guest](../../../tests/boot_smoke.py) 的实际介质选择语句和 [qemu_command](../../../scripts/run_qemu.py)。

每个 runner 检查 `.iso`、`.ISO`、`.img` 和无后缀，共 **16 个当前用例、16 个基线对照用例**。原实现全部选 floppy，其中 8 个 ISO 用例错误；修复后 ISO 选 cdrom，其余保持 floppy。`QEMU` 在该独立 Python 进程内指向已存在的 Python 可执行文件，仅满足命令生成器的可执行路径查找；**不会执行生成的命令，也不启动 Python 来冒充 QEMU**。没有要求本机安装 QEMU，输入镜像路径也只用于路径计算。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
from types import SimpleNamespace
import ast
import json
import os
import subprocess
import sys

ROOT = Path.cwd()
BASELINE = 'e6246faf8eefac305a99528f727b1592ee93a5b2'
OUT = ROOT / 'build/comprehensive_audit_replay'
OUT.mkdir(parents=True, exist_ok=True)
# Only qemu_command is called; this executable is never started.
os.environ['QEMU'] = sys.executable
sys.path.insert(0, str(ROOT / 'scripts'))
from run_qemu import qemu_command

paths = [f'tests/qt6_{name}.py' for name in ('fault_probe', 'file_errors', 'persist_probe', 'sdk_probe')]
boot_tree = ast.parse((ROOT / 'tests/boot_smoke.py').read_text())
guest = next(n for n in boot_tree.body if isinstance(n, ast.ClassDef) and n.name == 'Guest')
init = next(n for n in guest.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
media_selection = init.body[0]
assert isinstance(media_selection, ast.If)
results = []
for path in paths:
    for version, text in [('before', subprocess.check_output(['git', 'show', BASELINE + ':' + path], cwd=ROOT, text=True)), ('after', (ROOT / path).read_text())]:
        tree = ast.parse(text)
        assignments = [n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'image' for t in n.targets)]
        assert len(assignments) == 1, path
        for suffix in ('.iso', '.ISO', '.img', ''):
            context = {'Path': Path, 'a': SimpleNamespace(image=Path('source' + suffix)), 'tmp': OUT / 'media-input', 'temp': str(OUT / 'media-input'), 'folder': str(OUT / 'media-input'), 'iso': None}
            exec(compile(ast.Module(body=[assignments[0], media_selection], type_ignores=[]), path, 'exec'), context)
            command = qemu_command(context['image'], iso=context['iso'])
            is_cdrom = '-cdrom' in command
            if version == 'after':
                assert is_cdrom == (suffix.lower() == '.iso'), (path, suffix, command)
            else:
                assert not is_cdrom, (path, suffix, command)
            results.append({'runner': path, 'version': version, 'source_suffix': suffix, 'copied_name': context['image'].name, 'boot_medium': 'cdrom' if is_cdrom else 'floppy', 'command': command})
assert sum(r['version'] == 'after' and r['boot_medium'] == 'cdrom' for r in results) == 8
report = {'baseline': BASELINE, 'status': 'PASSED_HOST_COMMAND_SELECTION', 'checks': 16, 'before_cases': 16, 'guest_boot': 'NOT_RUN', 'qemu_executable': os.environ.get('QEMU'), 'scope': 'Execute actual runner image assignment and Guest suffix branch, then actual qemu_command; no subprocess starts QEMU.', 'results': results}
(OUT / 'ui_media_selection.json').write_text(json.dumps(report, indent=2) + '\n')
print(report['status'], '16 current cases; 16 baseline cases; no guest boot')
PY
```

## 4. B24：派生 runner 的来源记录

五个 runner：[P2G4](../../../tests/ssg_p2g4_guest.py)、[P2G5](../../../tests/ssg_p2g5_guest.py)、[exhaust](../../../tests/ssg_p2g6_exhaust_guest.py)、[navigation](../../../tests/ssg_p2g6_navigation_guest.py)、[reload](../../../tests/ssg_p2g6_reload_guest.py)。

直接执行每份源码中的真实来源记录循环。预期 **5 个当前 runner** 都记录自身名称、路径、当前 SHA-256 和共同的 structure 输入；**5 个基线循环** 都遗漏自身，仅记录 pages probe。基线循环仍在当前工作树文件上计算摘要，因此它证明的是旧循环选错了哪个输入，不是恢复历史运行时所有输入的完整快照。不会导入并执行整份 guest runner，也不写旧报告。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
import ast
import hashlib
import json
import subprocess

ROOT = Path.cwd()
BASELINE = 'e6246faf8eefac305a99528f727b1592ee93a5b2'
OUT = ROOT / 'build/comprehensive_audit_replay'
OUT.mkdir(parents=True, exist_ok=True)
paths = ['tests/ssg_p2g4_guest.py', 'tests/ssg_p2g5_guest.py', 'tests/ssg_p2g6_exhaust_guest.py', 'tests/ssg_p2g6_navigation_guest.py', 'tests/ssg_p2g6_reload_guest.py']
results = []
for path in paths:
    for version, text in [('before', subprocess.check_output(['git', 'show', BASELINE + ':' + path], cwd=ROOT, text=True)), ('after', (ROOT / path).read_text())]:
        tree = ast.parse(text)
        loops = [n for n in tree.body if isinstance(n, ast.For) and isinstance(n.iter, ast.Tuple) and any(isinstance(e, ast.Constant) and e.value == 'ssg_browser_structure.py' for e in n.iter.elts)]
        assert len(loops) == 1
        context = {'Path': Path, '__file__': str(ROOT / path), 'ROOT': ROOT, 'sha': lambda data: hashlib.sha256(data).hexdigest(), 'report': {'inputs': {}}}
        exec(compile(ast.Module(body=loops, type_ignores=[]), path, 'exec'), context)
        inputs = context['report']['inputs']
        if version == 'before':
            assert Path(path).name not in inputs
            assert set(inputs) == {'ssg_browser_pages_probe.py', 'ssg_browser_structure.py'}
        else:
            assert set(inputs) == {Path(path).name, 'ssg_browser_structure.py'}
            own = inputs[Path(path).name]
            assert Path(own['path']) == ROOT / path
            assert own['sha256'] == hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for name, entry in inputs.items():
            assert Path(entry['path']) == ROOT / 'tests' / name
            assert entry['sha256'] == hashlib.sha256((ROOT / 'tests' / name).read_bytes()).hexdigest()
        results.append({'runner': path, 'version': version, 'inputs': {name: {'path': str(Path(value['path']).relative_to(ROOT)), 'sha256': value['sha256']} for name, value in inputs.items()}})
report = {'baseline': BASELINE, 'status': 'PASSED_HOST_PROVENANCE_SELECTION', 'current_runners': 5, 'baseline_runners': 5, 'guest_run': 'NOT_RUN', 'scope': 'Execute actual runner provenance loop without argparse, QEMU, or historical report writes', 'results': results}
(OUT / 'ui_runner_provenance.json').write_text(json.dumps(report, indent=2) + '\n')
print(report['status'], '5 current runners, 5 baseline runners; no guest run')
PY
```

## 5. B28 / B29：非正次数和真实压力输入大小

对应 [E08 post5 P1 运行器](../../../tests/e08_post5_p1.py)。执行真实参数入口和生成表达式，不运行 seed preflight、Guest 或 GCC。

两版本各检查省略 `--cycles`、`-1`、`0`、`1`、`10`，共 **10 组参数检查**；原版全部接受，修复版对 `-1`、`0` 返回 2。再执行真实 `big.c` 生成表达式及报告表达式：两版本生成文本相同，审计时实际为 **385,814 字节**，修复后的报告按文件长度记录。这里没有把源码报告修正视为 R3 压力验收。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
"""Execute selected real runner AST nodes; no Guest or pressure run is simulated."""
import argparse
import ast
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path.cwd()
BASELINE = 'e6246faf8eefac305a99528f727b1592ee93a5b2'
OUT = ROOT / 'build/comprehensive_audit_replay'
OUT.mkdir(parents=True, exist_ok=True)
PATH = 'tests/e08_post5_p1.py'


def inspect_source(source, revision):
    tree = ast.parse(source, filename=PATH)
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    prefix = []
    for node in main.body:
        if any(isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
               and child.func.id == 'read_manifest' for child in ast.walk(node)):
            break
        prefix.append(node)
    parser_code = compile(ast.Module(body=prefix, type_ignores=[]), PATH, 'exec')
    rows = []
    original_argv = sys.argv
    try:
        for cycles in (None, -1, 0, 1, 10):
            sys.argv = [PATH, '--levels', 'r1']
            if cycles is not None:
                sys.argv += ['--cycles', str(cycles)]
            namespace = {'argparse': argparse, 'Path': Path, 'ROOT': ROOT, '__doc__': ast.get_docstring(tree)}
            stderr = io.StringIO()
            code = 0
            with contextlib.redirect_stderr(stderr):
                try:
                    exec(parser_code, namespace)
                except SystemExit as error:
                    code = error.code
            rows.append({'cycles': cycles, 'exit_code': code,
                         'error': stderr.getvalue().strip().splitlines()[-1:]})
            expected = 2 if revision == 'current' and cycles in (-1, 0) else 0
            assert code == expected, (revision, cycles, code)
    finally:
        sys.argv = original_argv

    generator = next(node.args[1] for node in ast.walk(main)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                     and node.func.id == 'put' and node.args and
                     isinstance(node.args[0], ast.Constant) and node.args[0].value == 'big.c')
    payload = eval(compile(ast.Expression(generator), PATH, 'eval'))
    label = next(node.value.args[0] for node in ast.walk(main)
                 if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                 and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'append'
                 and node.value.args and any(isinstance(part, ast.Constant)
                     and isinstance(part.value, str) and part.value.startswith('R3 ')
                     for part in ast.walk(node.value.args[0])))
    with tempfile.TemporaryDirectory(prefix='xos_e08_source_', dir=OUT) as folder:
        tmp = Path(folder)
        (tmp / 'big.c').write_text(payload)
        size = (tmp / 'big.c').stat().st_size
        check = eval(compile(ast.Expression(label), PATH, 'eval'), {'tmp': tmp})
        if revision == 'current':
            assert check == f'R3 {size} byte source/8MiB BSS/64 includes', check
        else:
            assert check == 'R3 1MiB source/8MiB BSS/64 includes', check
        assert size < 1024 * 1024
    return {'revision': revision, 'argument_checks': rows, 'source_bytes': size,
            'r3_check': check}, payload


baseline = subprocess.check_output(['git', 'show', f'{BASELINE}:{PATH}'], cwd=ROOT, text=True)
old, old_payload = inspect_source(baseline, BASELINE)
current, current_payload = inspect_source((ROOT / PATH).read_text(), 'current')
assert old_payload == current_payload, 'Pressure source changed'
report = {'status': 'passed', 'scope': 'real runner AST parameter validation, source generator, report label',
          'guest': 'not_run', 'source_unchanged': True, 'results': [old, current]}
output = OUT / 'e08_post5_contract.json'
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
PY
```

## 6. B20：可选隔离探针的源码与语法复核

对应 [VirtIO GPU 验收运行器](../../../tests/virtio_gpu_acceptance.py)。本次只完成源码流程和 Python 语法检查，未提供真实 access payload、未启动客体。因此 B20 没有加入上面的自动化宿主用例数量，也没有补造模拟 Guest 结果。

从仓库根运行以下命令可重现差异查看和语法编译，输出写入独立 replay 目录：

```bash
mkdir -p build/comprehensive_audit_replay
git diff e6246faf8eefac305a99528f727b1592ee93a5b2 -- tests/virtio_gpu_acceptance.py > build/comprehensive_audit_replay/b20_source.diff
PYTHONPYCACHEPREFIX="$PWD/build/comprehensive_audit_replay/pycache" python3 -m py_compile tests/virtio_gpu_acceptance.py
```

需结合实际完整流程核对三点：

1. `report` 初始化包含 `not_run`，统一成功检查表中没有无条件的 `user_MMIO_and_PCI_IO_fault_isolation`。
2. 提供 `a.access_payload` 时，VBE / VirtIO 两轮中实际执行 MMIO 与 ports 子场景并核对向量；只有两轮后续流程均未抛异常，才在统一收尾中追加该成功检查。
3. 未提供 payload 时追加 `not_run` 原因；不把可选隔离项标记为通过。异常会进入失败路径，不能到达末尾的 `PASSED`。

这些检查只能确认报告控制流和语法。该 runner 还存在报告中另列的旧 Display / Interactium 代际前置问题；需使用匹配当前系统的 Qt、SDK、guest 镜像和 access payload 完成后续验收。

## 本次文档重放记录

本文代码块从仓库根重放通过：第 1 节三组定向检查、第 2 节两个真实失败入口、第 3 节 16 个当前及 16 个基线用例、第 4 节 5 个当前及 5 个基线循环、第 5 节 10 组参数检查和真实源/标签检查，第 6 节语法编译通过。第 2 节的 B07 本次环境满足缺编译器条件，没有跳过。JSON 输出属于新的 replay 输出，不覆盖先前审计结果或冻结证据。

复核时以自己执行的结果为准；宿主语句证据与静态阅读范围不得扩大为完整 Qt 构建、客体压力、设备隔离或项目整体资格通过。
