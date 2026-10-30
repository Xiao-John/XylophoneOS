// SPDX-License-Identifier: Apache-2.0
#include "../../../src/ports/qt6/aurora/desktop.hpp"
#include "../../../src/ports/qt6/aurora/style.hpp"
#include <QtCore/QtPlugin>
#include <QtGui/QIcon>
#include <QtGui/QScreen>
#include <QtGui/QShortcut>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QVBoxLayout>
#include <cstdio>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)

int main(int argc,char **argv){
    QApplication app(argc,argv);aurora::initialize(app);aurora::DesktopSurface window;
    auto *layout=new QVBoxLayout(&window);layout->setContentsMargins(90,90,90,90);
    auto *button=new QPushButton("Icon action");QPixmap icon(24,24);icon.fill(QColor(255,0,255));
    button->setIcon(QIcon(icon));button->setIconSize(QSize(24,24));button->setMinimumHeight(64);layout->addWidget(button);
    auto *edit=new QLineEdit("Custom palette should survive theme changes");edit->setMinimumHeight(64);layout->addWidget(edit);layout->addStretch();
    auto *quit=new QShortcut(QKeySequence(Qt::Key_Escape),&window);QObject::connect(quit,&QShortcut::activated,&app,&QApplication::quit);
    window.setGeometry(app.primaryScreen()->geometry());window.showFullScreen();
    QTimer::singleShot(250,[&]{
        QPalette custom=edit->palette();custom.setColor(QPalette::Base,QColor("#197c35"));edit->setPalette(custom);
        aurora::set_preferences(aurora::preferences());
        QImage image(button->size(),QImage::Format_ARGB32_Premultiplied);image.fill(Qt::transparent);button->render(&image);
        int magenta=0;for(int y=0;y<image.height();++y)for(int x=0;x<image.width();++x){const auto c=image.pixelColor(x,y);if(c.red()>230 && c.blue()>230 && c.green()<20)++magenta;}
        QImage field(edit->size(),QImage::Format_ARGB32_Premultiplied);field.fill(Qt::transparent);edit->render(&field);
        int green=0;for(int y=0;y<field.height();++y)for(int x=0;x<field.width();++x){const auto c=field.pixelColor(x,y);if(c==QColor("#197c35"))++green;}
        const bool icon_ok=magenta>100, palette_ok=edit->palette().color(QPalette::Base)==QColor("#197c35"), paint_ok=green>100;
        std::printf("AURORA_STANDARD_CHECK button_icon=%s pixels=%d\n",icon_ok?"PASS":"FAIL",magenta);
        std::printf("AURORA_STANDARD_CHECK explicit_palette=%s\n",palette_ok?"PASS":"FAIL");
        std::printf("AURORA_STANDARD_CHECK palette_painted=%s pixels=%d\n",paint_ok?"PASS":"FAIL",green);
        std::printf("AURORA_STANDARD_READY failures=%d\n",int(!icon_ok)+int(!palette_ok)+int(!paint_ok));
    });return app.exec();
}
