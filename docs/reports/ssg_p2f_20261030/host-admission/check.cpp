#include "src/ports/aurora_browser/content.hpp"
#include <cstdio>
int main(int argc,char **argv){
    bool all=true;
    for(int i=1;i<argc;++i){
        QFile input(QString::fromUtf8(argv[i]));
        if(!input.open(QIODevice::ReadOnly))return 2;
        const auto bytes=input.readAll();QString error;
        const bool accepted=browser::html_allowed(bytes,error);
        std::printf("ADMISSION path=%s bytes=%lld accepted=%d error=%s\n",argv[i],(long long)bytes.size(),int(accepted),error.toUtf8().constData());
        all=all&&accepted;
    }
    return all?0:1;
}
