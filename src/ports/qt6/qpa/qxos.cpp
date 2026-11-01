// SPDX-License-Identifier: Apache-2.0
// Qt 6.8.3 private QPA API. No framebuffer mapping or application-name privilege.
#include <QtCore/QCoreApplication>
#include <QtCore/QFile>
#include <QtCore/QMutex>
#include <QtCore/QMutexLocker>
#include <QtCore/QPointer>
#include <QtCore/QThread>
#include <QtGui/QWindow>
#include <QtGui/QScreen>
#include <QtGui/QGuiApplication>
#include <QtGui/QImage>
#include <QtGui/QRegion>
#include <qpa/qplatformintegrationplugin.h>
#include <qpa/qplatformintegration.h>
#include <qpa/qplatformscreen.h>
#include <qpa/qplatformwindow.h>
#include <qpa/qplatformbackingstore.h>
#include <qpa/qwindowsysteminterface.h>
#include <private/qfreetypefontdatabase_p.h>
#include "qeventdispatcher_xos_p.h"
#include <xos/display_client.hpp>
#include <atomic>
#include <memory>
#include <cstdio>
#include <pthread.h>

namespace {
using WSI = QWindowSystemInterface;
// Compose, rather than fork, the qualified E15 dispatcher. QPA owns only the
// GUI queue drain; all deadlines, posted events and wake words remain in Core.
class gui_dispatcher final : public QAbstractEventDispatcherV2 {
    QEventDispatcherXos core;
public:
    gui_dispatcher() {
        QObject::connect(&core, &QAbstractEventDispatcher::awake, this, &QAbstractEventDispatcher::awake);
        QObject::connect(&core, &QAbstractEventDispatcher::aboutToBlock, this, &QAbstractEventDispatcher::aboutToBlock);
    }
    bool processEvents(QEventLoop::ProcessEventsFlags f) override {
        const bool sent = WSI::sendWindowSystemEvents(f);
        if (sent) f &= ~QEventLoop::WaitForMoreEvents;
        const bool result = core.processEvents(f);
        return WSI::sendWindowSystemEvents(f) || sent || result;
    }
    void registerSocketNotifier(QSocketNotifier *n) override { core.registerSocketNotifier(n); }
    void unregisterSocketNotifier(QSocketNotifier *n) override { core.unregisterSocketNotifier(n); }
    void registerTimer(Qt::TimerId id, Duration d, Qt::TimerType t, QObject *o) override { core.registerTimer(id,d,t,o); }
    bool unregisterTimer(Qt::TimerId id) override { return core.unregisterTimer(id); }
    bool unregisterTimers(QObject *o) override { return core.unregisterTimers(o); }
    QList<TimerInfoV2> timersForObject(QObject *o) const override { return core.timersForObject(o); }
    Duration remainingTime(Qt::TimerId id) const override { return core.remainingTime(id); }
    void wakeUp() override { core.wakeUp(); }
    void interrupt() override { core.interrupt(); }
};
class screen final : public QPlatformScreen {
    xos::display_mode mode;
public:
    explicit screen(xos::display_mode m) : mode(m) {}
    QRect geometry() const override { return {0,0,int(mode.width),int(mode.height)}; }
    int depth() const override { return 32; }
    QImage::Format format() const override { return QImage::Format_RGB32; }
    QString name() const override { return QStringLiteral("XOS Display Service"); }
};
class fonts final : public QFreeTypeFontDatabase {
public:
    void populateFontDatabase() override {
        QFile f(QStringLiteral(":/xos/DejaVuSans.ttf"));
        if (!f.open(QIODevice::ReadOnly) || addTTFile(f.readAll(), {}).isEmpty())
            qFatal("XOS QPA: embedded DejaVu font unavailable");
    }
};
Qt::KeyboardModifiers modifiers(xos::u32 m) {
    Qt::KeyboardModifiers r;
    if(m&1) r|=Qt::ShiftModifier;
    if(m&2) r|=Qt::ControlModifier;
    if(m&4) r|=Qt::AltModifier;
    return r;
}
Qt::MouseButtons buttons(xos::u32 m) {
    Qt::MouseButtons r;
    if(m&1) r|=Qt::LeftButton;
    if(m&2) r|=Qt::RightButton;
    if(m&4) r|=Qt::MiddleButton;
    return r;
}
struct Key { int key=0; QString text; };
Key mapKey(xos::u32 code, xos::u32 mods) {
    static const char normal[] = "\0\0331234567890-=\b\tqwertyuiop[]\r\0asdfghjkl;'`\0\\zxcvbnm,./\0*\0 ";
    static const char shifted[] = "\0\033!@#$%^&*()_+\b\tQWERTYUIOP{}\r\0ASDFGHJKL:\"~\0|ZXCVBNM<>?\0*\0 ";
    if(code==42 || code==54) return {Qt::Key_Shift,{}};
    if(code==29 || code==0x11d) return {Qt::Key_Control,{}};
    if(code==56 || code==0x138) return {Qt::Key_Alt,{}};
    if(code==58) return {Qt::Key_CapsLock,{}};
    if(code==0x14b) return {Qt::Key_Left,{}};
    if(code==0x14d) return {Qt::Key_Right,{}};
    if(code==0x148) return {Qt::Key_Up,{}};
    if(code==0x150) return {Qt::Key_Down,{}};
    if(code==0x147) return {Qt::Key_Home,{}};
    if(code==0x14f) return {Qt::Key_End,{}};
    if(code==0x149) return {Qt::Key_PageUp,{}};
    if(code==0x151) return {Qt::Key_PageDown,{}};
    if(code==0x153) return {Qt::Key_Delete,{}};
    if(code>=sizeof(normal)-1) return {};
    const char n=normal[code];
    if(!n) return {};
    if(n==27) return {Qt::Key_Escape,{}};
    if(n=='\b') return {Qt::Key_Backspace,{}};
    if(n=='\t') return {Qt::Key_Tab,QStringLiteral("\t")};
    if(n=='\r') return {Qt::Key_Return,QStringLiteral("\r")};
    bool upper=mods&1;
    if(n>='a' && n<='z' && (mods&8)) upper=!upper;
    const char ch=upper?shifted[code]:n;
    return {n>='a' && n<='z'?n-'a'+'A':int(n),
            (mods&6)?QString():QString(QChar::fromLatin1(ch))};
}
std::atomic<xos::u64> pauseUntil{0};
class window final : public QPlatformWindow {
    xos::sdk::display_client client;
    QMutex transaction;
    std::atomic<bool> stopping{false};
    pthread_t input{};
    bool inputStarted=false;
    std::unique_ptr<QObject> delivery;
    bool connected=false, visible=false;
    xos::u64 sequence=0;
    Key held[512];
    Qt::MouseButtons mouseButtons;
    QPointF position;
    void deliver(const xos::display_event &e) {
        Q_ASSERT(QThread::currentThread()==QPlatformWindow::window()->thread());
        if(stopping.load() || !visible) return;
        if(e.sequence<=sequence) qFatal("XOS QPA: input sequence regression");
        sequence=e.sequence;
        std::printf("[qpa-input] seq=%llu ns=%llu kind=%u code=%u mods=%u buttons=%u lost=%u gui_ns=%llu\n",
            (unsigned long long)e.sequence,(unsigned long long)e.monotonic_ns,e.kind,e.code,e.modifiers,e.buttons,e.lost,
            (unsigned long long)xos::thread::clock());
        const auto mods=modifiers(e.modifiers);
        if(e.kind==1 || e.kind==2) {
            Key key=mapKey(e.code,e.modifiers);
            if(e.code<512) {
                if(e.kind==1) held[e.code]=key;
                else { if(held[e.code].key) key=held[e.code]; held[e.code]={}; }
            }
            if(key.key) WSI::handleKeyEvent(QPlatformWindow::window(),ulong(e.monotonic_ns/1000000),
                e.kind==1?QEvent::KeyPress:QEvent::KeyRelease,key.key,mods,key.text);
        } else if(e.kind==3 || e.kind==4) {
            if(e.kind==4) {
                for(auto &key:held) {
                    if(key.key) WSI::handleKeyEvent(QPlatformWindow::window(),QEvent::KeyRelease,key.key,Qt::NoModifier);
                    key={};
                }
            }
            position={qreal(e.x),qreal(e.y)};
            const auto next=buttons(e.buttons);
            for(Qt::MouseButton b : {Qt::LeftButton,Qt::RightButton,Qt::MiddleButton}) {
                if(bool(mouseButtons&b)!=bool(next&b)) {
                    if(next&b) mouseButtons|=b; else mouseButtons&=~b;
                    WSI::handleMouseEvent(QPlatformWindow::window(),ulong(e.monotonic_ns/1000000),position,position,mouseButtons,b,
                        (next&b)?QEvent::MouseButtonPress:QEvent::MouseButtonRelease,mods);
                }
            }
            WSI::handleMouseEvent(QPlatformWindow::window(),ulong(e.monotonic_ns/1000000),position,position,mouseButtons,Qt::NoButton,QEvent::MouseMove,mods);
        }
    }
    void inputLoop() {
        while(!stopping.load(std::memory_order_acquire)) {
            // No request lock is held while waiting for hardware input.
            const auto rc=client.wait_input();
            if(stopping.load(std::memory_order_acquire)) break;
            if(rc) {
                QMetaObject::invokeMethod(delivery.get(),[]{
                    qWarning("XOS QPA: Display Service disconnected"); QCoreApplication::exit(72);
                },Qt::QueuedConnection);
                break;
            }
            const auto deadline=pauseUntil.load();
            if(deadline>xos::thread::clock()) xos::thread::sleep_until(deadline);
            xos::display_event e{};
            xos::i64 result;
            {
                QMutexLocker lock(&transaction);
                if(stopping.load()) break;
                result=client.input(e);
            }
            if(result==0) QMetaObject::invokeMethod(delivery.get(),[this,e]{deliver(e);},Qt::QueuedConnection);
            else if(result!=xos::display_again) {
                QMetaObject::invokeMethod(delivery.get(),[]{QCoreApplication::exit(72);},Qt::QueuedConnection);
                break;
            }
        }
        std::printf("[qpa] input-thread-exit\n");
    }
public:
    explicit window(QWindow *w) : QPlatformWindow(w) {
        const auto rc=client.open();
        if(rc) qFatal("XOS QPA: exclusive Surface connect failed (%lld)",(long long)rc);
        connected=true;
        setGeometry(screen()->geometry());
        delivery=std::make_unique<QObject>();
        const int threadResult=pthread_create(&input,nullptr,[](void *arg)->void* {
            static_cast<window*>(arg)->inputLoop();return nullptr;
        },this);
        if(threadResult) qFatal("XOS QPA: input thread resource allocation failed (%d)",threadResult);
        inputStarted=true;
        std::printf("[qpa] surface-created input-thread-start\n");
    }
    ~window() override {
        stopping.store(true,std::memory_order_release);
        { QMutexLocker lock(&transaction); if(connected) client.close(); connected=false; }
        // SDK join waits through TLS destruction and kernel stack reclamation.
        // wait_input has already been revoked above; no cancellation syscall.
        if(inputStarted && pthread_join(input,nullptr)) qFatal("XOS QPA: input thread join failed");
        delivery.reset();
        std::printf("[qpa] surface-destroyed input-thread-joined\n");
    }
    void setGeometry(const QRect &) override {
        const auto full=screen()->geometry();
        QPlatformWindow::setGeometry(full);
        WSI::handleGeometryChange(QPlatformWindow::window(),full);
    }
    void setVisible(bool v) override {
        visible=v;
        WSI::handleFocusWindowChanged(v?QPlatformWindow::window():nullptr);
        WSI::handleExposeEvent(QPlatformWindow::window(),v?QRegion(geometry()):QRegion());
    }
    bool isExposed() const override { return visible; }
    void requestActivateWindow() override { if(visible) WSI::handleFocusWindowChanged(QPlatformWindow::window()); }
    xos::i64 present(xos::display_present p) {
        QMutexLocker lock(&transaction);
        return connected?client.present(p):xos::display_unavailable;
    }
};
class backing_store final : public QPlatformBackingStore {
    QImage image;
public:
    explicit backing_store(QWindow *w):QPlatformBackingStore(w){}
    QPaintDevice *paintDevice() override { return &image; }
    void resize(const QSize &s,const QRegion &) override {
        if(s!=window()->screen()->size()) qFatal("XOS QPA: only full-screen backing stores supported");
        if(image.size()==s) return;
        image=QImage(s,QImage::Format_RGB32);
        if(image.isNull()) qFatal("XOS QPA: backing store allocation failed");
        image.fill(Qt::black);
    }
    void flush(QWindow *w,const QRegion &region,const QPoint &offset) override {
        std::printf("[qpa-flush] same=%d offset=%d,%d rects=%d\n",
            w==window(),offset.x(),offset.y(),region.rectCount());
        if(!offset.isNull() || w!=window()) qFatal("XOS QPA: child/offset flush unsupported");
        auto *platform=static_cast<::window*>(w->handle());
        const QRegion clipped=region.intersected(image.rect());
        for(const QRect &r:clipped) {
            const auto begin=xos::thread::clock();
            xos::display_present p{1,sizeof(p),reinterpret_cast<xos::u64>(image.constBits()),
                xos::u64(image.sizeInBytes()),xos::u32(image.bytesPerLine()),xos::display_xrgb8888,
                {xos::u32(r.x()),xos::u32(r.y()),xos::u32(r.width()),xos::u32(r.height())}};
            const auto rc=platform->present(p);
            if(rc) { qWarning("XOS QPA: present failed (%lld)",(long long)rc); QCoreApplication::exit(72); return; }
            std::printf("[qpa-frame] x=%d y=%d w=%d h=%d stride=%d ns=%llu\n",r.x(),r.y(),r.width(),r.height(),
                image.bytesPerLine(),(unsigned long long)(xos::thread::clock()-begin));
        }
    }
};
class integration final : public QPlatformIntegration {
    screen *screen_;
    mutable ::fonts fonts;
public:
    integration() {
        xos::display_mode mode{};
        const auto rc=xos::sdk::display_control(xos::display_action::mode,reinterpret_cast<xos::u64>(&mode));
        if(rc || mode.version!=1 || mode.size!=sizeof(mode) || mode.format!=xos::display_xrgb8888
            || !mode.width || !mode.height || mode.width>16384 || mode.height>16384
            || mode.stride<xos::u64(mode.width)*4 || mode.bytes<xos::u64(mode.stride)*mode.height)
            qFatal("XOS QPA: unavailable or invalid Display Service mode (%lld)",(long long)rc);
        screen_=new screen(mode);
        WSI::handleScreenAdded(screen_);
        std::printf("[qpa] initialized Qt=6.8.3 width=%u height=%u stride=%u format=%u\n",mode.width,mode.height,mode.stride,mode.format);
    }
    ~integration() override { WSI::handleScreenRemoved(screen_); }
    bool hasCapability(Capability c) const override {
        if(c==MultipleWindows || c==NonFullScreenWindows || c==OpenGL || c==RhiBasedRendering || c==ThreadedPixmaps) return false;
        return QPlatformIntegration::hasCapability(c);
    }
    QPlatformWindow *createPlatformWindow(QWindow *w) const override { return new window(w); }
    QPlatformBackingStore *createPlatformBackingStore(QWindow *w) const override { return new backing_store(w); }
    QAbstractEventDispatcher *createEventDispatcher() const override { return new gui_dispatcher; }
    QPlatformFontDatabase *fontDatabase() const override { return &fonts; }
};
}
extern "C" void xos_qpa_pause_input(unsigned milliseconds) {
    pauseUntil.store(xos::thread::clock()+xos::u64(milliseconds)*1000000);
}
class QXosIntegrationPlugin final : public QPlatformIntegrationPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QPlatformIntegrationFactoryInterface_iid FILE "xos.json")
public:
    QPlatformIntegration *create(const QString &key,const QStringList &) override {
        return key==QStringLiteral("xos")?new integration:nullptr;
    }
};
#include "qxos.moc"
