// SPDX-License-Identifier: Apache-2.0
#include <QtWidgets/QApplication>
#include <QtWidgets/QPlainTextEdit>
#include <QtGui/QScreen>
#include <QtGui/QImage>
#include <QtCore/QTimer>
#include <QtCore/QtPlugin>
#include <pthread.h>
#include <xos/thread_core.hpp>
#include <cstdio>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
int main(int argc,char **argv){
 QApplication app(argc,argv);const QByteArray mode=argc>1?argv[1]:"oom";
 if(mode=="quota"){
  for(int i=0;i<3;++i){pthread_t t{};if(pthread_create(&t,nullptr,[](void*)->void*{xos::thread::sleep_until(xos::thread::clock()+10000000000ull);return nullptr;},nullptr))return 9;}
  std::printf("WIDGETS_QUOTA_FULL\n");
 }else if(mode=="oom"){
  QImage impossible(32000,32000,QImage::Format_RGB32);if(!impossible.isNull())return 10;std::printf("WIDGETS_OOM_NULL\n");
 }
 QPlainTextEdit text("Real Widgets resource/fault consumer");text.setGeometry(app.primaryScreen()->geometry());text.showFullScreen();
 QTimer::singleShot(250,[&]{std::printf("WIDGETS_RESOURCE_READY\n");if(mode=="fault")__builtin_trap();else app.quit();});
 return app.exec();
}
