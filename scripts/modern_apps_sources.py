# SPDX-License-Identifier: Apache-2.0
"""Fetch bounded, immutable upstream source excerpts for compatibility probes."""
import base64
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/modern_apps/sources'
REPORT = ROOT / 'docs/reports/modern_apps_20261029'
CHROMIUM = '142.0.7444.59'
CODE = '1.106.0'

def get(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'XOS-compatibility-probe'})
    return urllib.request.urlopen(request, timeout=45).read()

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    meta = json.loads(get(f'https://chromium.googlesource.com/chromium/src/+/refs/tags/{CHROMIUM}?format=JSON')[4:])
    sha = meta['commit']
    deps = base64.b64decode(get(f'https://chromium.googlesource.com/chromium/src/+/{sha}/DEPS?format=TEXT')).decode()
    import re
    v8 = re.search(r"'v8_revision':\s*'([^']+)'", deps).group(1)
    code_meta = json.loads(get(f'https://api.github.com/repos/microsoft/vscode/git/ref/tags/{CODE}'))
    code_sha = code_meta['object']['sha']
    if code_meta['object']['type'] != 'commit':
        code_sha = json.loads(get(code_meta['object']['url']))['object']['sha']
    tasks=[]
    for p in ['DEPS','LICENSE','build/config/BUILDCONFIG.gn','base/memory/platform_shared_memory_region_posix.cc','sandbox/linux/services/credentials.cc','content/shell/app/shell_main.cc','base/process/launch_posix.cc','base/message_loop/message_pump_epoll.cc','base/native_library_posix.cc','tools/clang/scripts/update.py','build/config/compiler/BUILD.gn']:
        tasks.append(('chromium/'+p,f'https://chromium.googlesource.com/chromium/src/+/{sha}/{p}?format=TEXT',True))
    for p in ['LICENSE','include/v8config.h','include/v8-version.h','include/v8-platform.h','src/base/platform/platform-posix.cc','src/base/platform/platform.h','src/base/build_config.h','src/base/platform/mutex.cc','src/base/platform/semaphore.cc','BUILD.gn']:
        tasks.append(('v8/'+p,f'https://chromium.googlesource.com/v8/v8/+/{v8}/{p}?format=TEXT',True))
    for p in ['LICENSE.txt','package.json','.npmrc','src/vs/base/browser/browser.ts','src/vs/platform/files/browser/htmlFileSystemProvider.ts','src/vs/platform/terminal/node/ptyService.ts','src/vs/platform/files/node/watcher/watcherMain.ts','src/vs/workbench/services/extensions/browser/webWorkerExtensionHost.ts','src/vs/editor/browser/controller/editContext/native/nativeEditContext.ts','src/vs/workbench/services/extensions/worker/webWorkerExtensionHostIframe.html','src/vs/workbench/browser/web.main.ts','src/vs/workbench/api/node/extensionHostProcess.ts']:
        tasks.append(('vscode/'+p,f'https://raw.githubusercontent.com/microsoft/vscode/{code_sha}/{p}',False))
    results=[]
    def fetch(t):
        p,u,b64=t
        try:
            data=get(u)
            if b64:data=base64.b64decode(data)
            target=OUT/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            return {'path':p,'url':u,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'status':'PASSED'}
        except Exception as e:return {'path':p,'url':u,'status':'FAILED','error':str(e)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(fetch,tasks))
    report={'scope':'source retrieval, not a complete checkout or runtime qualification','chromium':{'version':CHROMIUM,'sha':sha},'v8':{'sha':v8},'code_oss':{'version':CODE,'sha':code_sha},'files':results}
    (REPORT/'source_lock.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
