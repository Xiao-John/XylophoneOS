// SPDX-License-Identifier: Apache-2.0
#include "../qt6/aurora/desktop.hpp"
#include "../qt6/aurora/style.hpp"
#include <QtWidgets/QLabel>
#include <QtWidgets/QVBoxLayout>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QStackedWidget>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QPlainTextEdit>
#include <QtWidgets/QCheckBox>
#include <QtGui/QScreen>
#include <QtGui/QShortcut>
#include <QtCore/QtPlugin>
#include <xos/sdk.hpp>
#include <xos/thread_core.hpp>
#include <cstdlib>
#include <functional>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
namespace {
class Desktop final : public aurora::DesktopSurface {
    aurora::GlassPanel *bar, *dock, *card;
    QStackedWidget *pages;
    QLabel *toast, *heading, *subtitle;
    QList<QPushButton*> controls;
    QCheckBox *contrast, *opaque, *motion, *glass;
    QElapsedTimer elapsed;
    int page=0;
    bool session_mode=false;
    QPushButton *button(QString name,QBoxLayout *layout,std::function<void()> action,bool accent=false) {
        auto *b=new QPushButton(name);b->setMinimumHeight(aurora::tokens().control_height);
        b->setProperty("auroraAccent",accent);b->setAccessibleName(name);b->setToolTip(QString());
        controls.append(b);layout->addWidget(b);connect(b,&QPushButton::clicked,this,[this,name,action]{
            const auto start=elapsed.elapsed();action();std::printf("DESKTOP_ACTION name=%s elapsed_ms=%lld\n",name.toUtf8().constData(),(long long)(elapsed.elapsed()-start));
        });return b;
    }
    QLabel *label(QString text,QVBoxLayout *l,int size=15) {
        auto *w=new QLabel(text);w->setWordWrap(true);auto f=w->font();f.setPixelSize(size);w->setFont(f);l->addWidget(w);return w;
    }
    QVBoxLayout *new_page() {auto *w=new QWidget;auto *l=new QVBoxLayout(w);l->setContentsMargins(24,20,24,20);l->setSpacing(12);pages->addWidget(w);return l;}
    void notify(const QString &text) {toast->setText(text);toast->show();toast->raise();std::printf("DESKTOP_NOTICE %s\n",text.toUtf8().constData());}
    void points() {
        for(auto *b:controls)if(b->isVisible()){const auto pos=b->mapTo(this,b->rect().center());std::printf("DESKTOP_POINT name=%s xy=%d,%d\n",b->text().toUtf8().constData(),pos.x(),pos.y());}
        for(auto *b:{contrast,opaque,motion,glass})if(b->isVisible()){const auto pos=b->mapTo(this,QPoint(10,b->height()/2));std::printf("DESKTOP_POINT name=%s xy=%d,%d\n",b->text().toUtf8().constData(),pos.x(),pos.y());}
    }
    void select(int index) {page=index;card->show();pages->setCurrentIndex(index);std::printf("DESKTOP_PAGE index=%d\n",index);QTimer::singleShot(50,this,[this]{points();});}
    void apply() {
        auto prefs=aurora::preferences();prefs.high_contrast=contrast->isChecked();
        prefs.reduce_transparency=opaque->isChecked();prefs.reduce_motion=motion->isChecked();prefs.glass_enabled=glass->isChecked();
        aurora::set_preferences(prefs);arrange();
        notify("Appearance updated for this desktop session");
        std::printf("DESKTOP_THEME_JSON %s\n",aurora::theme_json().constData());
        QTimer::singleShot(50,this,[this]{points();});
    }
    void scheme(aurora::Scheme value) {auto p=aurora::preferences();p.scheme=value;aurora::set_preferences(p);apply();}
    void launch(int id) {
        if(!session_mode){notify("Preview mode. Start the desktop session to open apps.");return;}
        const auto p=aurora::preferences();const int bits=(p.scheme==aurora::Scheme::daybreak?1:0)|(p.high_contrast?2:0)|(p.reduce_transparency?4:0)|(p.reduce_motion?8:0)|(int(p.quality)<<4)|(p.glass_enabled?0:64);
        // A normal process exit, interpreted only by our unprivileged session parent.
        std::printf("DESKTOP_HANDOFF app=%d preferences=%d\n",id,bits);qApp->exit(16+bits*8+id);
    }
    void arrange() {
        const bool day=aurora::preferences().scheme==aurora::Scheme::daybreak;
        bar->setGeometry(20,16,width()-40,48);
        dock->setGeometry(day?QRect(20,88,140,height()-108):QRect(90,height()-70,width()-180,50));
        auto *layout=qobject_cast<QBoxLayout*>(dock->layout());layout->setDirection(day?QBoxLayout::TopToBottom:QBoxLayout::LeftToRight);
        heading->setGeometry(day?188:42,day?84:88,width()-(day?215:84),44);
        subtitle->setGeometry(day?190:44,day?131:137,width()-(day?215:88),26);
        card->setGeometry(day?QRect(184,176,width()-208,height()-204):QRect(40,182,width()-80,height()-270));
        pages->setGeometry(0,0,card->width(),card->height());toast->setGeometry(width()-326,74,300,44);
        const auto t=aurora::tokens();auto f=heading->font();f.setPixelSize(day?28:32);f.setBold(true);heading->setFont(f);
        heading->setText(day?"Daybreak Atelier":"A little space to create.");
        subtitle->setText(day?"Quiet light. Clear focus. Your Xylophone desktop.":"MIDNIGHT CURRENT   /   Xylophone Aurora Glass");
        update();
    }
protected:
    void resizeEvent(QResizeEvent *e) override {DesktopSurface::resizeEvent(e);if(bar)arrange();}
public:
    Desktop(int bits,const QString &last,bool session):bar(nullptr),dock(nullptr),card(nullptr) {
        session_mode=session;elapsed.start();auto p=aurora::preferences();p.scheme=bits&1?aurora::Scheme::daybreak:aurora::Scheme::midnight;
        p.high_contrast=bits&2;p.reduce_transparency=bits&4;p.reduce_motion=bits&8;p.quality=aurora::Quality((bits>>4)&3);p.glass_enabled=!(bits&64);aurora::set_preferences(p);
        bar=new aurora::GlassPanel(this);auto *top=new QHBoxLayout(bar);top->setContentsMargins(18,6,12,6);
        auto *brand=new QLabel("X Y L O P H O N E");auto font=brand->font();font.setBold(true);brand->setFont(font);top->addWidget(brand);top->addStretch();
        top->addWidget(new QLabel("Aurora  /  Single-app session"));button("Exit",top,[]{qApp->quit();});
        heading=new QLabel(this);subtitle=new QLabel(this);
        dock=new aurora::GlassPanel(this);auto *nav=new QBoxLayout(QBoxLayout::LeftToRight,dock);nav->setContentsMargins(10,6,10,6);nav->setSpacing(8);
        button("Home",nav,[this]{select(0);});button("Apps",nav,[this]{select(1);});
        button("Studio",nav,[this]{select(2);});button("Settings",nav,[this]{select(3);});
        button("Quality",nav,[this]{select(5);});
        button("Hide",nav,[this]{card->hide();notify("Panel hidden. Home restores it.");});
        card=new aurora::GlassPanel(this);pages=new QStackedWidget(card);
        auto *home=new_page();label("YOUR WORKSPACE",home,12);label("Make room for the next idea.",home,24);
        label("A native desktop built around calm materials, clear controls and your own applications.",home);
        home->addStretch();auto *quick=new QHBoxLayout;home->addLayout(quick);
        button("Notes",quick,[this]{launch(1);},true);button("Browser",quick,[this]{launch(2);});button("Explore components",quick,[this]{select(2);});
        label("Apps open one at a time. Closing an app returns to this desktop.",home,12);
        auto *apps=new_page();label("APPLICATIONS",apps,12);label("Your tools, within reach.",apps,24);
        label("Choose an app. When it closes, return to your workspace.",apps);
        auto *tiles=new QHBoxLayout;apps->addLayout(tiles);button("Aurora Notes",tiles,[this]{launch(1);},true);
        button("Xylophone Browser",tiles,[this]{launch(2);});button("SDK Studio",tiles,[this]{launch(3);});
        apps->addStretch();label("LocalPilot: platform support in progress.",apps,12);
        auto *studio=new_page();label("NATIVE COMPONENT STUDIO",studio,12);
        auto *field=new QLineEdit;field->setPlaceholderText("A standard Qt text field. Try typing here.");field->setMinimumHeight(36);studio->addWidget(field);
        auto *row=new QHBoxLayout;studio->addLayout(row);button("Primary action",row,[this]{notify("Native button activated");},true);
        button("Menu",row,[this]{select(4);});auto *disabled=button("Unavailable",row,[]{});disabled->setEnabled(false);
        auto *editor=new QPlainTextEdit("A real Qt text editor.\nShared palette, shared focus states.\nTab moves focus; Escape returns home.");editor->setAccessibleName("Studio document");studio->addWidget(editor);
        connect(editor,&QPlainTextEdit::textChanged,this,[editor]{std::printf("DESKTOP_EDIT hex=%s\n",editor->toPlainText().toUtf8().toHex().constData());});
        auto *settings=new_page();label("APPEARANCE",settings,12);
        auto *themes=new QHBoxLayout;settings->addLayout(themes);button("Midnight Current",themes,[this]{scheme(aurora::Scheme::midnight);});button("Daybreak Atelier",themes,[this]{scheme(aurora::Scheme::daybreak);});
        contrast=new QCheckBox("Increase contrast");opaque=new QCheckBox("Reduce transparency");motion=new QCheckBox("Reduce motion");
        contrast->setChecked(p.high_contrast);opaque->setChecked(p.reduce_transparency);motion->setChecked(p.reduce_motion);
        for(auto *check:{contrast,opaque,motion}){settings->addWidget(check);connect(check,&QCheckBox::toggled,this,[this]{apply();});}
        auto *wall=new QHBoxLayout;settings->addLayout(wall);button("Tidal wallpaper",wall,[this]{set_wallpaper(0);notify("Tidal wallpaper selected");});button("Ribbon wallpaper",wall,[this]{set_wallpaper(1);notify("Ribbon wallpaper selected");});
        label("These appearance preferences apply to this desktop session.",settings,12);
        auto *menu=new_page();label("STUDIO MENU",menu,12);label("In-surface menu",menu,24);
        label("Keyboard-accessible child controls. Native popup windows await the window protocol.",menu);
        button("Send notification",menu,[this]{notify("Hello from the native component menu");});
        button("Back to Studio",menu,[this]{select(2);});menu->addStretch();
        auto *quality=new_page();label("MATERIAL QUALITY",quality,12);
        label("Choose the cost of light.",quality,24);
        auto *levels=new QHBoxLayout;quality->addLayout(levels);
        for(int i=0;i<4;++i){const QString names[]={"High","Balanced","Low","Safe"};button(names[i],levels,[this,i]{auto p=aurora::preferences();p.quality=aurora::Quality(i);aurora::set_preferences(p);notify("Quality updated. Effects may lower to stay responsive.");});}
        glass=new QCheckBox("Enable glass effects");glass->setChecked(p.glass_enabled);quality->addWidget(glass);
        connect(glass,&QCheckBox::toggled,this,[this]{apply();});
        label("High: fine blur. Balanced: cached soft glass. Low: coarse blur. Safe: opaque native controls, no backdrop blur.",quality);
        label("Disabling glass selects an ordinary opaque theme. Cache budget or slow generation can lower the effective quality.",quality,12);
        quality->addStretch();
        toast=new QLabel(this);toast->setWordWrap(true);toast->setMargin(10);toast->setAutoFillBackground(true);toast->hide();
        auto shortcut=[this](const QKeySequence &key,auto action){auto *s=new QShortcut(key,this);connect(s,&QShortcut::activated,this,action);};
        shortcut(QKeySequence(Qt::CTRL|Qt::Key_Comma),[this]{select(3);});
        shortcut(QKeySequence(Qt::CTRL|Qt::Key_L),[this]{select(1);});
        shortcut(QKeySequence(Qt::CTRL|Qt::Key_D),[this]{scheme(aurora::preferences().scheme==aurora::Scheme::midnight?aurora::Scheme::daybreak:aurora::Scheme::midnight);});
        shortcut(QKeySequence(Qt::Key_Escape),[this]{if(page!=0 || !card->isVisible())select(0);else qApp->quit();});
        shortcut(QKeySequence(Qt::CTRL|Qt::Key_Q),[]{qApp->quit();});
        if(!last.isEmpty())notify(last);
        QTimer::singleShot(250,this,[this]{
            std::printf("DESKTOP_READY width=%d height=%d theme=%s\n",width(),height(),aurora::theme_json().constData());
            points();
            xos::thread_stats s{};xos::sdk::syscall(xos::sys_thread_stats,reinterpret_cast<xos::u64>(&s));
            std::printf("DESKTOP_SAMPLE pages=%u threads=%u startup_ms=%lld\n",s.process_user_pages,s.threads,(long long)elapsed.elapsed());
        });
    }
};
}
int main(int argc,char **argv) {
    QApplication app(argc,argv);aurora::initialize(app);
    Desktop window(argc>1?std::atoi(argv[1]):16,argc>2?QString::fromUtf8(argv[2]):QString(),argc>2);
    window.setGeometry(app.primaryScreen()->geometry());window.showFullScreen();return app.exec();
}
