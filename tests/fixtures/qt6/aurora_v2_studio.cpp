// SPDX-License-Identifier: Apache-2.0
// Independent third-party consumer: only public Aurora headers and standard Qt.
#include "../../../src/ports/qt6/aurora/desktop.hpp"
#include "../../../src/ports/qt6/aurora/style.hpp"
#include <QtWidgets/QVBoxLayout>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QLabel>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QPlainTextEdit>
#include <QtGui/QScreen>
#include <QtGui/QShortcut>
#include <QtCore/QtPlugin>
#include <cstdlib>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
int main(int argc,char **argv) {
    QApplication app(argc,argv);aurora::initialize(app);
    const int bits=argc>1?std::atoi(argv[1]):16;
    auto prefs=aurora::preferences();prefs.scheme=bits&1?aurora::Scheme::daybreak:aurora::Scheme::midnight;
    prefs.high_contrast=bits&2;prefs.reduce_transparency=bits&4;prefs.reduce_motion=bits&8;prefs.quality=aurora::Quality((bits>>4)&3);prefs.glass_enabled=!(bits&64);
    aurora::set_preferences(prefs);aurora::desktop_surface window;
    auto *root=new QVBoxLayout(&window);root->setContentsMargins(60,56,60,56);
    auto *panel=new aurora::glass_panel(&window);root->addWidget(panel);
    auto *l=new QVBoxLayout(panel);l->setContentsMargins(28,24,28,24);l->setSpacing(16);
    l->addWidget(new QLabel("NORTHSTAR  /  Independent SDK Studio"));
    auto *field=new QLineEdit("Shared native controls");field->setMinimumHeight(36);l->addWidget(field);
    auto *row=new QHBoxLayout;l->addLayout(row);
    auto *theme=new QPushButton("Switch theme");theme->setMinimumHeight(38);row->addWidget(theme);
    auto *menu=new QPushButton("Menu");menu->setMinimumHeight(38);row->addWidget(menu);
    auto *disabled=new QPushButton("Disabled");disabled->setEnabled(false);row->addWidget(disabled);
    auto *editor=new QPlainTextEdit("Independent source; shared Aurora API.\nType, select, scroll and switch themes.");l->addWidget(editor);
    auto *notice=new QLabel("Menu closed");l->addWidget(notice);
    auto *menu_panel=new QWidget;auto *ml=new QHBoxLayout(menu_panel);
    auto *notify=new QPushButton("Notify");auto *close=new QPushButton("Close menu");ml->addWidget(notify);ml->addWidget(close);l->addWidget(menu_panel);menu_panel->hide();
    QObject::connect(theme,&QPushButton::clicked,[&]{auto p=aurora::preferences();p.scheme=p.scheme==aurora::Scheme::midnight?aurora::Scheme::daybreak:aurora::Scheme::midnight;aurora::set_preferences(p);std::printf("STUDIO_THEME %s\n",aurora::theme_json().constData());});
    QObject::connect(menu,&QPushButton::clicked,[&]{menu_panel->setVisible(!menu_panel->isVisible());std::printf("STUDIO_MENU visible=%d\n",menu_panel->isVisible());});
    QObject::connect(notify,&QPushButton::clicked,[&]{notice->setText("Notification delivered inside this application");std::printf("STUDIO_NOTICE\n");});
    QObject::connect(close,&QPushButton::clicked,[&]{menu_panel->hide();});
    QObject::connect(editor,&QPlainTextEdit::textChanged,[&]{std::printf("STUDIO_EDIT hex=%s\n",editor->toPlainText().toUtf8().toHex().constData());});
    auto *quit=new QShortcut(QKeySequence(Qt::Key_Escape),&window);QObject::connect(quit,&QShortcut::activated,&app,&QApplication::quit);
    window.setGeometry(app.primaryScreen()->geometry());window.showFullScreen();
    QTimer::singleShot(250,[&]{
        for(auto pair:{qMakePair("theme",static_cast<QWidget*>(theme)),qMakePair("menu",static_cast<QWidget*>(menu)),qMakePair("editor",static_cast<QWidget*>(editor))}){const auto p=pair.second->mapTo(&window,pair.second->rect().center());std::printf("STUDIO_POINT name=%s xy=%d,%d\n",pair.first,p.x(),p.y());}
        std::printf("STUDIO_READY\n");});return app.exec();
}
