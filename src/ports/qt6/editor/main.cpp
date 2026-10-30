// SPDX-License-Identifier: Apache-2.0
#include "safe_file.hpp"
#include "../aurora/aurora.hpp"
#include "../aurora/style.hpp"
#include "../aurora/ssg.hpp"
#include "../aurora/ssg_pipe_provider.hpp"
#include <QtCore/QJsonDocument>
#include <memory>
#include <QtWidgets/QApplication>
#include <QtWidgets/QPlainTextEdit>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QLabel>
#include <QtWidgets/QVBoxLayout>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QStyleFactory>
#include <QtGui/QCloseEvent>
#include <QtGui/QShortcut>
#include <QtGui/QScreen>
#include <QtGui/QTextDocument>
#include <QtGui/QTextBlock>
#include <QtGui/QSyntaxHighlighter>
#include <QtGui/QKeyEvent>
#include <QtWidgets/QScrollBar>
#include <QtCore/QTimer>
#include <QtCore/QtPlugin>
#include <xos/thread_core.hpp>
#include <cstdio>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
class NoteHighlight final : public QSyntaxHighlighter {
    void highlightBlock(const QString &line) override {
        QTextCharFormat f;
        if(currentBlock().blockNumber()==0 && !line.isEmpty()) {f.setForeground(QColor(235,239,250));f.setProperty(QTextFormat::FontPixelSize,22);f.setFontWeight(QFont::DemiBold);setFormat(0,line.size(),f);}
        if(line.startsWith('#')) {f.setForeground(QColor(183,169,241));f.setProperty(QTextFormat::FontPixelSize,16);f.setFontWeight(QFont::Medium);setFormat(0,line.size(),f);}
    }
public:explicit NoteHighlight(QTextDocument *doc):QSyntaxHighlighter(doc){}
};
class Editor final : public aurora::Canvas {
    std::unique_ptr<aurora::QtScene> scene;
    std::unique_ptr<aurora::PipeProvider> pipe_provider;
    quint64 previous_scene=0;
    QString previous_epoch;
    void dump_scene(){if(!scene)return;const auto snapshot=scene->snapshot(false,"document");
        std::printf("SSG_NOTES_SNAPSHOT %s\n",QJsonDocument(snapshot).toJson(QJsonDocument::Compact).constData());
        std::printf("SSG_NOTES_DIFF %s\n",QJsonDocument(scene->diff(previous_scene,previous_epoch)).toJson(QJsonDocument::Compact).constData());
        previous_scene=snapshot["sceneVersion"].toString().toULongLong();previous_epoch=snapshot["sourceEpoch"].toString();}
    QLineEdit *path;
    QPlainTextEdit *text;
    QLabel *status,*fileTitle,*sideFile,*position;
    QWidget *confirmation;
    QPushButton *saveButton,*exitButton,*discardButton,*cancelButton;
    QByteArray original;
    QString loadedPath;
    bool loading=false, bom=false, crlf=false, uncertain=false;
    enum class Pending { None, Open, Quit } pending=Pending::None;
    QByteArray encode() const {
        auto bytes=text->toPlainText().toUtf8();
        if(crlf) bytes.replace("\n","\r\n");
        if(bom) bytes.prepend("\xef\xbb\xbf");
        return bytes;
    }
    void logPoint(const char *name,QWidget *w) {const auto p=w->mapToGlobal(w->rect().center());std::printf("EDITOR_POINT %s=%d,%d\n",name,p.x(),p.y());}
    void fileLabel() {
        const auto name=path->text().section('/',-1);
        sideFile->setText(sideFile->fontMetrics().elidedText(name,Qt::ElideMiddle,140));
        fileTitle->setText(fileTitle->fontMetrics().elidedText("LOCAL / "+name.toUpper(),Qt::ElideMiddle,460));
    }
    void message(const QString &s) {status->setText(s);std::printf("EDITOR_STATUS %s\n",s.toUtf8().constData());}
    void openFile() {
        QByteArray bytes;QString error;
        if(!xos_editor::read(path->text(),bytes,error)) {message("Open failed: "+error);return;}
        auto payload=bytes;const bool hasBom=payload.startsWith("\xef\xbb\xbf");
        if(hasBom) payload.remove(0,3);
        const auto decoded=QString::fromUtf8(payload);
        if(decoded.toUtf8()!=payload || payload.contains('\0')) {message("Open refused: requires valid UTF-8 text without NUL");return;}
        auto normalized=decoded;normalized.replace("\r\n","\n");
        if(normalized.contains('\r')) {message("Open refused: mixed/bare CR newline format");return;}
        const bool windows=payload.contains("\r\n");
        if(windows && payload.count('\n')!=payload.count("\r\n")){message("Open refused: mixed newline format");return;}
        // QTextDocument normalizes some Unicode separators; reject loss before loading.
        QTextDocument check;check.setPlainText(normalized);
        if(check.toPlainText()!=normalized){message("Open refused: unsupported Unicode paragraph separators");return;}
        fileLabel();
        loading=true;bom=hasBom;crlf=windows;original=bytes;loadedPath=path->text();
        text->setPlainText(normalized);text->document()->setModified(false);loading=false;uncertain=false;
        message(QString("Opened %1 bytes; UTF-8%2%3").arg(bytes.size()).arg(bom?" BOM":"").arg(crlf?" CRLF":" LF"));
        std::printf("EDITOR_OPEN_OK bytes=%lld\n",(long long)bytes.size());text->setFocus();
    }
    bool saveFile() {
        if(uncertain){message("Save blocked: prior commit outcome unknown; recover first");return false;}
        const auto bytes=encode();
        // Detect changes since load before replacing an existing file. This is a
        // consumer check, not a filesystem CAS or a concurrent-writer guarantee.
        if(path->text()==loadedPath) {
            QByteArray current;QString error;
            if(!xos_editor::read(loadedPath,current,error) || current!=original){message("Save refused: file changed or cannot be read; keep buffer");return false;}
        }
        const auto result=xos_editor::save(path->text(),bytes);
        uncertain=result.unknown;message(result.message);
        if(result.saved){fileLabel();original=bytes;loadedPath=path->text();text->document()->setModified(false);}
        return result.saved;
    }
    void request(Pending action) {
        if(text->document()->isModified() || uncertain) {
            pending=action;confirmation->show();
            QTimer::singleShot(0,this,[this]{logPoint("discard",discardButton);logPoint("cancel",cancelButton);});message("Unsaved changes: Save and continue, Discard, or Cancel");
            std::printf("EDITOR_UNSAVED_GUARD\n");
        } else perform(action);
    }
    void perform(Pending action) {
        confirmation->hide();pending=Pending::None;
        if(action==Pending::Open) openFile();
        else if(action==Pending::Quit){text->document()->setModified(false);QApplication::quit();}
    }
protected:
    bool eventFilter(QObject *o,QEvent *e) override {
        if(o==text && e->type()==QEvent::KeyPress) {const auto *key=static_cast<QKeyEvent*>(e);
            std::printf("EDITOR_KEY key=%d latency_ns=%llu\n",key->key(),(unsigned long long)(xos::thread::clock()-xos::u64(key->timestamp())*1000000));}
        return aurora::Canvas::eventFilter(o,e);
    }
    void closeEvent(QCloseEvent *event) override {event->ignore();request(Pending::Quit);}
public:
    explicit Editor(QString initial,bool ssg_probe=false,QString pipe_instance={},bool pipe_text=false) {
        setWindowTitle("Xylophone Notes — Aurora Glass");
        setStyleSheet("QLabel { color: #becce2; background: transparent; } QLineEdit { background: rgba(9,20,40,120); color: #e0eafa; border: 1px solid rgba(180,207,243,35); border-radius: 10px; padding: 6px 10px; selection-background-color: #536eb7; } QLineEdit:focus { border-color: #8abddf; } QPlainTextEdit { color: #dce4f3; background: transparent; border: 0; selection-background-color: #4a5e9d; selection-color: #ffffff; } QScrollBar:vertical { background: transparent; width: 7px; margin: 6px 0; } QScrollBar::handle:vertical { background: #52627e; border-radius: 3px; min-height: 28px; } QScrollBar::handle:vertical:hover { background: #8299bf; } QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height: 0px; } QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background: transparent; } QScrollBar:horizontal { background: transparent; height: 7px; } QScrollBar::handle:horizontal { background: #52627e; min-width: 28px; border-radius: 3px; } QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal { width: 0; }");
        auto *shell=new QHBoxLayout(this);shell->setContentsMargins(32,32,32,32);shell->setSpacing(32);
        auto *sidebar=new QWidget(this);sidebar->setFixedWidth(156);auto *nav=new QVBoxLayout(sidebar);nav->setContentsMargins(0,0,0,0);nav->setSpacing(14);
        nav->addWidget(new aurora::Brand);nav->addSpacing(14);
        auto caption=[&](QString title){auto *l=new QLabel(title);l->setStyleSheet("color: #9caecb; font-size: 10px; letter-spacing: 1px; padding: 5px 8px;");return l;};
        nav->addWidget(caption("WORKSPACE"));auto *current=new aurora::Button("Current note",true);current->setFixedHeight(42);nav->addWidget(current);
        nav->addSpacing(6);nav->addWidget(caption("LOCAL FILE"));sideFile=new QLabel("Untitled");sideFile->setTextFormat(Qt::PlainText);sideFile->setStyleSheet("color: #d4e1f4; font-size: 12px; padding: 0 8px;");sideFile->setWordWrap(true);nav->addWidget(sideFile);
        auto *local=new QLabel("UTF-8 document");local->setStyleSheet("color: #8fa9c6; font-size: 10px; padding: 0 8px;");nav->addWidget(local);nav->addSpacing(12);
        nav->addWidget(caption("QUICK KEYS"));auto *keys=new QLabel("Save                 Ctrl S\n\nOpen path       Ctrl O\n\nExit                      Esc");keys->setStyleSheet("font-size: 11px; color: #b3c3dc; padding: 0 8px;");nav->addWidget(keys);nav->addStretch();nav->addWidget(caption("AURORA GLASS"));
        auto *motto=new QLabel("A little more imagination.");motto->setStyleSheet("color: #8fa9c6; font-size: 10px; padding: 0 8px;");nav->addWidget(motto);shell->addWidget(sidebar);
        auto *column=new QVBoxLayout;column->setContentsMargins(0,0,0,0);column->setSpacing(18);shell->addLayout(column,1);
        auto *toolbar=new aurora::Panel(this,20);toolbar->setFixedHeight(54);auto *top=new QHBoxLayout(toolbar);top->setContentsMargins(10,8,10,8);top->setSpacing(8);
        path=new QLineEdit(initial);path->setObjectName("path");path->setMinimumWidth(100);path->setContextMenuPolicy(Qt::NoContextMenu);path->setPlaceholderText("/path/to/note.txt");path->setStyleSheet("font-size: 12px;");
        auto *open=new aurora::Button("Open");open->setFixedWidth(54);auto *save=new aurora::Button("Save",true);save->setFixedWidth(70);auto *quit=new aurora::Button("Exit");quit->setFixedWidth(44);
        saveButton=save;exitButton=quit;top->addWidget(path,1);top->addWidget(open);top->addWidget(save);top->addWidget(quit);column->addWidget(toolbar);
        auto *paper=new aurora::Panel(this,28,true);auto *body=new QVBoxLayout(paper);body->setContentsMargins(22,20,18,15);body->setSpacing(12);column->addWidget(paper,1);
        fileTitle=new QLabel("NEW DOCUMENT");fileTitle->setTextFormat(Qt::PlainText);fileTitle->setStyleSheet("color: #94a8c7; font-size: 10px; letter-spacing: 1px;");body->addWidget(fileTitle);
        text=new QPlainTextEdit; text->setObjectName("document");text->setContextMenuPolicy(Qt::NoContextMenu);text->setFrameShape(QFrame::NoFrame);text->setCursorWidth(1);text->setLineWrapMode(QPlainTextEdit::NoWrap);text->document()->setDocumentMargin(0);new NoteHighlight(text->document());body->addWidget(text,1);
        connect(current,&QPushButton::clicked,text,[this]{text->setFocus();});
        confirmation=new QWidget(this);auto *confirm=new QHBoxLayout(confirmation);confirm->setContentsMargins(0,0,0,0);confirm->setSpacing(6);
        auto *keep=new aurora::Button("Save and continue",true);auto *discard=new aurora::Button("Discard");auto *cancel=new aurora::Button("Cancel");
        discardButton=discard;cancelButton=cancel;confirm->addWidget(keep);confirm->addWidget(discard);confirm->addWidget(cancel);body->addWidget(confirmation);confirmation->hide();
        position=new QLabel("Ln 1, Col 1 · UTF-8");position->setStyleSheet("color: #8fa6c7; font-size: 10px;");body->addWidget(position);
        status=new QLabel("New document · Local files only");status->setTextFormat(Qt::PlainText);status->setStyleSheet("color: #a8c7c6; font-size: 10px;");status->setWordWrap(true);body->addWidget(status);
        connect(text,&QPlainTextEdit::cursorPositionChanged,this,[this]{const auto c=text->textCursor();position->setText(QString("Ln %1, Col %2  ·  %3 characters  ·  UTF-8%4").arg(c.blockNumber()+1).arg(c.positionInBlock()+1).arg(text->document()->characterCount()-1).arg(crlf?" CRLF":" LF"));});
        connect(open,&QPushButton::clicked,this,[this]{request(Pending::Open);});
        connect(save,&QPushButton::clicked,this,[this]{saveFile();});
        connect(quit,&QPushButton::clicked,this,[this]{request(Pending::Quit);});
        connect(keep,&QPushButton::clicked,this,[this]{if(saveFile()) perform(pending);});
        connect(discard,&QPushButton::clicked,this,[this]{perform(pending);});
        connect(cancel,&QPushButton::clicked,this,[this]{pending=Pending::None;confirmation->hide();text->setFocus();});
        auto shortcut=[this](QKeySequence seq,auto callback){auto *s=new QShortcut(seq,this);connect(s,&QShortcut::activated,this,callback);};
        shortcut(QKeySequence(Qt::CTRL|Qt::Key_S),[this]{saveFile();});
        shortcut(QKeySequence(Qt::CTRL|Qt::Key_O),[this]{path->setFocus();path->selectAll();});
        shortcut(QKeySequence(Qt::Key_Escape),[this]{request(Pending::Quit);});
        connect(path,&QLineEdit::returnPressed,this,[this]{request(Pending::Open);});
        connect(text,&QPlainTextEdit::textChanged,this,[this]{if(!loading){message("Modified — not saved");std::printf("EDITOR_CHANGE characters=%d\n",text->document()->characterCount()-1);}});
        connect(text,&QPlainTextEdit::selectionChanged,this,[this]{std::printf("EDITOR_SELECTION start=%d end=%d\n",text->textCursor().selectionStart(),text->textCursor().selectionEnd());});
        if(ssg_probe){scene=std::make_unique<aurora::QtScene>(this);scene->host_allow_observation(true);
            shortcut(QKeySequence(Qt::CTRL|Qt::Key_I),[this]{dump_scene();});}
        setGeometry(QApplication::primaryScreen()->geometry());showFullScreen();
        if(!initial.isEmpty()) openFile();text->setFocus();
        if(!pipe_instance.isEmpty()){
            if(!scene)scene=std::make_unique<aurora::QtScene>(this);
            scene->host_allow_observation(pipe_text);
            pipe_provider=std::make_unique<aurora::PipeProvider>(*scene,pipe_instance);
            pipe_provider->start();
            std::printf("SSG_PROVIDER_READY pid=%llu instance=%s text=%d\n",(unsigned long long)xos::sdk::pid(),pipe_instance.toUtf8().constData(),int(pipe_text));
        }
        auto *sampler=new QTimer(this);sampler->setInterval(1000);
        connect(sampler,&QTimer::timeout,this,[this]{xos::thread_stats stats{};
            xos::sdk::syscall(xos::sys_thread_stats,reinterpret_cast<xos::u64>(&stats));
            std::printf("EDITOR_SAMPLE pages=%u threads=%u scroll=%d cursor=%d\n",stats.process_user_pages,stats.threads,text->verticalScrollBar()->value(),text->textCursor().position());
        });sampler->start();
        QTimer::singleShot(250,this,[this,ssg_probe]{logPoint("save",saveButton);logPoint("exit",exitButton);logPoint("document",text->viewport());logPoint("path",path);
            if(scene && ssg_probe){std::printf("SSG_NOTES_TREE %s\n",QJsonDocument(scene->snapshot()).toJson(QJsonDocument::Compact).constData());dump_scene();}
            std::printf("QT_EDITOR_READY viewport=%dx%d\n",text->viewport()->width(),text->viewport()->height());});
    }
};
static void ipc_qt_message(QtMsgType,const QMessageLogContext &,const QString &message){
    std::printf("QT_MESSAGE %s\n",message.toUtf8().constData());
}
int main(int argc,char **argv) {
    QString instance;bool text_scope=false,probe=false;QString initial;
    for(int i=1;i<argc;++i){const QByteArray arg(argv[i]);
        if(arg=="--ssg-ipc-provider" && i+1<argc)instance=QString::fromLatin1(argv[++i]);
        else if(arg=="--ssg-ipc-text")text_scope=true;
        else if(arg=="--ssg-probe")probe=true;
        else if(!arg.startsWith('-') && initial.isEmpty())initial=QString::fromUtf8(arg);
    }
    if(!instance.isEmpty()){
        if(instance.size()!=32 || xos::sdk::syscall(xos::sys_process_stdio,0,0)!=0 ||
           xos::sdk::syscall(xos::sys_process_stdio,0,2)!=0){std::printf("SSG_PROVIDER_BAD_WIRING\n");return 2;}
        for(const auto c:instance)if(!((c>='0' && c<='9') || (c>='a' && c<='f')))return 2;
        qInstallMessageHandler(ipc_qt_message);
    }
    QApplication app(argc,argv);aurora::initialize(app);
    QFont font(QStringLiteral("DejaVu Sans"));font.setPixelSize(16);app.setFont(font);
    Editor editor(initial,probe,instance,text_scope);
    return app.exec();
}
