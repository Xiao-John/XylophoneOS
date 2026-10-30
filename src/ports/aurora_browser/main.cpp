// SPDX-License-Identifier: Apache-2.0
#include "view.hpp"
#include "../qt6/aurora/aurora.hpp"
#include "../qt6/aurora/style.hpp"
#include "../qt6/aurora/ssg_pipe_provider.hpp"
#include <memory>
#include <QtWidgets/QApplication>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QLabel>
#include <QtWidgets/QTabBar>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QVBoxLayout>
#include <QtGui/QShortcut>
#include <QtCore/QtPlugin>
#include <QtGui/QScreen>
#include <cstdio>
#include <xos/thread_core.hpp>
#include <QtCore/QJsonDocument>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
class Browser final:public aurora::Canvas {
    browser::HtmlView *view;
    QString pipe_instance;bool pipe_text=false;
    std::unique_ptr<aurora::PipeProvider> pipe_provider;
    quint64 previous_scene=0;
    QString previous_epoch;
    void dump_scene(){
        // The legacy local probe must not expand a prewired consumer's scope.
        if(!pipe_instance.isEmpty() && !pipe_text){std::printf("SSG_BROWSER_PROBE DENIED\n");return;}
        view->allow_scene_observation(true);const auto snapshot=view->scene_snapshot("content");
        std::printf("SSG_BROWSER_SNAPSHOT %s\n",QJsonDocument(snapshot).toJson(QJsonDocument::Compact).constData());
        std::printf("SSG_BROWSER_DIFF %s\n",QJsonDocument(view->scene_diff(previous_scene,previous_epoch)).toJson(QJsonDocument::Compact).constData());
        previous_scene=snapshot["sceneVersion"].toString().toULongLong();previous_epoch=snapshot["sourceEpoch"].toString();}
    QLineEdit *address;
    QLabel *status,*title;
    aurora::Button *back,*forward;
    QStringList history;int index=-1;
    struct Tab{QStringList history;int index=-1,scroll=0;};
    Tab states[4];int active=0;QTabBar *tabbar;bool switching=false;
    void switchTab(int target){if(switching||target==active||target<0||target>3)return;
        const int previous=active;const auto old_history=history;const int old_index=index;
        states[active]={history,index,view->verticalScrollBar()->value()};
        active=target;history=states[active].history;index=states[active].index;
        const bool loaded=index<0?navigate("/web/start.html"):navigate(history[index],false);
        if(!loaded){active=previous;history=old_history;index=old_index;switching=true;tabbar->setCurrentIndex(previous);switching=false;updateButtons();return;}
        if(states[active].index>=0)view->verticalScrollBar()->setValue(states[active].scroll);
        std::printf("BROWSER_TAB active=%d history=%d\n",active,int(history.size()));}

