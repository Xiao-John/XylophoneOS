// SPDX-License-Identifier: Apache-2.0
// Guest-only boundary fault injection. Production service and SDK stay intact.
#include "../../../src/ports/qt6/editor/safe_file.hpp"
#include <QtCore/QCoreApplication>
#include <QtCore/QSaveFile>
#include <xos/thread_core.hpp>
#include <cstring>
using Client=xos::file::Client;
static QByteArray mode;
extern "C" xos::i64 real_close(Client*,xos::u32) asm("__real__ZN3xos4file6Client5closeEj");
extern "C" xos::i64 wrap_close(Client *c,xos::u32 h) asm("__wrap__ZN3xos4file6Client5closeEj");
extern "C" xos::i64 wrap_close(Client *c,xos::u32 h){const auto rc=real_close(c,h);if(mode=="close"){mode.clear();return -7;}return rc;}
extern "C" xos::i64 real_sync(Client*) asm("__real__ZN3xos4file6Client4syncEv");
extern "C" xos::i64 wrap_sync(Client*) asm("__wrap__ZN3xos4file6Client4syncEv");
extern "C" xos::i64 wrap_sync(Client *c){if(mode=="sync"){mode.clear();return -7;}return real_sync(c);}
extern "C" xos::i64 real_chunk(Client*,xos::u32,const void*,xos::u32) asm("__real__ZN3xos4file6Client13chunk_replaceEjPKvj");
extern "C" xos::i64 wrap_chunk(Client*,xos::u32,const void*,xos::u32) asm("__wrap__ZN3xos4file6Client13chunk_replaceEjPKvj");
extern "C" xos::i64 wrap_chunk(Client *c,xos::u32 offset,const void *data,xos::u32 n){
 if(mode=="short"){mode.clear();const auto rc=real_chunk(c,offset,data,n/2);return rc?rc:-4;}
 const auto rc=real_chunk(c,offset,data,n);
 if(mode=="hold"){std::printf("SAVE_HOLD_STAGED\n");xos::thread::sleep_until(xos::thread::clock()+30000000000ull);}
 return rc;
}
extern "C" xos::i64 real_commit(Client*) asm("__real__ZN3xos4file6Client14commit_replaceEv");
extern "C" xos::i64 wrap_commit(Client*) asm("__wrap__ZN3xos4file6Client14commit_replaceEv");
extern "C" xos::i64 wrap_commit(Client *c){const auto rc=real_commit(c);if(mode=="commit-unknown"){mode.clear();return -7;}return rc;}
int main(int argc,char **argv){
 QCoreApplication app(argc,argv);if(argc<3)return 2;
 const QByteArray requested=argv[1];mode.clear();const QString path=QString::fromUtf8(argv[2]);
 QByteArray before;QString error;if(!xos_editor::read(path,before,error))return 3;
 mode=requested;
 if(mode=="qsave") {
  mode.clear();QSaveFile f(path);f.setDirectWriteFallback(false);
  bool committed=false;if(f.open(QIODevice::WriteOnly)){if(f.write("replacement")!=11)return 4;committed=f.commit();}
  QByteArray after;if(!xos_editor::read(path,after,error)||after!=before||committed)return 5;
  std::printf("QSAVE_EXISTING_REPLACE_UNSUPPORTED_OLD_RETAINED\n");return 0;
 }
 const auto result=xos_editor::save(requested=="badpath"?QString("/missing/path.txt"):path,QByteArray("replacement\n"));
 std::printf("SAVE_RESULT saved=%d unknown=%d message=%s\n",result.saved,result.unknown,result.message.toUtf8().constData());
 QByteArray after;if(!xos_editor::read(path,after,error))return 6;
 if(requested=="commit-unknown"){
  if(result.saved || !result.unknown || after!="replacement\n")return 7;
  std::printf("SAVE_COMMIT_ERROR_UNKNOWN_NEW_COMPLETE_NOT_FALSE_SUCCESS\n");
 }else{
  if(result.saved || result.unknown || after!=before)return 8;
  std::printf("SAVE_FAILURE_OLD_BYTES_RETAINED\n");
 }
 return 0;
}
