// SPDX-License-Identifier: Apache-2.0
// Matched scenes in the same ELF: sampled cost, not an absolute peak measurement.
#include "../../../src/ports/qt6/aurora/aurora.hpp"
#include "../../../src/ports/qt6/aurora/style.hpp"
#include <QtWidgets/QVBoxLayout>
#include <QtWidgets/QPlainTextEdit>
#include <QtWidgets/QLabel>
#include <QtWidgets/QStyleFactory>
#include <QtGui/QScreen>
#include <QtCore/QtPlugin>
#include <xos/thread_core.hpp>
#include <memory>
#include <cstdio>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
int main(int argc,char **argv){
 QApplication app(argc,argv);const bool glass=argc>1 && QByteArray(argv[1])=="aurora";
 if(glass)aurora::initialize(app);else{app.setStyle(QStyleFactory::create("Fusion"));QFont font("DejaVu Sans");font.setPixelSize(16);app.setFont(font);}
 auto window=glass?std::unique_ptr<QWidget>(new aurora::canvas):std::unique_ptr<QWidget>(new QWidget);
 auto *root=new QVBoxLayout(window.get());root->setContentsMargins(32,32,32,32);
 QWidget *panel=glass?new aurora::panel(static_cast<aurora::canvas*>(window.get()),28,true):new QWidget(window.get());root->addWidget(panel);
 auto *body=new QVBoxLayout(panel);body->setContentsMargins(22,22,22,22);body->addWidget(new QLabel("Matched Widgets memory scene"));auto *text=new QPlainTextEdit("A quiet place for a bright idea.\nSame ELF, layout, text and font.\n");body->addWidget(text);body->addWidget(new QPushButton("Save"));
 window->setGeometry(app.primaryScreen()->geometry());window->showFullScreen();
 QTimer::singleShot(350,[&]{xos::thread_stats stats{};xos::sdk::syscall(xos::sys_thread_stats,reinterpret_cast<xos::u64>(&stats));std::printf("WIDGETS_MEMORY mode=%s pages=%u threads=%u\n",glass?"aurora":"baseline",stats.process_user_pages,stats.threads);app.quit();});
 const auto code=app.exec();window.reset();return code;
}
