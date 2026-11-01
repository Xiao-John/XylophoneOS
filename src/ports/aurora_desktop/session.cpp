// SPDX-License-Identifier: Apache-2.0
// Ordinary userspace parent. Start with xsh exec-driver for explicit child-spawn
// authority; names/paths confer no authority. No child inherits spawn authority.
#include <xos/sdk.hpp>
#include <cstdio>
int main() {
    const char *const apps[]={"/bin/desktop.elf","/bin/notes.elf","/bin/browser.elf","/bin/studio.elf"};
    char preferences[16]="16";const char *notice="";
    for (;;) {
        const char *args[]={apps[0],preferences,notice};
        const auto child=xos::sdk::spawn_file(apps[0],3,args);
        if(child<0){std::printf("SESSION_START_FAILED error=%lld\n",(long long)child);return 1;}
        xos::process_status status{};const auto result=xos::sdk::wait(child,status);
        if(result<0){std::printf("SESSION_WAIT_FAILED error=%lld\n",(long long)result);return 2;}
        if(status.outcome!=xos::process_outcome::exited || status.code<16)return status.outcome==xos::process_outcome::exited && status.code==0?0:1;
        const int request=status.code-16,id=request%8,bits=request/8;
        if(id<1 || id>3 || bits>127){std::printf("SESSION_REQUEST_REJECTED\n");return 3;}
        std::snprintf(preferences,sizeof(preferences),"%d",bits);
        const char *app_args[]={apps[id],preferences};
        const auto app=xos::sdk::spawn_file(apps[id],id==3?2:1,app_args);
        if(app<0){std::printf("SESSION_APP_FAILED app=%d error=%lld\n",id,(long long)app);notice="Application could not start. See serial diagnostics.";continue;}
        std::printf("SESSION_APP_STARTED app=%d pid=%lld\n",id,(long long)app);
        if(xos::sdk::wait(app,status)<0)return 4;
        std::printf("SESSION_APP_ENDED app=%d kind=%u code=%lld\n",id,unsigned(status.outcome),(long long)status.code);
        notice=status.outcome==xos::process_outcome::exited && status.code==0 ? "Application closed. Welcome back." : "Application ended with an error. See serial diagnostics.";
    }
}
