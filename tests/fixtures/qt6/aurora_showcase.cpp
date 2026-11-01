// SPDX-License-Identifier: Apache-2.0
#include "../../../src/ports/qt6/aurora/aurora.hpp"
#include "../../../src/ports/qt6/aurora/style.hpp"
#include <QtWidgets/QLabel>
#include <QtWidgets/QVBoxLayout>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QPlainTextEdit>
#include <QtGui/QScreen>
#include <QtGui/QShortcut>
#include <QtCore/QtPlugin>
#include <cstdio>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
int main(int argc,char **argv){
 QApplication app(argc,argv);aurora::initialize(app);aurora::canvas window;
 auto *root=new QVBoxLayout(&window);root->setContentsMargins(70,60,70,60);
 auto *panel=new aurora::panel(&window,28,true);root->addWidget(panel);auto *layout=new QVBoxLayout(panel);layout->setContentsMargins(26,26,26,26);
 layout->addWidget(new QLabel("Xylophone Aurora Glass | Native Widgets style"));
 auto *path=new QLineEdit("A reusable QProxyStyle + QPalette");layout->addWidget(path);
 auto *buttons=new QHBoxLayout;
 for(QString name:{"Standard","Primary","Disabled"}){auto *b=new QPushButton(name);b->setMinimumHeight(38);if(name=="Primary")b->setDefault(true);if(name=="Disabled")b->setEnabled(false);buttons->addWidget(b);}
 layout->addLayout(buttons);auto *text=new QPlainTextEdit("These are standard Qt Widgets.\nAurora is selected by aurora::initialize(app).\nNo editor-specific painting is required.");layout->addWidget(text);
 auto *exit=new QShortcut(QKeySequence(Qt::Key_Escape),&window);QObject::connect(exit,&QShortcut::activated,&app,&QApplication::quit);
 window.setGeometry(app.primaryScreen()->geometry());window.showFullScreen();
 QTimer::singleShot(250,[&]{std::printf("AURORA_SHOWCASE_READY app=%08x window=%08x text=%08x inactive=%08x disabled=%08x\n",app.palette().color(QPalette::Text).rgba(),window.palette().color(QPalette::WindowText).rgba(),text->palette().color(QPalette::Text).rgba(),text->palette().color(QPalette::Inactive,QPalette::Text).rgba(),text->palette().color(QPalette::Disabled,QPalette::Text).rgba());});if(argc>1)QTimer::singleShot(1600,&app,&QApplication::quit);return app.exec();
}
