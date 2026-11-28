from pathlib import Path
import hashlib,json,shutil,sys
root=Path('/work/worktrees/p1_d')
sys.path.insert(0,str(root/'scripts'))
from xos_app import build,pack
from xypm_format import load_json,canonical,sha_file
base=root/'.cache/xos_seed/xypm/2397198eff7f5003a5f0'
folder=root/'build/p1d-xypm-ipc-diagnostic-v1'
folder.mkdir(exist_ok=False)
project=folder/'project'
shutil.copytree(base/'project',project,ignore=shutil.ignore_patterns('build'))
path=project/'src/pumpkin/provisioning_client.cpp'
old=path.read_text()
original=sha_file(path)
text='#include <cstdio>\n'+old
before='static_cast<u64>(start) > ~u64{0} - max_request_ns) { close(); return exchange::not_sent; }'
after='''static_cast<u64>(start) > ~u64{0} - max_request_ns) {
        std::fprintf(stderr,"P1D_IPC_DIAG preflight op=%u send=%u receive=%u sequence=%llu now=%lld\\n",
            static_cast<unsigned>(request.operation), channel_.send, channel_.receive,
            static_cast<unsigned long long>(sequence_), static_cast<long long>(start));
        close(); return exchange::not_sent; }'''
assert text.count(before)==1
text=text.replace(before,after)
before='if (sdk::ipc_send(channel_.send, &request, sizeof(request)) != 0) { close(); return exchange::not_sent; }'
after='''const auto sent = sdk::ipc_send(channel_.send, &request, sizeof(request));
    if (sent != 0) {
        u64 peer = 0;
        const auto queried = sdk::ipc_endpoint_peer(channel_.send, peer);
        const auto writable = sdk::ipc_wait(channel_.send, ipc_wait_mode::try_send);
        std::fprintf(stderr,"P1D_IPC_DIAG op=%u send=%u receive=%u sequence=%llu now=%lld sent=%lld peer_result=%lld peer=%llu writable=%lld\\n",
            static_cast<unsigned>(request.operation), channel_.send, channel_.receive,
            static_cast<unsigned long long>(request.sequence), static_cast<long long>(start),
            static_cast<long long>(sent), static_cast<long long>(queried),
            static_cast<unsigned long long>(peer), static_cast<long long>(writable));
        close(); return exchange::not_sent;
    }'''
assert text.count(before)==1
text=text.replace(before,after)
path.write_text(text)
(folder/'diagnostic_source.json').write_bytes(canonical({'scope':'failure-only observational copied-client diagnostics; no authority/deadline/return-value change',
    'original_installer_manifest_sha256':sha_file(base/'manifest.json'), 'source':str(path),
    'original_source_sha256':original,'instrumented_source_sha256':sha_file(path)}))
profile=load_json('/work/worktrees/p1_f/build/p1f-profile.json')
sdk=Path('/work/worktrees/p1_f/build/p1f-cxx-sdk')
receipt=build(project,sdk,profile,archives=('src/vendor/libcrypto.a',),gc_sections=True)
result=pack(project,sdk,profile,folder/'xypm.xpk')
result['elf']=str(project/receipt['output'])
result['cache_key']='ipc_diagnostic_v1'
(folder/'manifest.json').write_bytes(canonical(result))
print(json.dumps(result,indent=2))
