// SPDX-License-Identifier: Apache-2.0
// Offline installer/exporter. FatFs runs here only for explicit host transfer;
// XOS runtime still performs all filesystem operations inside the guest.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>
#include "ff.h"
#include "diskio.h"
static int image_fd = -1;
static LBA_t sectors;
extern "C" DSTATUS disk_initialize(BYTE p) { return p == 0 ? 0 : STA_NOINIT; }
extern "C" DSTATUS disk_status(BYTE p) { return disk_initialize(p); }
extern "C" DRESULT disk_read(BYTE p, BYTE* b, LBA_t s, UINT n) {
    if (p || !n || s >= sectors || n > sectors-s) return RES_PARERR;
    return pread(image_fd,b,size_t(n)*512,off_t(s)*512)==ssize_t(n)*512 ? RES_OK : RES_ERROR;
}
extern "C" DRESULT disk_write(BYTE p, const BYTE* b, LBA_t s, UINT n) {
    if (p || !n || s >= sectors || n > sectors-s) return RES_PARERR;
    return pwrite(image_fd,b,size_t(n)*512,off_t(s)*512)==ssize_t(n)*512 ? RES_OK : RES_ERROR;
}
extern "C" DRESULT disk_ioctl(BYTE p, BYTE c, void* b) {
    if (p) return RES_PARERR;
    if(c==CTRL_SYNC) return fsync(image_fd)==0 ? RES_OK : RES_ERROR;
    if(c==GET_SECTOR_COUNT) { *static_cast<LBA_t*>(b)=sectors; return RES_OK; }
    if(c==GET_SECTOR_SIZE) { *static_cast<WORD*>(b)=512; return RES_OK; }
    if(c==GET_BLOCK_SIZE) { *static_cast<DWORD*>(b)=1; return RES_OK; }
    return RES_PARERR;
}
static void check(FRESULT r) { if(r!=FR_OK) { std::fprintf(stderr,"FatFs error=%d\n",int(r)); std::exit(1); } }
int main(int argc,char** argv) {
    if(argc<4) return 2;
    image_fd=open(argv[1], O_RDWR | O_NOFOLLOW);
    struct stat st{};
    if(image_fd<0 || fstat(image_fd,&st) || !S_ISREG(st.st_mode) || st.st_size%512) return 2;
    struct flock lock{}; lock.l_type=F_WRLCK; lock.l_whence=SEEK_SET;
    if(fcntl(image_fd,F_SETLK,&lock)) { std::perror("image busy"); return 2; }
    sectors=LBA_t(st.st_size/512);
    FATFS fs{}; check(f_mount(&fs,"",1));
    FIL f{}; BYTE buffer[65536]; UINT count;
    if(!std::strcmp(argv[2],"mkdir")) { check(f_mkdir(argv[3])); }
    else if(!std::strcmp(argv[2],"import") && argc==5) {
        FILE* input=std::fopen(argv[4],"rb"); if(!input) return 2;
        // Never overwrite an existing destination. Partial imports removed on failure.
        check(f_open(&f,argv[3],FA_CREATE_NEW|FA_WRITE));
        size_t n; bool failed=false;
        while((n=std::fread(buffer,1,sizeof(buffer),input))!=0) {
            FRESULT r=f_write(&f,buffer,UINT(n),&count);
            if(r!=FR_OK || count!=n) { failed=true; break; }
        }
        failed=failed || std::ferror(input); std::fclose(input);
        FRESULT closed=f_close(&f);
        if(failed || closed!=FR_OK) { f_unlink(argv[3]); disk_ioctl(0,CTRL_SYNC,nullptr); return 1; }
    } else if(!std::strcmp(argv[2],"export") && argc==5) {
        check(f_open(&f,argv[3],FA_READ));
        FILE* output=std::fopen(argv[4],"wbx"); if(!output) return 2;
        do { check(f_read(&f,buffer,sizeof(buffer),&count));
            if(std::fwrite(buffer,1,count,output)!=count) return 1;
        } while(count);
        check(f_close(&f)); if(std::fclose(output)) return 1;
    } else return 2;
    check(f_mount(nullptr,"",0));
    if(fsync(image_fd)) return 1;
    close(image_fd); return 0;
}
