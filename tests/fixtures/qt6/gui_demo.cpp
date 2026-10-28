// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QWindow>
#include <QScreen>
#include <QBackingStore>
#include <QPainter>
#include <QFontDatabase>
#include <QFontInfo>
#include <QTimer>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QEventLoop>
#include <QFile>
#include <QImage>
#include <QThread>
#include <vector>
#include <memory>
#include <thread>
#include <QtPlugin>
#include <xos/thread_core.hpp>
#include <cstdio>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
extern "C" void xos_qpa_pause_input(unsigned);

class Demo final : public QWindow {
    QBackingStore store{this};
    QTimer animation;
    int frame=0, clicks=0;
    QString typed;
    QPoint mouse{400,300};
    bool down=false;
    bool pixelProbe=false, overflowProbe=false;
    xos::u32 peak=0,samples=0;
    void paint(QRegion dirty) {
        if(!isExposed()) return;
        const auto start=xos::thread::clock();
        store.resize(size());
        store.beginPaint(dirty);
        QPainter p(store.paintDevice());
        p.setClipRegion(dirty);
        p.fillRect(QRect(QPoint(),size()),QColor(17,24,39));
        p.fillRect(0,0,width(),8,QColor(45,212,191));
        p.setPen(QColor(241,245,249));
        QFont title(QStringLiteral("DejaVu Sans")); title.setPixelSize(32);p.setFont(title);
        p.drawText(40,65,QStringLiteral("XylophoneOS / Qt 6.8.3"));
        QFont body(QStringLiteral("DejaVu Sans"));body.setPixelSize(18);p.setFont(body);
        p.setPen(QColor(148,163,184));p.drawText(40,100,QStringLiteral("QtGui + XOS QPA  |  CPU raster  |  Display Service"));
        const QColor colors[]={QColor(239,68,68),QColor(245,158,11),QColor(52,211,153),QColor(56,189,248)};
        for(int i=0;i<4;++i) p.fillRect(40+i*175,135,155,80,colors[i]);
        p.setPen(QPen(QColor(94,234,212),3));p.drawLine(40,235,width()-40,235);
        p.setPen(Qt::white);p.drawText(40,280,QStringLiteral("Keyboard: ")+typed);
        p.drawText(40,320,QStringLiteral("Mouse: %1, %2   clicks: %3").arg(mouse.x()).arg(mouse.y()).arg(clicks));
        p.fillRect(40,350,200,50,down?QColor(245,158,11):QColor(30,41,59));
        p.drawText(55,382,down?QStringLiteral("PRESSED"):QStringLiteral("Click anywhere"));
        p.setPen(QColor(148,163,184));p.drawText(40,450,QStringLiteral("Type English / Shift / Ctrl / Alt. Release Esc to exit."));
        p.fillRect(40,height()-90,width()-80,50,QColor(30,41,59));
        p.fillRect(40+(frame%20)*((width()-100)/20),height()-85,20,40,QColor(45,212,191));
        p.setPen(Qt::white);p.drawText(width()-230,height()-57,QStringLiteral("Timer frame %1").arg(frame));
        p.end();store.endPaint();store.flush(dirty);
        xos::thread_stats stats{};
        if(xos::sdk::syscall(xos::sys_thread_stats,reinterpret_cast<xos::u64>(&stats))==0){
            peak=qMax(peak,stats.process_user_pages);++samples;
        }
        std::printf("[qt-demo] paint frame=%d ns=%llu sampled_pages=%u threads=%u\n",frame,
            (unsigned long long)(xos::thread::clock()-start),stats.process_user_pages,stats.threads);
    }
public:
    explicit Demo(bool pixels=false, bool idle=false, bool overflow=false) : pixelProbe(pixels), overflowProbe(overflow) {
        setSurfaceType(QSurface::RasterSurface);setGeometry(screen()->geometry());
        animation.setInterval(250);
        QObject::connect(&animation,&QTimer::timeout,[this]{++frame;paint(QRect(40,height()-90,width()-80,50));});
        if(!pixelProbe && !idle) animation.start();
    }
    ~Demo() override {
        std::printf("QT_GUI_MEMORY sampled_peak_user_pages=%u samples=%u page_bytes=4096\n",peak,samples);
    }
protected:
    void exposeEvent(QExposeEvent *) override {
        paint(QRect(QPoint(),size()));
        if(pixelProbe && isExposed()) {
            QRegion edges=QRegion(QRect(-10,-10,30,30))|QRegion(QRect(width()-10,height()-10,30,30));
            store.beginPaint(edges);
            QPainter p(store.paintDevice());p.setClipRegion(edges);
            p.fillRect(-10,-10,30,30,QColor(0x12,0x34,0x56));
            p.fillRect(width()-10,height()-10,30,30,QColor(0xab,0xcd,0xef));
            p.end();store.endPaint();store.flush(edges);
            auto *image=dynamic_cast<QImage*>(store.paintDevice());
            QFile f(QStringLiteral("/qtframe.bin"));
            if(!image || !f.open(QIODevice::WriteOnly) || f.write(reinterpret_cast<const char*>(image->constBits()),image->sizeInBytes())!=image->sizeInBytes())
                qFatal("Qt pixel reference write failed");
            f.close();std::printf("QT_GUI_PIXEL_REFERENCE_READY bytes=%lld\n",(long long)image->sizeInBytes());
        }
    }
    void keyPressEvent(QKeyEvent *e) override {
        std::printf("[qt-key] press key=%d mods=%u text=%s latency_ns=%llu\n",e->key(),unsigned(e->modifiers().toInt()),e->text().toUtf8().constData(),
            (unsigned long long)(xos::thread::clock()-xos::u64(e->timestamp())*1000000));
        if(overflowProbe && e->key()==Qt::Key_P){xos_qpa_pause_input(1800);std::printf("QT_INPUT_PAUSE_ARMED\n");}
        if(e->key()==Qt::Key_Backspace) typed.chop(1);else typed+=e->text();
        paint(QRect(30,245,width()-60,50));
    }
    void keyReleaseEvent(QKeyEvent *e) override {
        std::printf("[qt-key] release key=%d mods=%u\n",e->key(),unsigned(e->modifiers().toInt()));
        if(e->key()==Qt::Key_Escape) close();
    }
    void mouseMoveEvent(QMouseEvent *e) override {
        mouse=e->position().toPoint();std::printf("[qt-mouse] move x=%d y=%d buttons=%u\n",mouse.x(),mouse.y(),unsigned(e->buttons().toInt()));
        paint(QRect(30,295,width()-60,110));
    }
    void mousePressEvent(QMouseEvent *e) override {
        ++clicks;down=true;std::printf("[qt-mouse] press button=%u\n",unsigned(e->button()));paint(QRect(30,295,width()-60,110));
    }
    void mouseReleaseEvent(QMouseEvent *e) override {
        down=false;std::printf("[qt-mouse] release button=%u\n",unsigned(e->button()));paint(QRect(30,295,width()-60,110));
    }
    bool event(QEvent *e) override {
        if(e->type()==QEvent::FocusIn || e->type()==QEvent::FocusOut)
            std::printf("[qt-focus] active=%d\n",e->type()==QEvent::FocusIn);
        return QWindow::event(e);
    }
};
int main(int argc,char **argv) {
    std::printf("QT_GUI_ENTER\n");
    QGuiApplication app(argc,argv);
    const auto mode=argc>1?QByteArray(argv[1]):QByteArray("hold");
    QFont font(QStringLiteral("DejaVu Sans"));font.setPixelSize(18);
    QFontInfo info(font);
    if(info.family()!=QStringLiteral("DejaVu Sans")) return 73;
    std::printf("QT_GUI_FONT family=%s pixel=%d\n",info.family().toUtf8().constData(),info.pixelSize());
    std::vector<std::unique_ptr<QThread>> quota;
    if(mode=="quota") {
        for(int i=0;i<3;++i) { quota.emplace_back(QThread::create([]{QThread::sleep(5);}));quota.back()->start(); }
    }
    const int count=mode=="repeat"?3:1;
    app.setQuitOnLastWindowClosed(false);
    for(int i=0;i<count;++i) {
        xos::thread_stats before{};
        xos::sdk::syscall(xos::sys_thread_stats,reinterpret_cast<xos::u64>(&before));
        Demo w(mode=="pixels",mode=="idle",mode=="overflow");w.show();
        std::unique_ptr<std::thread> idleSampler;
        if(mode=="idle") {
            idleSampler=std::make_unique<std::thread>([&app]{
                QThread::msleep(500);
                xos::thread_stats stats{};
                xos::sdk::syscall(xos::sys_thread_stats,reinterpret_cast<xos::u64>(&stats));
                std::printf("QT_GUI_IDLE waiting=%u threads=%u\n",stats.waiting,stats.threads);
                QMetaObject::invokeMethod(&app,[&app]{app.quit();},Qt::QueuedConnection);
            });
        }
        if(mode=="focus") {
            QTimer::singleShot(250,&w,&QWindow::hide);
            QTimer::singleShot(500,[&w]{
                if(QGuiApplication::focusWindow()) qFatal("Hidden Qt window kept GUI focus");
                std::printf("QT_GUI_FOCUS_OUT_OK\n");w.show();
            });
            QTimer::singleShot(800,[&w,&app]{
                if(QGuiApplication::focusWindow()!=&w) qFatal("Shown Qt window missing focus");
                std::printf("QT_GUI_FOCUS_IN_OK\n");w.close();app.quit();
            });
        }
        if(mode=="oom") QTimer::singleShot(500,[]{
            QImage huge(32000,32000,QImage::Format_RGB32);
            if(!huge.isNull()) qFatal("Expected real Qt image quota failure");
            std::printf("QT_GUI_IMAGE_OOM_NULL_OK\n");QCoreApplication::quit();
        });
        if(mode=="fault") QTimer::singleShot(800,[]{std::printf("QT_GUI_FAULT_TRIGGER\n");asm volatile("ud2");});
        if(mode=="second") QTimer::singleShot(800,[]{auto *w2=new Demo;w2->show();});
        if(mode=="auto" || mode=="repeat") QTimer::singleShot(1200,&w,&QWindow::close);
        QObject::connect(&w,&QWindow::visibleChanged,[&](bool v){if(!v && mode!="focus") app.quit();});
        std::printf("QT_GUI_READY cycle=%d\n",i);
        const int rc=app.exec();
        if(idleSampler) idleSampler->join();
        w.destroy();
        xos::thread_stats after{};
        xos::sdk::syscall(xos::sys_thread_stats,reinterpret_cast<xos::u64>(&after));
        std::printf("QT_GUI_TEARDOWN threads_before=%u threads_after=%u stacks_before=%u stacks_after=%u\n",
            before.threads,after.threads,before.process_kernel_stack_pages,after.process_kernel_stack_pages);
        if(before.threads!=after.threads || before.process_kernel_stack_pages!=after.process_kernel_stack_pages) return 74;
        if(rc) return rc;
    }
    for(auto &thread:quota) thread->wait();
    std::printf("QT_GUI_OK\n");return 0;
}
