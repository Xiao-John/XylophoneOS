#!/bin/sh
set -eu
kit=/kit/glibc
test ! -e /repo
"$kit/xos-app" init /apps/path --id unified.g3_cwd --language c
"$kit/xos-app" init /apps/cxx --id unified.unified_cxx --language cpp
cp /apps/sources/cwd_probe.c /apps/path/src/main.c
cp /apps/sources/unified_cpp_probe.cpp /apps/cxx/src/main.cpp
cp /apps/sources/xos_stack_bounds.cpp /apps/sources/xos_stack_bounds.hpp /apps/cxx/src/
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/apps/cxx/xos_app.json')
app=json.loads(p.read_bytes())
app['required_features'] += ['threads', 'stdio_transfer']
app['sources'].append('src/xos_stack_bounds.cpp')
for name in ('xos_stack_bounds.cpp', 'xos_stack_bounds.hpp'):
    app['files'].append({'source':f'src/{name}', 'path':f'usr/share/unified.unified_cxx/source/{name}', 'role':'data'})
p.write_text(json.dumps(app, indent=2)+'\n')
p=Path('/apps/path/xos_app.json')
app=json.loads(p.read_bytes())
app['required_features'] += ['directories', 'stdio_transfer']
p.write_text(json.dumps(app, indent=2)+'\n')
PY
for name in path cxx; do
    "$kit/xos-app" build "/apps/$name" >"/apps/records/$name-build.json"
    "$kit/xos-app" check "/apps/$name" >"/apps/records/$name-check.json"
    "$kit/xos-app" pack "/apps/$name" --output "/apps/$name.xpk" >"/apps/records/$name-package.json"
done
