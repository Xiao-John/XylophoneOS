// SPDX-License-Identifier: Apache-2.0
// Bypass libc FD-mode checks to prove seal lives in the shared files service.
#include <xos/file_client.hpp>
#include <xos/sdk.hpp>
#include <sys/wait.h>
#include <unistd.h>
#include <string.h>

int main() {
    using namespace xos;
    file::Client client{};
    u32 handle=0, transferred=0;
    int begin[2],done[2],status=0;
    if(!client.init()||client.anonymous(handle)!=0||client.write(handle,"abc",3)!=3||
       client.seek(handle,0)!=0||pipe(begin)||pipe(done))return 80;
    const pid_t child=fork();
    if(child<0)return 81;
    if(!child){
        close(begin[1]);close(done[0]);u32 other=0;char data[3];
        if(read(begin[0],&other,sizeof(other))!=sizeof(other)||!other||other==handle)_exit(82);
        if(client.write(handle,"X",1)>=0||client.write(other,"Y",1)>=0)_exit(83);
        if(client.seek(handle,0,file::seek_current)!=0||client.seal_anonymous(other)!=0||
           client.seek(other,0,file::seek_current)!=0)_exit(84);
        if(client.read(handle,data,2)!=2||memcmp(data,"ab",2)||
           client.read(other,data+2,1)!=1||data[2]!='c')_exit(85);
        if(client.close(handle)!=0||client.close(other)!=0||write(done[1],"Y",1)!=1)_exit(86);
        _exit(0);
    }
    close(begin[0]);close(done[1]);
    if(client.transfer(handle,static_cast<u64>(child),transferred)!=0||
       client.seal_anonymous(handle)!=0||client.seal_anonymous(handle)!=0||
       client.write(handle,"Z",1)>=0||client.close(handle)!=0||
       write(begin[1],&transferred,sizeof(transferred))!=sizeof(transferred))return 87;
    close(begin[1]);char answer=0;
    if(read(done[0],&answer,1)!=1||answer!='Y'||read(done[0],&answer,1)!=0||close(done[0]))return 88;
    if(waitpid(child,&status,0)!=child||!WIFEXITED(status)||WEXITSTATUS(status))return 89;
    sdk::print("C3_ANON_SERVICE seal=shared fork=readonly transfer=readonly offset=shared last_close=clean PASS\n");
    return 0;
}
