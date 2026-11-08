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
#include <qpa/qplatformcursor.h>
#include <qpa/qplatformwindow.h>
#include <qpa/qplatformbackingstore.h>
#include <qpa/qwindowsysteminterface.h>
#include <private/qfreetypefontdatabase_p.h>
#include "qeventdispatcher_xos_p.h"
#include <xos/interactium_abi.hpp>
#include <xos/process_abi.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_core.hpp>
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
QPoint pointerPosition;
class cursor final : public QPlatformCursor {
public:
    void changeCursor(QCursor *, QWindow *) override {} // Interactium draws the pointer.
    QPoint pos() const override { return pointerPosition; }
};
class screen final : public QPlatformScreen {
    QSize size_;
    mutable ::cursor cursor_;
public:
    screen(xos::u32 width, xos::u32 height) : size_(int(width), int(height)) {}
    QRect geometry() const override { return QRect(QPoint(0,0),size_); }
    int depth() const override { return 32; }
    QImage::Format format() const override { return QImage::Format_RGB32; }
    QString name() const override { return QStringLiteral("XOS Display Service"); }
    QPlatformCursor *cursor() const override { return &cursor_; }
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

class interactium_connection {
    xos::ipc_channel channel_{};
    QMutex transaction_;
    xos::u64 session_ = 0;
    xos::u64 sequence_ = 0;
    xos::u32 width_ = 0, height_ = 0;

    xos::i64 exchange(xos::interactium::message_type type, xos::u64 object,
                      const void* payload, xos::u32 payload_length,
                      const xos::u8* data, xos::u32 data_length,
                      xos::interactium::wire_header& reply, xos::u8* reply_payload,
                      xos::u32& reply_length, bool hello = false) {
        using namespace xos;
        using namespace xos::interactium;
        const u64 total = sizeof(wire_header) + u64(payload_length) + data_length;
        if (total > process_pipe_bytes || (payload_length && !payload) || (data_length && !data))
            return process_error_invalid;
        QMutexLocker lock(&transaction_);
        alignas(8) u8 request[process_pipe_bytes]{};
        wire_header header{protocol_version, static_cast<u32>(total), type, 0, ++sequence_,
                           hello ? 0 : session_, object, payload_length + data_length, 0};
        auto* out = request;
        const auto* header_bytes = reinterpret_cast<const u8*>(&header);
        for (u32 i = 0; i < sizeof(header); ++i) out[i] = header_bytes[i];
        const auto* payload_bytes = static_cast<const u8*>(payload);
        for (u32 i = 0; i < payload_length; ++i) out[sizeof(header) + i] = payload_bytes[i];
        for (u32 i = 0; i < data_length; ++i)
            out[sizeof(header) + payload_length + i] = data[i];
        if (sdk::ipc_wait(channel_.send, ipc_wait_mode::send) != 0 ||
            sdk::ipc_send(channel_.send, request, total) != 0 ||
            sdk::ipc_wait(channel_.receive, ipc_wait_mode::receive) != 0) return process_error_state;
        alignas(8) u8 response[process_pipe_bytes]{};
        const i64 received = sdk::ipc_recv(channel_.receive, response, sizeof(response));
        if (received < static_cast<i64>(sizeof(wire_header))) return process_error_state;
        for (u32 i = 0; i < sizeof(reply); ++i)
            reinterpret_cast<u8*>(&reply)[i] = response[i];
        if (reply.version != protocol_version || reply.size != static_cast<u32>(received) ||
            reply.sequence != header.sequence || reply.payload_length !=
                static_cast<u32>(received) - sizeof(wire_header) || reply.session !=
                (hello ? reply.session : session_) || reply_payload == nullptr ||
            reply.payload_length > process_pipe_bytes - sizeof(wire_header)) return process_error_invalid;
        reply_length = reply.payload_length;
        for (u32 i = 0; i < reply_length; ++i) reply_payload[i] = response[sizeof(wire_header) + i];
        return 0;
    }

