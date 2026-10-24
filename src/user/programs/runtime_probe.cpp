// SPDX-License-Identifier: Apache-2.0
#define _POSIX_C_SOURCE 200809L
#include <xos/sdk.hpp>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <spawn.h>
#include <dirent.h>

static int fail(const char* message) { fprintf(stderr,"[runtime] FAILED %s errno=%d\n",message,errno); return 1; }
int main(int argc,char** argv) {
    if(argc<2) return fail("mode");
    if(!strcmp(argv[1],"tls-control")) {
        using namespace xos;
        if(sdk::syscall(sys_process_tls,sdk::pid(),process_tls_begin)!=process_error_denied) return fail("TLS self authorization");
        const char child_name[]="tls_check";
        const i64 child=sdk::syscall(sys_process_create,0,reinterpret_cast<u64>(child_name),9);
        if(child<0) return fail("TLS builder create");
        const i64 outside=sdk::syscall(sys_process_tls,static_cast<u64>(child),process_user_begin);
        const i64 unmapped=sdk::syscall(sys_process_tls,static_cast<u64>(child),process_tls_begin);
        const i64 aborted=sdk::syscall(sys_process_abort,static_cast<u64>(child));
        if(outside!=process_error_invalid || unmapped!=process_error_invalid || aborted!=0) return fail("TLS bad TP/abort");
        printf("[runtime] tls-control=ok self-denied outside-denied unmapped-denied abort=ok\n");
        return 0;
    }
    if(!strcmp(argv[1],"file-position")) {
        const char* path="/out/position.bin";
        unsigned char data[16384];
        for(size_t i=0;i<sizeof(data);++i) data[i]=static_cast<unsigned char>((i*37+i/251)&255);
        FILE* stream=fopen(path,"wb");
        if(!stream || fwrite(data,1,sizeof(data),stream)!=sizeof(data) || fclose(stream)) return fail("position fixture");
        int fd=open(path,O_RDONLY);
        if(fd<0) return fail("position open");
        off_t initial=lseek(fd,0,SEEK_CUR);
        printf("[runtime] initial-offset=%ld expected=0\n",static_cast<long>(initial));
        if(initial!=0) return fail("initial file offset");
        unsigned char bytes[257];
        int alias=dup(fd);
        if(alias<0 || read(fd,bytes,17)!=17 || lseek(alias,0,SEEK_CUR)!=17 ||
           lseek(alias,-7,SEEK_CUR)!=10 || read(fd,bytes,19)!=19 || memcmp(bytes,data+10,19) ||
           close(fd) || close(alias)) return fail("position dup/relative seek");
        stream=fopen(path,"rb");
        if(!stream || ftell(stream)!=0 || fread(bytes,1,17,stream)!=17 || ftell(stream)!=17 ||
           fseek(stream,4000,SEEK_SET) || fread(bytes,1,sizeof(bytes),stream)!=sizeof(bytes) ||
           memcmp(bytes,data+4000,sizeof(bytes)) || ftell(stream)!=4257 ||
           fseek(stream,-257,SEEK_CUR) || fread(bytes,1,sizeof(bytes),stream)!=sizeof(bytes) ||
           memcmp(bytes,data+4000,sizeof(bytes)) || fseek(stream,100,SEEK_SET) ||
           fread(bytes,1,sizeof(bytes),stream)!=sizeof(bytes) || memcmp(bytes,data+100,sizeof(bytes)) ||
           fseek(stream,-257,SEEK_END) || fread(bytes,1,sizeof(bytes),stream)!=sizeof(bytes) ||
           memcmp(bytes,data+sizeof(data)-sizeof(bytes),sizeof(bytes)) || fclose(stream)) return fail("buffered file position");
        fd=open(path,O_WRONLY|O_APPEND);
        if(fd<0 || lseek(fd,0,SEEK_CUR)!=sizeof(data) || write(fd,"!",1)!=1 ||
           lseek(fd,0,SEEK_CUR)!=sizeof(data)+1 || close(fd)) return fail("append initial offset");
        printf("[runtime] file-position=ok raw/dup/buffered/append\n");
        return 0;
    }
    if(!strcmp(argv[1],"archive-index")) {
        if(argc!=4 || (strcmp(argv[3],"yes") && strcmp(argv[3],"no"))) return fail("archive arguments");
        FILE* archive=fopen(argv[2],"rb");
        unsigned char header[68];
        if(!archive || fread(header,1,sizeof(header),archive)!=sizeof(header) || fclose(archive) ||
           memcmp(header,"!<arch>\n",8)) return fail("archive header");
        bool present=(header[8]=='/' && header[9]==' ') || !memcmp(header+8,"/SYM64/",7);
        if(present!=(strcmp(argv[3],"yes")==0)) return fail("archive index state");
        printf("[runtime] archive-index=%s\n",present?"present":"absent");
        return 0;
    }
    if(!strcmp(argv[1],"emit")) {
        const char* value=getenv("XOS_CHILD_ENV");
        char cwd[256];
        if(!value || strcmp(value,"inherited-value") || !getcwd(cwd,sizeof(cwd)) || strcmp(cwd,"/src")) return fail("environment/cwd");
        printf("child-pipe-data\n");
        return 23;
    }
    if(!strcmp(argv[1],"copy")) {
        FILE* input=fopen("input.c","rb");
        if(!input) return fail("child fopen");
        char bytes[128];size_t n=fread(bytes,1,sizeof(bytes),input);
        if(ferror(input) || fclose(input) || n==0) return fail("child read");
        FILE* output=fopen("/out/object.bin","wb");
        if(!output || fwrite(bytes,1,n,output)!=n || fclose(output)) return fail("child write");
        return 17;
    }
    if(strcmp(argv[1],"driver")) return fail("unknown mode");
    struct stat st{};
    if(stat("/src/input.c",&st) || !S_ISREG(st.st_mode) || st.st_size==0) return fail("stat");
    struct stat same{};
    if(stat("/SRC/INPUT.C",&same) || same.st_dev!=st.st_dev || same.st_ino!=st.st_ino || st.st_ino==0) return fail("stat identity/case alias");
    errno=0;if(open("/src/absent.c",O_RDONLY)>=0 || errno!=ENOENT) return fail("not_found");
    char* memory=static_cast<char*>(malloc(8*1024*1024));
    if(!memory) return fail("malloc8m");
    for(size_t i=0;i<8*1024*1024;i+=4096) memory[i]=static_cast<char>((i/4096)&127);
    for(size_t i=0;i<8*1024*1024;i+=4096) if(memory[i]!=static_cast<char>((i/4096)&127)) return fail("heap contents");
    free(memory);
    char temporary[]="/tmp/tempXXXXXX";int temp=mkstemp(temporary);
    if(temp<0 || write(temp,"temporary",9)!=9 || lseek(temp,0,SEEK_SET)!=0) return fail("temporary/seek");
    char text[32]{};
    int copied=dup(temp);
    if(copied<0 || read(copied,text,sizeof(text))!=9 || strcmp(text,"temporary") ||
       read(temp,text,1)!=0 || close(temp) || lseek(copied,0,SEEK_SET)!=0 ||
       read(copied,text,1)!=1 || text[0]!='t' || close(copied) || unlink(temporary)) return fail("temp dup/offset/unlink");
    if(mkdir("/out/runtime_dir",0755) && errno!=EEXIST) return fail("mkdir");
    if(access("/out/runtime_dir",R_OK|W_OK|X_OK)) return fail("directory access");
    errno=0;
    if(unlink("/out/runtime_dir")!=-1 || errno!=EISDIR || rmdir("/out/runtime_dir")) return fail("rmdir/unlink distinction");
    char raw[8192];memset(raw,'R',sizeof(raw));
    int raw_fd=open("/out/raw_io.bin",O_CREAT|O_TRUNC|O_RDWR,0644);
    if(raw_fd<0 || write(raw_fd,raw,sizeof(raw))!=sizeof(raw) || lseek(raw_fd,0,SEEK_SET)!=0) return fail("raw write8192");
    struct stat raw_stat{},raw_open_stat{};
    if(stat("/out/raw_io.bin",&raw_stat) || fstat(raw_fd,&raw_open_stat) ||
       raw_stat.st_dev!=raw_open_stat.st_dev || raw_stat.st_ino!=raw_open_stat.st_ino ||
       (raw_stat.st_dev==st.st_dev && raw_stat.st_ino==st.st_ino)) return fail("stat/fstat distinct identity");
    size_t raw_done=0;
    while(raw_done<sizeof(raw)) {
        ssize_t got=read(raw_fd,raw+raw_done,sizeof(raw)-raw_done);
        if(got<=0) return fail("raw read8192");
        raw_done+=static_cast<size_t>(got);
    }
    for(size_t i=0;i<sizeof(raw);++i) if(raw[i]!='R') return fail("raw contents");
    if(close(raw_fd)) return fail("raw close");
    if(rename("/out/raw_io.bin","/out/raw_moved.bin") || stat("/out/raw_moved.bin",&same) ||
       same.st_dev!=raw_stat.st_dev || same.st_ino!=raw_stat.st_ino ||
       rename("/out/raw_moved.bin","/out/raw_io.bin")) return fail("rename identity");
    DIR* dir=opendir("/src");if(!dir) return fail("opendir");
    bool found=false;while(struct dirent* item=readdir(dir)) if(!strcmp(item->d_name,"input.c")) found=true;
    if(closedir(dir) || !found) return fail("readdir");
    if(chdir("/src")) return fail("chdir");
    char* child_env[]={const_cast<char*>("XOS_CHILD_ENV=inherited-value"),const_cast<char*>("PATH=/bin"),nullptr};
    char* child_args[]={argv[0],const_cast<char*>("copy"),nullptr};pid_t child=0;int status=0;
    int error=posix_spawn(&child,argv[0],nullptr,nullptr,child_args,child_env);
    if(error) return fail("spawn-copy/wait");
    errno=0;
    if(waitpid(child,&status,WNOHANG)!=-1 || errno!=ENOTSUP) return fail("unsupported nonblocking wait");
    if(waitpid(child,&status,0)!=child || !WIFEXITED(status) || WEXITSTATUS(status)!=17) return fail("spawn-copy/wait");
    FILE* object=fopen("/out/object.bin","rb");
    if(!object || fread(text,1,3,object)!=3 || memcmp(text,"int",3) || fclose(object)) return fail("object");
    int ends[2];if(pipe(ends)) return fail("pipe");
    posix_spawn_file_actions_t actions;
    if(posix_spawn_file_actions_init(&actions) || posix_spawn_file_actions_adddup2(&actions,ends[1],1) ||
       posix_spawn_file_actions_addclose(&actions,ends[0])) return fail("file-actions");
    child_args[1]=const_cast<char*>("emit");
    error=posix_spawn(&child,argv[0],&actions,nullptr,child_args,child_env);
    posix_spawn_file_actions_destroy(&actions);
    if(error || close(ends[1]) || waitpid(child,&status,0)!=child || !WIFEXITED(status) || WEXITSTATUS(status)!=23) return fail("spawn-pipe/wait");
    memset(text,0,sizeof(text));
    if(read(ends[0],text,sizeof(text))!=16 || strcmp(text,"child-pipe-data\n") || read(ends[0],text,1)!=0 || close(ends[0])) return fail("pipe-data/eof");
    if(posix_spawn_file_actions_init(&actions) ||
       posix_spawn_file_actions_addopen(&actions,1,"/out/redirect.txt",O_CREAT|O_TRUNC|O_WRONLY,0644)) return fail("redirect action");
    error=posix_spawn(&child,argv[0],&actions,nullptr,child_args,child_env);
    posix_spawn_file_actions_destroy(&actions);
    if(error || waitpid(child,&status,0)!=child || !WIFEXITED(status) || WEXITSTATUS(status)!=23) return fail("redirect child");
    FILE* redirected=fopen("/out/redirect.txt","rb");
    memset(text,0,sizeof(text));
    if(!redirected || fread(text,1,sizeof(text)-1,redirected)!=16 || strcmp(text,"child-pipe-data\n") || fclose(redirected)) return fail("redirect contents");
    if(posix_spawn(&child,"/bin/absent_tool",nullptr,nullptr,child_args,child_env)!=ENOENT) return fail("spawn absent errno");
    FILE* input=fopen("/src/input.c","rb");
    if(!input || fread(text,1,3,input)!=3 || memcmp(text,"int",3) || fclose(input)) return fail("source preserved");
    printf("[runtime] files=ok heap=8m args_env_cwd=ok spawn_wait=ok pipe=ok source=preserved\n");
    return 0;
}