    QStringList bookmarks;
    QWidget *bookmarkRow;
    void message(QString text){status->setText(text);std::printf("BROWSER_STATUS %s\n",text.toUtf8().constData());}
    void updateButtons(){back->setEnabled(index>0);forward->setEnabled(index+1<history.size());}
    bool navigate(QString url,bool record=true){
        QString path=browser::resolve(url,index>=0?history[index]:"/web/start.html");
        if(path.isEmpty()){message("Blocked: local /web pages only; HTTP / HTTPS unavailable");if(view->current().size())address->setText("file:"+view->current());return false;}
        QString error, candidate_title;message("Loading local page...");
        auto *candidate=new browser::HtmlView(this);
        candidate->resize(view->size());
        candidate->titleChanged=[&candidate_title](QString text){candidate_title=text;};
        if(!candidate->load(path,error)){delete candidate;if(view->current().size())address->setText("file:"+view->current());message("Page error: "+error);return false;}
        if(!pipe_instance.isEmpty())candidate->allow_scene_observation(pipe_text);
        candidate->navigate=[this](QString target){navigate(target);};
        candidate->titleChanged=[this](QString text){title->setText(text+" · Aurora");};
        candidate->setObjectName("page");
        auto *old=view;view=candidate;
        auto *item=layout()->replaceWidget(old,view);delete item;old->hide();view->show();old->deleteLater();
        title->setText(candidate_title+" · Aurora");address->setText("file:"+path);
        if(record){while(history.size()>index+1)history.removeLast();history.append(path);if(history.size()>16)history.removeFirst();index=history.size()-1;}
        tabbar->setTabText(active,title->text().section(" ·",0,0).left(19));updateButtons();message("Local page · liteHTML 0.9 · JavaScript off · network unavailable");view->setFocus();
        QTimer::singleShot(100,this,[this]{view->log_anchor_point();xos::thread_stats stats{};xos::sdk::syscall(xos::sys_thread_stats,reinterpret_cast<xos::u64>(&stats));std::printf("BROWSER_SAMPLE pages=%u threads=%u tab=%d scroll=%d\n",stats.process_user_pages,stats.threads,active,view->verticalScrollBar()->value());});
        return true;
    }
    void travel(int delta){const int target=index+delta;if(target<0||target>=history.size())return;if(navigate(history[target],false))index=target;updateButtons();}
    void point(const char *name,QWidget *w){auto p=w->mapToGlobal(w->rect().center());std::printf("BROWSER_POINT %s=%d,%d\n",name,p.x(),p.y());}
public:
    Browser(QString initial={},QString instance={},bool text_scope=false):pipe_instance(std::move(instance)),pipe_text(text_scope){setWindowTitle("Xylophone Browser — Aurora");resize(800,600);
        auto *layout=new QVBoxLayout(this);layout->setContentsMargins(32,30,32,26);layout->setSpacing(10);
        auto *tabs=new QHBoxLayout;title=new QLabel("Aurora / Start");title->setStyleSheet("color:#eef5ff;font-size:16px;font-weight:600;");tabs->addWidget(title,1);
        auto *newTab=new QLabel("LOCAL PREVIEW");newTab->setStyleSheet("color:#91cfdc;font-size:11px;");tabs->addWidget(newTab);
        auto *exit=new aurora::Button("Close");exit->setFixedSize(64,34);tabs->addWidget(exit);connect(exit,&QPushButton::clicked,qApp,&QApplication::quit);layout->addLayout(tabs);
        auto *tabrow=new QHBoxLayout;tabbar=new QTabBar;tabbar->setExpanding(false);tabbar->setDrawBase(false);tabbar->setStyleSheet("QTabBar::tab { background:#233751; color:#b9cfe7; padding:7px 17px; margin-right:5px; border:1px solid #456381; border-radius:10px; } QTabBar::tab:selected { background:#46617e; color:white; }");tabbar->addTab("Start");tabrow->addWidget(tabbar);auto *add=new aurora::Button("+");add->setFixedSize(32,30);tabrow->addWidget(add);tabrow->addStretch();layout->addLayout(tabrow);
        connect(tabbar,&QTabBar::currentChanged,this,[this](int target){switchTab(target);});connect(add,&QPushButton::clicked,this,[this]{if(tabbar->count()>=4){message("Tab limit: 4");return;}switching=true;int n=tabbar->addTab("New page");switching=false;tabbar->setCurrentIndex(n);});
        auto *toolbar=new aurora::Panel(this,23);auto *tools=new QHBoxLayout(toolbar);tools->setContentsMargins(10,8,10,8);tools->setSpacing(7);
        back=new aurora::Button("‹");forward=new aurora::Button("›");auto *reload=new aurora::Button("↻");auto *home=new aurora::Button("Home");
        for(auto *button:{back,forward,reload}){button->setFixedSize(36,34);tools->addWidget(button);}home->setFixedWidth(58);tools->addWidget(home);
        address=new QLineEdit;address->setMinimumHeight(34);address->setPlaceholderText("file:/web/start.html");tools->addWidget(address,1);auto *go=new aurora::Button("Go",true);go->setFixedWidth(45);tools->addWidget(go);layout->addWidget(toolbar);
        bookmarkRow=new QWidget;auto *marks=new QHBoxLayout(bookmarkRow);marks->setContentsMargins(0,0,0,0);marks->setSpacing(8);
        for(const auto &entry:{qMakePair(QString("Start"),QString("/web/start.html")),qMakePair(QString("Reading"),QString("/web/reading.html")),qMakePair(QString("CSS garden"),QString("/web/garden.html"))}){auto *button=new aurora::Button(entry.first);button->setMinimumHeight(28);marks->addWidget(button);connect(button,&QPushButton::clicked,this,[this,entry]{navigate(entry.second);});}
        auto *sessionRow=new QWidget;auto *sessionMarks=new QHBoxLayout(sessionRow);sessionMarks->setContentsMargins(0,0,0,0);sessionMarks->setSpacing(8);sessionMarks->addStretch();sessionRow->hide();auto *bookmark=new aurora::Button("+ Bookmark");marks->addWidget(bookmark);marks->addStretch();connect(bookmark,&QPushButton::clicked,this,[this,sessionMarks,sessionRow]{if(index<0||bookmarks.contains(history[index]))return;if(bookmarks.size()>=4){message("Session bookmark limit: 4");return;}auto path=history[index];bookmarks.append(path);auto *button=new aurora::Button(path.section('/',-1).left(10));button->setFixedWidth(116);sessionMarks->insertWidget(sessionMarks->count()-1,button);sessionRow->show();std::printf("BROWSER_BOOKMARK_ADDED path=%s count=%lld\n",path.toUtf8().constData(),(long long)bookmarks.size());connect(button,&QPushButton::clicked,this,[this,path]{navigate(path);});message("Bookmark added for this session");});layout->addWidget(bookmarkRow);layout->addWidget(sessionRow);
        view=new browser::HtmlView(this);view->setObjectName("page");layout->addWidget(view,1);
        status=new QLabel;status->setStyleSheet("color:#c0d0e5;font-size:10px;");status->setMinimumHeight(20);layout->addWidget(status);
        connect(back,&QPushButton::clicked,this,[this]{travel(-1);});connect(forward,&QPushButton::clicked,this,[this]{travel(1);});connect(reload,&QPushButton::clicked,this,[this]{if(index>=0)navigate(history[index],false);});connect(home,&QPushButton::clicked,this,[this]{navigate("/web/start.html");});connect(go,&QPushButton::clicked,this,[this]{navigate(address->text());});connect(address,&QLineEdit::returnPressed,this,[this]{navigate(address->text());});
        view->navigate=[this](QString path){navigate(path);};view->titleChanged=[this](QString text){title->setText(text+" · Aurora");};
        auto *newTabKey=new QShortcut(QKeySequence("Ctrl+T"),this);connect(newTabKey,&QShortcut::activated,add,&QPushButton::click);auto *cycleTab=new QShortcut(QKeySequence("Ctrl+Tab"),this);connect(cycleTab,&QShortcut::activated,this,[this]{tabbar->setCurrentIndex((active+1)%tabbar->count());});
        auto *focus=new QShortcut(QKeySequence("Ctrl+L"),this);connect(focus,&QShortcut::activated,this,[this]{address->setFocus();address->selectAll();});
        auto *previous=new QShortcut(QKeySequence("Alt+Left"),this);connect(previous,&QShortcut::activated,this,[this]{travel(-1);});auto *next=new QShortcut(QKeySequence("Alt+Right"),this);connect(next,&QShortcut::activated,this,[this]{travel(1);});auto *refresh=new QShortcut(QKeySequence("Ctrl+R"),this);connect(refresh,&QShortcut::activated,this,[this]{if(index>=0)navigate(history[index],false);});auto *quit=new QShortcut(QKeySequence(Qt::Key_Escape),this);connect(quit,&QShortcut::activated,qApp,&QApplication::quit);
        if(qApp->arguments().contains("--ssg-probe")){
            auto *ssg=new QShortcut(QKeySequence(Qt::CTRL|Qt::Key_I),this);
            connect(ssg,&QShortcut::activated,this,[this]{dump_scene();});
        }
        QTimer::singleShot(0,this,[this,bookmark,initial]{
            navigate(initial.isEmpty()?QStringLiteral("/web/start.html"):initial);
            if(!pipe_instance.isEmpty()){
                pipe_provider=std::make_unique<aurora::PipeProvider>(pipe_instance,
                    [this](bool visible,const QString &role,unsigned limit){return view->scene_snapshot(role,visible,limit);},
                    [this](quint64 version,const QString &epoch){return view->scene_diff(version,epoch);});
                pipe_provider->start();
                std::printf("SSG_PROVIDER_READY pid=%llu instance=%s text=%d kind=browser\n",(unsigned long long)xos::sdk::pid(),pipe_instance.toUtf8().constData(),int(pipe_text));
            }
            point("address",address);point("back",back);point("forward",forward);point("page",view);point("tabs",tabbar);point("bookmark",bookmark);std::printf("BROWSER_READY engine=litehtml-0.9 local_only=1 javascript=0\n");});
    }
};
static void ipc_qt_message(QtMsgType,const QMessageLogContext &,const QString &message){std::printf("QT_MESSAGE %s\n",message.toUtf8().constData());}
int main(int argc,char **argv){
    QString instance,initial;bool text_scope=false;
    for(int i=1;i<argc;++i){const QByteArray arg(argv[i]);
        if(arg=="--ssg-ipc-provider" && i+1<argc)instance=QString::fromLatin1(argv[++i]);
        else if(arg=="--ssg-ipc-text")text_scope=true;
        else if(!arg.startsWith('-') && initial.isEmpty())initial=QString::fromUtf8(arg);
    }
    if(!instance.isEmpty()){
        if(instance.size()!=32 || xos::sdk::syscall(xos::sys_process_stdio,0,0)!=0 || xos::sdk::syscall(xos::sys_process_stdio,0,2)!=0)return 2;
        for(const auto c:instance)if(!((c>='0' && c<='9') || (c>='a' && c<='f')))return 2;
        qInstallMessageHandler(ipc_qt_message);
    }
    QApplication app(argc,argv);aurora::initialize(app);Browser browser(initial,instance,text_scope);browser.show();return app.exec();
}