    xos::i64 status_call(xos::interactium::message_type type, xos::u64 object,
                         const void* payload, xos::u32 length) {
        using namespace xos;
        using namespace xos::interactium;
        wire_header reply{};
        u8 body[sizeof(input_payload)]{};
        u32 body_length = 0;
        const i64 rc = exchange(type, object, payload, length, nullptr, 0,
                                reply, body, body_length);
        if (rc != 0) return rc;
        if (reply.type != message_type::ack || body_length != sizeof(status_payload))
            return process_error_invalid;
        status_payload status{};
        for (u32 i = 0; i < sizeof(status); ++i) reinterpret_cast<u8*>(&status)[i] = body[i];
        return status.result;
    }

public:
    ~interactium_connection() {
        if (session_ != 0) (void)status_call(xos::interactium::message_type::disconnect, 0, nullptr, 0);
        if (channel_.send) (void)xos::sdk::ipc_channel_close(channel_.send);
    }
    xos::i64 open() {
        using namespace xos;
        using namespace xos::interactium;
        const i64 connected = sdk::ipc_name_connect("interactium", channel_);
        if (connected != 0) return connected;
        const hello_payload hello{protocol_version, 0, 800, 600};
        wire_header reply{};
        u8 body[sizeof(hello_reply_payload)]{};
        u32 body_length = 0;
        const i64 rc = exchange(message_type::hello, 0, &hello, sizeof(hello), nullptr, 0,
                                reply, body, body_length, true);
        if (rc != 0 || reply.type != message_type::hello_reply ||
            body_length != sizeof(hello_reply_payload)) return process_error_state;
        hello_reply_payload hello_reply{};
        for (u32 i = 0; i < sizeof(hello_reply); ++i)
            reinterpret_cast<u8*>(&hello_reply)[i] = body[i];
        if (hello_reply.server_version != protocol_version || hello_reply.session_epoch == 0 ||
            hello_reply.screen_width == 0 || hello_reply.screen_height == 0 ||
            hello_reply.screen_width > 800 || hello_reply.screen_height > 600)
            return process_error_invalid;
        session_ = reply.session;
        width_ = hello_reply.screen_width;
        height_ = hello_reply.screen_height;
        return 0;
    }
    xos::u32 width() const { return width_; }
    xos::u32 height() const { return height_; }
    xos::i64 create_window(const QRect& geometry, xos::u64& id) {
        using namespace xos;
        using namespace xos::interactium;
        const create_window_payload create{geometry.x(), geometry.y(), u32(geometry.width()),
                                           u32(geometry.height()), window_role::normal, 0, 0};
        wire_header reply{}; u8 body[sizeof(status_payload)]{}; u32 length = 0;
        const i64 rc = exchange(message_type::create_window, 0, &create, sizeof(create), nullptr, 0,
                                reply, body, length);
        if (rc != 0 || reply.type != message_type::ack || length != sizeof(status_payload))
            return process_error_state;
        status_payload status{};
        for (u32 i = 0; i < sizeof(status); ++i) reinterpret_cast<u8*>(&status)[i] = body[i];
        id = reply.object;
        return id != 0 ? status.result : process_error_invalid;
    }
    xos::i64 configure(xos::u64 id, const QRect& geometry, bool visible) {
        const xos::interactium::configure_payload payload{0, geometry.x(), geometry.y(),
            xos::u32(geometry.width()), xos::u32(geometry.height()),
            visible ? xos::interactium::flag_visible : 0u, 0};
        return status_call(xos::interactium::message_type::configure, id, &payload, sizeof(payload));
    }
    xos::i64 focus(xos::u64 id) {
        return status_call(xos::interactium::message_type::focus, id, nullptr, 0);
    }
    xos::i64 destroy_window(xos::u64 id) {
        return status_call(xos::interactium::message_type::destroy_window, id, nullptr, 0);
    }
    xos::i64 begin_frame(xos::u64 id, const xos::interactium::frame_payload& frame) {
        return status_call(xos::interactium::message_type::begin_frame, id, &frame, sizeof(frame));
    }
    xos::i64 write_tile(xos::u64 id, const xos::interactium::tile_payload& tile,
                        const xos::u8* pixels, xos::u32 length) {
        using namespace xos;
        using namespace xos::interactium;
        wire_header reply{}; u8 body[sizeof(status_payload)]{}; u32 reply_length = 0;
        const i64 rc = exchange(message_type::write_tile, id, &tile, sizeof(tile), pixels, length,
                                reply, body, reply_length);
        if (rc != 0 || reply.type != message_type::ack || reply_length != sizeof(status_payload))
            return process_error_state;
        status_payload status{};
        for (u32 i = 0; i < sizeof(status); ++i) reinterpret_cast<u8*>(&status)[i] = body[i];
        return status.result;
    }
    xos::i64 commit_frame(xos::u64 id, xos::u64 serial) {
        const xos::interactium::commit_payload commit{serial, 0, 0};
        return status_call(xos::interactium::message_type::commit_frame, id, &commit, sizeof(commit));
    }
    xos::i64 input(xos::u64 id, xos::interactium::input_payload& event) {
        using namespace xos;
        using namespace xos::interactium;
        wire_header reply{}; u8 body[sizeof(input_payload)]{}; u32 length = 0;
        const i64 rc = exchange(message_type::input, id, nullptr, 0, nullptr, 0,
                                reply, body, length);
        if (rc != 0) return rc;
        if (reply.type == message_type::ack && length == sizeof(status_payload)) {
            status_payload status{};
            for (u32 i = 0; i < sizeof(status); ++i) reinterpret_cast<u8*>(&status)[i] = body[i];
            return status.result;
        }
        if (reply.type != message_type::input || length != sizeof(event)) return process_error_invalid;
        for (u32 i = 0; i < sizeof(event); ++i) reinterpret_cast<u8*>(&event)[i] = body[i];
        return 0;
    }
};

class window final : public QPlatformWindow {
    interactium_connection* client_ = nullptr;
    xos::u64 id_ = 0;
    xos::u64 frame_serial_ = 0;
    std::atomic<bool> stopping{false};
    pthread_t input{};
    bool inputStarted=false;
    std::unique_ptr<QObject> delivery;
    bool connected=false, visible=false;
    bool pointer_inside=false;
    xos::u64 sequence=0;
    Key held[512];
    Qt::MouseButtons mouseButtons;
    QPointF position;
    void deliver(const xos::interactium::input_payload &e) {
        Q_ASSERT(QThread::currentThread()==QPlatformWindow::window()->thread());
        if(stopping.load() || !visible) return;
        if(e.input_sequence<=sequence) qFatal("XOS QPA: input sequence regression");
        sequence=e.input_sequence;
        const auto time = ulong(xos::thread::clock()/1000000);
        std::printf("[qpa-input] seq=%llu kind=%u code=%u mods=%u buttons=%u lost=%u pos=%d,%d\n",
            (unsigned long long)e.input_sequence,unsigned(e.kind),e.code,e.modifiers,e.buttons,e.lost,e.x,e.y);
        const auto mods=modifiers(e.modifiers);
        if(e.kind==xos::interactium::input_kind::key_press ||
           e.kind==xos::interactium::input_kind::key_release) {
            Key key=mapKey(e.code,e.modifiers);
            if(e.code<512) {
                if(e.kind==xos::interactium::input_kind::key_press) held[e.code]=key;
                else { if(held[e.code].key) key=held[e.code]; held[e.code]={}; }
            }
            if(key.key) WSI::handleKeyEvent(QPlatformWindow::window(),time,
                e.kind==xos::interactium::input_kind::key_press?QEvent::KeyPress:QEvent::KeyRelease,
                key.key,mods,key.text);
        } else if(e.kind==xos::interactium::input_kind::pointer ||
                  e.kind==xos::interactium::input_kind::resync) {
            if(e.kind==xos::interactium::input_kind::resync) {
                for(auto &key:held) {
                    if(key.key) WSI::handleKeyEvent(QPlatformWindow::window(),QEvent::KeyRelease,key.key,Qt::NoModifier);
                    key={};
                }
            }
            position={qreal(e.x-geometry().x()),qreal(e.y-geometry().y())};
            pointerPosition = QPoint(e.x, e.y);
            const QPointF globalPosition(pointerPosition);
            const bool inside = geometry().contains(pointerPosition);
            if (inside != pointer_inside) {
                pointer_inside = inside;
                if (inside) WSI::handleEnterEvent(QPlatformWindow::window(), position, globalPosition);
                else WSI::handleLeaveEvent(QPlatformWindow::window());
            }
            const auto next=buttons(e.buttons);
            for(Qt::MouseButton b : {Qt::LeftButton,Qt::RightButton,Qt::MiddleButton}) {
                if(bool(mouseButtons&b)!=bool(next&b)) {
                    if(next&b) mouseButtons|=b; else mouseButtons&=~b;
                    WSI::handleMouseEvent(QPlatformWindow::window(),time,position,globalPosition,mouseButtons,b,
                        (next&b)?QEvent::MouseButtonPress:QEvent::MouseButtonRelease,mods);
                }
            }
            WSI::handleMouseEvent(QPlatformWindow::window(),time,position,globalPosition,mouseButtons,Qt::NoButton,QEvent::MouseMove,mods);
        }
    }
    void inputLoop() {
        while(!stopping.load(std::memory_order_acquire)) {
            const auto deadline=pauseUntil.load();
            if(deadline>xos::thread::clock()) xos::thread::sleep_until(deadline);
            xos::interactium::input_payload event{};
            const xos::i64 result=client_->input(id_,event);
            if(stopping.load(std::memory_order_acquire)) break;
            if(result==0) QMetaObject::invokeMethod(delivery.get(),[this,event]{deliver(event);},Qt::QueuedConnection);
            else if(result==xos::process_error_would_block) {
                xos::thread::sleep_until(xos::thread::clock()+5000000);
            } else {
                QMetaObject::invokeMethod(delivery.get(),[]{
                    qWarning("XOS QPA: Interactium disconnected"); QCoreApplication::exit(72);
                },Qt::QueuedConnection);
                break;
            }
        }
        std::printf("[qpa] input-thread-exit\n");
    }
public:
    window(QWindow *w, interactium_connection& client) : QPlatformWindow(w),client_(&client) {
        QRect requested=w->geometry();
        if(requested.width()<=0 || requested.height()<=0) requested=QRect(80,80,640,420);
        if(requested.width()>800 || requested.height()>600)
            qFatal("XOS QPA: requested Interactium window exceeds 800x600");
        if(requested.x()==0 && requested.y()==0)
            requested.moveTo((int(client.width())-requested.width())/2,
                             (int(client.height())-requested.height())/2);
        const auto rc=client_->create_window(requested,id_);
        if(rc) qFatal("XOS QPA: Interactium create-window failed (%lld)",(long long)rc);
        connected=true;
        QPlatformWindow::setGeometry(requested);
        WSI::handleGeometryChange(w,requested);
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
        if(inputStarted && pthread_join(input,nullptr)) qFatal("XOS QPA: input thread join failed");
        if(connected) (void)client_->destroy_window(id_);
        connected=false;
        delivery.reset();
        std::printf("[qpa] interactium-window-destroyed input-thread-joined\n");
    }
    void setGeometry(const QRect& requested) override {
        if(requested.width()<=0 || requested.height()<=0 || requested.width()>800 || requested.height()>600)
            return;
        QPlatformWindow::setGeometry(requested);
        if(connected && client_->configure(id_,requested,visible)!=0)
            qWarning("XOS QPA: Interactium configure failed");
        WSI::handleGeometryChange(QPlatformWindow::window(),requested);
    }
    void setVisible(bool v) override {
        if (!v && pointer_inside) {
            WSI::handleLeaveEvent(QPlatformWindow::window());
            pointer_inside = false;
        }
        visible=v;
        if(connected && client_->configure(id_,geometry(),v)!=0)
            qWarning("XOS QPA: Interactium visibility update failed");
        if(v && client_->focus(id_)!=0) qWarning("XOS QPA: Interactium focus failed");
        WSI::handleFocusWindowChanged(v?QPlatformWindow::window():nullptr);
        WSI::handleExposeEvent(QPlatformWindow::window(),v?QRegion(geometry()):QRegion());
    }
    bool isExposed() const override { return visible; }
    void requestActivateWindow() override {
        if(visible) { (void)client_->focus(id_); WSI::handleFocusWindowChanged(QPlatformWindow::window()); }
    }
    xos::i64 flush(const QImage& image,const QRegion& region) {
        using namespace xos;
        using namespace xos::interactium;
        if(!connected) return process_error_state;
        const auto serial=++frame_serial_;
        const frame_payload frame{serial,u32(image.width()),u32(image.height()),
                                  u32(image.bytesPerLine()),pixel_format::argb8888_premultiplied,
                                  u64(image.sizeInBytes())};
        auto rc=client_->begin_frame(id_,frame);
        if(rc) return rc;
        u8 packed[4008];
        for(const QRect& rect:region) {
            for(int y=rect.y();y<rect.y()+rect.height();) {
                const int tile_width=qMin(rect.width(),1002);
                const int tile_height=qMax(1,qMin(rect.y()+rect.height()-y,4008/(tile_width*4)));
                for(int x=rect.x();x<rect.x()+rect.width();) {
                    const int width=qMin(tile_width,rect.x()+rect.width()-x);
                    const int height=qMin(tile_height,rect.y()+rect.height()-y);
                    const auto bytes=u32(width*height*4);
                    for(int row=0;row<height;++row) {
                        const auto* source=image.constScanLine(y+row)+x*4;
                        for(int column=0;column<width*4;++column)
                            packed[row*width*4+column]=source[column];
                    }
                    const tile_payload tile{serial,u32(x),u32(y),u32(width),u32(height),
                        u32(y*image.bytesPerLine()+x*4),bytes,0};
                    rc=client_->write_tile(id_,tile,packed,bytes);
                    if(rc) return rc;
                    x+=width;
                }
                y+=tile_height;
            }
        }
        return client_->commit_frame(id_,serial);
    }
};
class backing_store final : public QPlatformBackingStore {
    QImage image;
public:
    explicit backing_store(QWindow *w):QPlatformBackingStore(w){}
    QPaintDevice *paintDevice() override { return &image; }
    void resize(const QSize &s,const QRegion &) override {
        if(s.isEmpty() || s.width()>800 || s.height()>600)
            qFatal("XOS QPA: backing store exceeds Interactium surface limits");
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
        const auto begin=xos::thread::clock();
        const auto rc=platform->flush(image,clipped);
        if(rc) { qWarning("XOS QPA: Interactium frame commit failed (%lld)",(long long)rc); QCoreApplication::exit(72); return; }
        std::printf("[qpa-frame] rects=%d stride=%d ns=%llu\n",clipped.rectCount(),image.bytesPerLine(),
            (unsigned long long)(xos::thread::clock()-begin));
    }
};
class integration final : public QPlatformIntegration {
    screen *screen_;
    mutable ::fonts fonts;
    interactium_connection client_;
public:
    integration() {
        const auto rc=client_.open();
        if(rc) qFatal("XOS QPA: Interactium connect/hello failed (%lld)",(long long)rc);
        screen_=new screen(client_.width(),client_.height());
        WSI::handleScreenAdded(screen_);
        std::printf("[qpa] initialized Qt=6.8.3 backend=Interactium width=%u height=%u\n",client_.width(),client_.height());
    }
    ~integration() override { WSI::handleScreenRemoved(screen_); }
    bool hasCapability(Capability c) const override {
        if(c==OpenGL || c==RhiBasedRendering || c==ThreadedPixmaps) return false;
        return QPlatformIntegration::hasCapability(c);
    }
    QPlatformWindow *createPlatformWindow(QWindow *w) const override { return new window(w,const_cast<interactium_connection&>(client_)); }
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
