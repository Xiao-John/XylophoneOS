// SPDX-License-Identifier: Apache-2.0
// Host-only deterministic test of the unmodified Client IPC failure behavior.
#include <xos/file_client.hpp>
#include <xos/sdk.hpp>
#include <cstdio>
static int sends,receives,yields;static bool fail_send;
namespace xos::sdk {
i64 syscall(u64 n,u64 a,u64,u64){
 if(n==6)return 42;
 if(n==sys_ipc_handles){auto* p=reinterpret_cast<u32*>(a);p[0]=12;p[1]=13;return 0;}
 if(n==4){++sends;return fail_send?-1:0;}
 if(n==5){++receives;return process_error_would_block;}
 if(n==3){++yields;return 0;}
 return -1;
}
}
int main(){xos::file::Client client{};if(!client.init())return 1;
 const auto timeout=client.ping();if(timeout!=static_cast<xos::i64>(xos::file::status::would_block)||sends!=1||receives!=8192||yields!=8192)return 2;
 fail_send=true;const auto failed=client.ping();if(failed!=static_cast<xos::i64>(xos::file::status::io)||sends!=2)return 3;
 std::printf("PASS IPC no response=%lld receives=%d yields=%d; send failure=%lld\n",(long long)timeout,receives,yields,(long long)failed);return 0;}
