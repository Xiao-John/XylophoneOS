# SPDX-License-Identifier: Apache-2.0
"""Produce evidence-linked calling-point matrices from the frozen source files."""
import argparse,csv,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
# group, source path, literal call anchor, current behavior, gap, suggested owner, probe
PUBLIC=[
('chromium','v8/include/v8config.h','# define V8_OS_STRING "linux"','header parses but selects no XOS OS','native OS/build configuration; no impersonating Linux','engine/toolchain','v8_target FAILED'),
('chromium','v8/src/base/platform/platform-posix.cc','void* result = mmap(hint','libc internal mmap returns ENOSYS; public sys/mman.h absent','anonymous VMA reservations; alignment; commit/decommit; guard/unmap lifetime','memory/ABI then libc','mprotect; v8_posix_system_includes FAILED'),
('chromium','v8/src/base/platform/platform-posix.cc','int ret = mprotect(address','public protection mechanism absent','W^X page protection and executable transitions; isolated fault tests','memory/ABI','mprotect FAILED'),
('chromium','v8/src/base/platform/platform-posix.cc','MAP_SHARED, fd, offset','no accepted shared mapping contract','shared object ownership/rights/transfer/revoke and cross-process mapping','memory/IPC','NOT_RUN shared mapping'),
('chromium','v8/src/base/platform/platform-posix.cc','result = pthread_create','restricted 1:1 threads; max 4/process, 32 total','actual V8 thread budget; stack/TLS/termination; no fake locks','thread/runtime','threads PASSED restricted Python only; V8 NOT_RUN'),
('chromium','v8/src/base/platform/semaphore.cc','int result = sem_init','pthread mutex/cond accepted subset; sem not qualified','semaphore backend with real wait/deadline semantics','thread/runtime','NOT_RUN semaphore'),
('chromium','chromium/base/process/launch_posix.cc','pid = fork();','single-thread eager fork only; threaded fork/exec rejected','safe Chromium child launch with authenticated handles and lifecycle','process/loader','subprocess FAILED'),
('chromium','chromium/base/message_loop/message_pump_epoll.cc','epoll_.reset(epoll_create1','IPC/word/pipe waits exist; no epoll API','generic readiness and atomic wait/cancel/deadline adapters','wait/IPC/libc','v8_posix_system_includes FAILED; event loop NOT_RUN'),
('chromium','chromium/base/memory/platform_shared_memory_region_posix.cc','if (!AllocateFileRegion','bounded files; no shared-memory seal/transfer contract','sealed shared regions, RO duplication, object lifetime','memory/file/IPC','NOT_RUN shared regions'),
('chromium','chromium/base/native_library_posix.cc','void* dl = dlopen','static ELF loader; no accepted dynamic loading','relocations, TLS, dependency validation, unload and failures','loader/runtime','dlopen FAILED'),
('chromium','chromium/sandbox/linux/services/credentials.cc','if (sys_unshare(CLONE_NEWUSER))','no Linux namespaces/seccomp contract; XOS authenticated grants exist','native sandbox broker and policy equivalence with denial/escape probes','security/process','BLOCKED native sandbox design; NOT_RUN containment'),
('chromium','chromium/content/shell/app/shell_main.cc','ContentMain','no content shell executable built','toolchain/dependency closure, Ozone software output/input integration','engine/graphics','NOT_RUN full content shell'),
('code_oss','vscode/src/vs/workbench/services/extensions/worker/webWorkerExtensionHostIframe.html','new URL(document.location.href)','QuickJS lacks URL/DOM; Aurora has no JS runtime','real DOM/URL/origin/resource loading in target Web engine','web engine','code_actual_iframe FAILED on guest'),
('code_oss','vscode/src/vs/workbench/services/extensions/browser/webWorkerExtensionHost.ts',"document.createElement('iframe')",'no JS DOM/iframe isolation','sandboxed iframe, postMessage transfer, origin checks','web engine/security','web_capabilities unavailable; NOT_RUN extension host'),
('code_oss','vscode/src/vs/workbench/services/extensions/worker/webWorkerExtensionHostIframe.html','new Worker(','no Web Worker API','worker execution, module loading, MessagePort, termination','web engine/thread','web_capabilities absent; NOT_RUN worker execution'),
('code_oss','vscode/src/vs/workbench/services/extensions/worker/webWorkerExtensionHostIframe.html','crypto.subtle.digest','no Web Crypto API; os.urandom probe only','secure context, origin validation, SHA-256 Web Crypto semantics','web engine/security','web_capabilities absent; NOT_RUN Web Crypto'),
('code_oss','vscode/src/vs/platform/files/browser/htmlFileSystemProvider.ts',"import { IndexedDB }",'guest files exist; no browser IndexedDB/FileSystemAccess provider','origin quota/persistence and reviewed capability bridge to native files','web engine/file service','web_capabilities absent; NOT_RUN file provider'),
('code_oss','vscode/src/vs/editor/browser/controller/editContext/native/nativeEditContext.ts',"document.createElement('textarea')",'Aurora Qt input works in its own scope; no DOM editor','DOM/CSS selection, clipboard, IME, accessibility and layout','web engine/input','NOT_RUN Monaco/Code editing'),
('code_oss','node/src/spawn_sync.cc','r = uv_spawn(','no Node/libuv runtime; restricted fork/exec','process spawn/stdio/environment/kill/wait lifecycle','Node/process/libc','subprocess FAILED; Node NOT_RUN'),
('code_oss','node/src/tty_wrap.cc','uv_tty_init(','no PTY/termios contract','PTY master/slave, resize, EOF/cancel, terminal input ownership','terminal/process','pty FAILED'),
('code_oss','node/deps/uv/src/unix/linux.c','loop->backend_fd = epoll_create1','no epoll backend','XOS libuv readiness backend; no fake success','wait/Node','event-loop NOT_RUN'),
('code_oss','node/deps/uv/src/unix/linux.c','fd = inotify_init1','file service has no equivalent watch guarantee','bounded watch lifecycle, overflow/rescan, cancellation','files/Node','file_watch FAILED'),
('code_oss','node/src/node_file.cc','req->Dispatch(uv_fs_close','bounded native file API; no Node fs adapter','stat/path/rights/watch/close adapter preserving errors','Node/files','NOT_RUN Node fs'),
('code_oss','vscode/src/vs/workbench/api/node/extensionHostProcess.ts','process','no Electron or Node extension-host binary','extension launch, RPC/lifecycle, LSP/DAP/Git processes and budgets','Code/Node/process','NOT_RUN desktop, extensions, LSP, DAP, Git'),
]
PRIVATE=[
('localpilot_api/server.py','class APIServer(ThreadingHTTPServer)','_socket absent; threaded server import blocked','socket bind/listen/accept and select backend; HTTP/SSE contract tests','network/Python','socket_loopback FAILED'),
('agent/local_http.py','import ssl','_ssl absent','verified TLS, trust store, hostname/time/RNG; no insecure context','TLS/Python','ssl_verified_context FAILED'),
('agent/commands.py','subprocess.Popen(','_posixsubprocess absent; threaded process constraints','real subprocess stdio/deadline/cancel; preserve approvals','process/Python','subprocess FAILED'),
('localpilot_service/security.py','os.open(path, os.O_RDONLY','private open rejected by XOS; no owner-only file contract','O_NOFOLLOW/nonblock, uid/mode trust and metadata consistency','file/Python/security','file_permissions FAILED'),
('localpilot_service/cli.py','psutil.Process(','psutil import blocked by _socket; native getpriority unit fails','authenticated process identity/statistics; platform backend; no PID-only fake','process/Python','psutil FAILED; native psutil FAILED'),
('localpilot_service/workspaces.py','os.open(root,os.O_RDONLY','dirfd/identity safety not qualified','reviewed stable directory grants, revocation and path substitution defenses','files/security','NOT_RUN original workspace grants'),
('agent/host_tools.py',"'/usr/bin/sandbox-exec'",'macOS sandbox command absent','XOS-specific least-rights executor with original operator gateway','security/process','BLOCKED native executor; NOT_RUN host tools'),
('agent/host_tools.py','ssl.create_default_context()','no TLS provider network','remote inference only after egress approval and TLS qualification','network/security','NOT_RUN inference'),
('desktop/src-tauri/Cargo.toml','tauri =','no registered XOS Rust std/WebView target','Rust std/target + Tauri runtime/window/event loop/dialog/tray backends','Rust/GUI/platform','NOT_RUN Tauri target build'),
('computer/native/AXBridge.swift','import AppKit','Apple frameworks absent','XOS native accessibility/consent/audit platform implementation','XOS desktop/security','NOT_RUN Computer Use'),
('companion/ui/main.swift','import AppKit','Apple native pet has no XOS runtime','native pet/window/tray integration with identity and permissions','XOS desktop','NOT_RUN Apple pet compatibility'),
]
def main():
 p=argparse.ArgumentParser();p.add_argument('--localpilot',type=Path,required=True);a=p.parse_args();out=ROOT/'docs/reports/modern_apps_20261029';lock=json.loads((out/'source_lock.json').read_text());rows={x:[] for x in ['chromium','code_oss','localpilot']}
 def add(group,path,anchor,current,gap,owner,probe,private=False):
  source=(a.localpilot if private else ROOT/'build/modern_apps/sources')/path
  lines=source.read_text().splitlines();line=next((i for i,s in enumerate(lines,1) if anchor in s),None)
  if line is None:raise ValueError('call point not found: '+path+' '+anchor)
  rows[group].append({'source_path':path,'line':line,'call_anchor':anchor,'XOS_current_behavior':current,'gap':gap,'suggested_owner':owner,'acceptance_probe':probe,'source_scope':'private SHA pinned; source text not copied' if private else 'public SHA pinned in source_lock.json'})
 for row in PUBLIC:add(*row)
 for row in PRIVATE:add('localpilot',*row,private=True)
 for name,data in rows.items():
  with (out/(name+'_matrix.csv')).open('w') as f:
   writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
 print({name:len(data) for name,data in rows.items()})
if __name__=='__main__':main()
