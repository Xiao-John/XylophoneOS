// SPDX-License-Identifier: Apache-2.0
// Private offline FatFs session. Holds one image lock until quit/EOF.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>
#include "ff.h"
#include "diskio.h"
static int image_fd = -1;
static LBA_t sectors;
static bool read_only;
extern "C" DSTATUS disk_initialize(BYTE p) { return p == 0 ? 0 : STA_NOINIT; }
extern "C" DSTATUS disk_status(BYTE p) { return disk_initialize(p); }
extern "C" DRESULT disk_read(BYTE p, BYTE* b, LBA_t s, UINT n) {
    if (p || !n || s >= sectors || n > sectors-s) return RES_PARERR;
    return pread(image_fd,b,size_t(n)*512,off_t(s)*512)==ssize_t(n)*512 ? RES_OK : RES_ERROR;
}
extern "C" DRESULT disk_write(BYTE p, const BYTE* b, LBA_t s, UINT n) {
    if (read_only) return RES_WRPRT;
    if (p || !n || s >= sectors || n > sectors-s) return RES_PARERR;
    return pwrite(image_fd,b,size_t(n)*512,off_t(s)*512)==ssize_t(n)*512 ? RES_OK : RES_ERROR;
}
extern "C" DRESULT disk_ioctl(BYTE p, BYTE c, void* b) {
    if (p) return RES_PARERR;
    if(c==CTRL_SYNC) return read_only || fsync(image_fd)==0 ? RES_OK : RES_ERROR;
    if(c==GET_SECTOR_COUNT) { *static_cast<LBA_t*>(b)=sectors; return RES_OK; }
    if(c==GET_SECTOR_SIZE) { *static_cast<WORD*>(b)=512; return RES_OK; }
    if(c==GET_BLOCK_SIZE) { *static_cast<DWORD*>(b)=1; return RES_OK; }
    return RES_PARERR;
}
static void response(FRESULT code) {
    if (code==FR_OK) std::puts("OK"); else std::printf("ERR\t%d\n",int(code));
}
static std::vector<std::string> split(char* line) {
    std::vector<std::string> fields;
    char* begin=line;
    for (char* p=line;;++p) {
        if (*p=='\t' || *p=='\n' || !*p) {
            bool end=*p!='\t'; *p=0; fields.emplace_back(begin); begin=p+1;
            if (end) break;
        }
    }
    return fields;
}
int main(int argc,char** argv) {
    if (argc!=2 && argc!=3) return 2;
    read_only=argc==3 && !std::strcmp(argv[2],"--read-only");
    image_fd=open(argv[1],(read_only?O_RDONLY:O_RDWR)|O_NOFOLLOW);
    struct stat info{};
    if (image_fd<0 || fstat(image_fd,&info) || !S_ISREG(info.st_mode) || info.st_size<=0 || info.st_size%512) return 2;
    struct flock lock{};lock.l_type=read_only?F_RDLCK:F_WRLCK;lock.l_whence=SEEK_SET;
    if (fcntl(image_fd,F_SETLK,&lock)) { std::perror("xypm image busy");return 2; }
    sectors=LBA_t(info.st_size/512);FATFS fs{};
    FRESULT code=f_mount(&fs,"",1);
    if (code!=FR_OK) {response(code);return 2;}
    std::puts("OK");std::fflush(stdout);
    char line[4096];BYTE buffer[65536];
    while (std::fgets(line,sizeof(line),stdin)) {
        if (!std::strchr(line,'\n')) {response(FR_INVALID_PARAMETER);break;}
        auto fields=split(line);const auto& op=fields[0];
        if (op=="quit") {response(FR_OK);std::fflush(stdout);break;}
        if (op=="stat" && fields.size()==2) {
            FILINFO stat{};code=f_stat(fields[1].c_str(),&stat);
            if (code==FR_NO_FILE || code==FR_NO_PATH) std::puts("MISSING");
            else if (code==FR_OK) std::printf("OK\t%c\t%llu\t%s\t%s\n",(stat.fattrib&AM_DIR)?'D':'F',static_cast<unsigned long long>(stat.fsize),stat.fname,stat.altname);
            else response(code);
        } else if (op=="free" && fields.size()==1) {
            DWORD clusters=0;FATFS* volume=nullptr;code=f_getfree("",&clusters,&volume);
            if (code==FR_OK) std::printf("OK\t%llu\t%lu\n",static_cast<unsigned long long>(clusters)*volume->csize*512,static_cast<unsigned long>(volume->csize)*512);
            else response(code);
        } else if (op=="export" && fields.size()==3) {
            FIL file{};code=f_open(&file,fields[1].c_str(),FA_READ);
            if (code==FR_OK) {
                FILE* out=std::fopen(fields[2].c_str(),"wbx");
                if (!out) code=FR_DISK_ERR;
                else {
                    UINT count=0;
                    do {
                        code=f_read(&file,buffer,sizeof(buffer),&count);
                        if (code!=FR_OK || std::fwrite(buffer,1,count,out)!=count) {code=FR_DISK_ERR;break;}
                    } while(count);
                    if (std::fclose(out)) code=FR_DISK_ERR;
                }
                FRESULT closed=f_close(&file);if (code==FR_OK) code=closed;
            }
            response(code);
        } else if (read_only) response(FR_WRITE_PROTECTED);
        else if (op=="remove-empty" && fields.size()==2) {
            DIR dir{};code=f_opendir(&dir,fields[1].c_str());
            if (code==FR_NO_FILE || code==FR_NO_PATH) std::puts("OK\tREMOVED");
            else if (code!=FR_OK) response(code);
            else {
                FILINFO item{};code=f_readdir(&dir,&item);bool empty=code==FR_OK && !item.fname[0];
                FRESULT closed=f_closedir(&dir);if (code==FR_OK) code=closed;
                if (code!=FR_OK) response(code);
                else if (!empty) std::puts("OK\tKEPT");
                else {code=f_unlink(fields[1].c_str());if (code==FR_OK) std::puts("OK\tREMOVED");else response(code);}
            }
        }
        else if (op=="mkdir" && fields.size()==2) response(f_mkdir(fields[1].c_str()));
        else if (op=="remove" && fields.size()==2) response(f_unlink(fields[1].c_str()));
        else if (op=="import" && fields.size()==3) {
            FILE* input=std::fopen(fields[2].c_str(),"rb");
            if (!input) response(FR_DISK_ERR);
            else {
                FIL file{};code=f_open(&file,fields[1].c_str(),FA_CREATE_NEW|FA_WRITE);
                if (code==FR_OK) {
                    size_t count;UINT written;
                    while((count=std::fread(buffer,1,sizeof(buffer),input))!=0) {
                        code=f_write(&file,buffer,UINT(count),&written);
                        if (code!=FR_OK || written!=count) {code=FR_DISK_ERR;break;}
                    }
                    if (std::ferror(input)) code=FR_DISK_ERR;
                    if (code==FR_OK) code=f_sync(&file);
                    FRESULT closed=f_close(&file);if (code==FR_OK) code=closed;
                    if (code!=FR_OK) (void)f_unlink(fields[1].c_str());
                }
                std::fclose(input);response(code);
            }
        } else if (op=="sync" && fields.size()==1) response(fsync(image_fd)==0?FR_OK:FR_DISK_ERR);
        else response(FR_INVALID_PARAMETER);
        std::fflush(stdout);
    }
    code=f_mount(nullptr,"",0);
    if (!read_only && fsync(image_fd)) code=FR_DISK_ERR;
    close(image_fd);return code==FR_OK?0:1;
}
