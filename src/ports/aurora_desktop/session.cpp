// SPDX-License-Identifier: Apache-2.0
// Ordinary userspace parent. Start with xsh exec-driver for explicit child-spawn
// authority; names/paths confer no authority. No child inherits spawn authority.
#include <xos/execution.hpp>
#include <xos/file_abi.hpp>
#include <xos/sdk.hpp>
#include <cstdio>

namespace {
struct app_entry {
    const char* path;
    const char* legacy_path = nullptr;
};

xos::i64 launch_app(const app_entry& entry, xos::u32 argc, const char** argv) {
    argv[0] = entry.path;
    xos::execution::launch_diagnostic diagnostic{};
    const auto child = xos::execution::spawn_file_diagnosed(entry.path, argc, argv, {}, diagnostic);
    if (entry.legacy_path == nullptr || diagnostic.stage != xos::execution::launch_stage::open ||
        child != static_cast<xos::i64>(xos::file::status::not_found)) {
        return child;
    }
    argv[0] = entry.legacy_path;
    return xos::sdk::spawn_file(entry.legacy_path, argc, argv);
}
}

int main() {
    const app_entry apps[] = {
        {"/usr/bin/mobius.elf", "/bin/desktop.elf"},
        {"/bin/notes.elf"},
        {"/usr/bin/clarke.elf", "/bin/browser.elf"},
        {"/bin/studio.elf"},
    };
    char preferences[16]="16";const char *notice="";
    for (;;) {
        const char *args[]={nullptr,preferences,notice};
        const auto child=launch_app(apps[0],3,args);
        if(child<0){std::printf("SESSION_START_FAILED error=%lld\n",(long long)child);return 1;}
        xos::process_status status{};const auto result=xos::sdk::wait(child,status);
        if(result<0){std::printf("SESSION_WAIT_FAILED error=%lld\n",(long long)result);return 2;}
        if(status.outcome!=xos::process_outcome::exited || status.code<16)return status.outcome==xos::process_outcome::exited && status.code==0?0:1;
        const int request=status.code-16,id=request%8,bits=request/8;
        if(id<1 || id>3 || bits>127){std::printf("SESSION_REQUEST_REJECTED\n");return 3;}
        std::snprintf(preferences,sizeof(preferences),"%d",bits);
        const char *app_args[]={nullptr,preferences};
        const auto app=launch_app(apps[id],id==3?2:1,app_args);
        if(app<0){std::printf("SESSION_APP_FAILED app=%d error=%lld\n",id,(long long)app);notice="Application could not start. See serial diagnostics.";continue;}
        std::printf("SESSION_APP_STARTED app=%d pid=%lld\n",id,(long long)app);
        if(xos::sdk::wait(app,status)<0)return 4;
        std::printf("SESSION_APP_ENDED app=%d kind=%u code=%lld\n",id,unsigned(status.outcome),(long long)status.code);
        notice=status.outcome==xos::process_outcome::exited && status.code==0 ? "Application closed. Welcome back." : "Application ended with an error. See serial diagnostics.";
    }
}
