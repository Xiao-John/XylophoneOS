// SPDX-License-Identifier: Apache-2.0
#include "transport.hpp"
#include <xos/fault_sha256.hpp>
#include <QBackingStore>
#include <QCloseEvent>
#include <QFontDatabase>
#include <QGuiApplication>
#include <QImage>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPluginLoader>
#include <QTimer>
#include <QWindow>
#include <array>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <thread>
#include <vector>
#include "../../qt6/qpa/frame_receipt.hpp"

Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
namespace {
using namespace xos;
using namespace xos::clarke;
class viewport final : public QWindow {
public:
    viewport(ipc_channel channel, QString address) : channel_(channel), backing_(this), address_(address) {
        setTitle(QStringLiteral("ClarkE — WebCore")); resize(640, 440);
        QFontDatabase::addApplicationFont(QStringLiteral("/usr/share/fonts/clarke/DejaVuSans.ttf"));
        const ipc_channel worker_channel = channel_;
        worker_ = std::thread([this, worker_channel] {
            for (;;) {
                if (stopping_.load()) break;
                packet value{};
                const i64 result = receive_now(worker_channel, value);
                if (!result) {
                    QMetaObject::invokeMethod(this, [this, value] { accept(value); }, Qt::QueuedConnection);
                    continue;
                }
                if (result == process_error_would_block) {
                    const i64 waited = sdk::ipc_wait_until(worker_channel.receive, ipc_wait_mode::receive, deadline_after(1'000'000'000));
                    if (!waited || waited == thread_error_timeout) continue;
                }
                if (!stopping_.load()) QMetaObject::invokeMethod(this, [] { QGuiApplication::exit(10); }, Qt::QueuedConnection);
                break;
            }
        });
        QTimer::singleShot(0, this, [this] { navigate(); });
    }
    ~viewport() override {
        stopping_.store(true); close_pair(channel_);
        if (worker_.joinable()) worker_.join();
    }
protected:
    void exposeEvent(QExposeEvent*) override { paint(); }
    bool event(QEvent* event) override {
        if (event->type() == QEvent::Close) {
            packet value{}; value.action = operation::close;
            (void)send_packet(channel_, value, deadline_after(bootstrap_ns));
            QGuiApplication::quit(); return true;
        }
        if (event->type() == QEvent::KeyPress) {
            auto* key = static_cast<QKeyEvent*>(event);
            if (key->modifiers().testFlag(Qt::ControlModifier) && key->key() == Qt::Key_Q) { close(); return true; }
            if (key->modifiers().testFlag(Qt::ControlModifier) && key->key() == Qt::Key_A) { select_all_ = true; return true; }
            if (key->key() == Qt::Key_Return || key->key() == Qt::Key_Enter || key->key() == Qt::Key_F5) { navigate(); return true; }
            if (key->key() == Qt::Key_Escape) { cancel(); return true; }
            if (key->key() == Qt::Key_Backspace) {
                if (select_all_) address_.clear(); else address_.chop(1);
                select_all_ = false; paint(); return true;
            }
            const auto text = key->text();
            if (!text.isEmpty() && !key->modifiers().testFlag(Qt::ControlModifier)) {
                if (select_all_) address_.clear();
                select_all_ = false;
                if (address_.size() + text.size() <= url_limit) address_ += text;
                paint(); return true;
            }
        }
        if (event->type() == QEvent::MouseButtonPress) {
            auto* mouse = static_cast<QMouseEvent*>(event);
            if (QRect(476, 20, 60, 32).contains(mouse->position().toPoint())) navigate();
            else if (QRect(544, 20, 72, 32).contains(mouse->position().toPoint())) cancel();
            return true;
        }
        return QWindow::event(event);
    }
private:
    void reset_pending() { partial_.clear(); position_ = 0; pending_present_ = false; }
    void navigate() {
        const QByteArray bytes = address_.toUtf8();
        if (!valid_url(reinterpret_cast<const u8*>(bytes.constData()), static_cast<u32>(bytes.size())) || navigation_ == ~u64{0}) {
            status_ = QStringLiteral("Enter a supported HTTP or HTTPS URL"); paint(); return;
        }
        packet value{}; value.action = operation::navigate; value.navigation = ++navigation_;
        value.length = static_cast<u32>(bytes.size()); std::memcpy(value.data, bytes.constData(), value.length);
        reset_pending(); awaiting_ = true; status_ = QStringLiteral("Loading…");
        if (!send_packet(channel_, value, deadline_after(bootstrap_ns))) QGuiApplication::exit(11);
        paint();
    }
    void cancel() {
        packet value{}; value.action = operation::cancel; value.navigation = navigation_;
        reset_pending(); awaiting_ = false; status_ = QStringLiteral("Cancelled");
        if (!send_packet(channel_, value, deadline_after(bootstrap_ns))) QGuiApplication::exit(11);
        paint();
    }
    void invalid_frame() { reset_pending(); awaiting_ = false; QGuiApplication::exit(12); }
    void accept(const packet& value) {
        if (value.navigation != navigation_) return;
        if (value.action == operation::status) {
            if (value.length || value.offset || value.result >= 0) { invalid_frame(); return; }
            reset_pending(); awaiting_ = false;
            status_ = QStringLiteral("Navigation failed (%1)").arg(value.result); paint(); return;
        }
        if (!awaiting_) return;
        if (value.result) { invalid_frame(); return; }
        if (value.action == operation::frame_begin) {
            frame_info info{};
            if (value.offset || value.length != sizeof(info) || !partial_.empty()) { invalid_frame(); return; }
            std::memcpy(&info, value.data, sizeof(info));
            if (info.width != viewport_width || info.height != viewport_height ||
                info.stride != viewport_width * 4 || info.bytes != frame_bytes) { invalid_frame(); return; }
            partial_.resize(frame_bytes); position_ = 0; hash_ = sha256{}; return;
        }
        if (value.action == operation::frame_chunk) {
            if (partial_.size() != frame_bytes || value.offset != position_ || !value.length ||
                value.length > frame_bytes - position_) { invalid_frame(); return; }
            std::memcpy(partial_.data() + position_, value.data, value.length); hash_.update(value.data, value.length);
            position_ += value.length; return;
        }
        if (value.action != operation::frame_end || partial_.size() != frame_bytes || position_ != frame_bytes ||
            value.offset != frame_bytes || value.length != 32) { invalid_frame(); return; }
        hash_.finish(frame_digest_.data());
        if (std::memcmp(frame_digest_.data(), value.data, 32)) { invalid_frame(); return; }
        frame_ = QImage(partial_.data(), viewport_width, viewport_height, viewport_width * 4, QImage::Format_RGBA8888).copy();
        partial_.clear(); pending_present_ = true; awaiting_ = false; status_ = QStringLiteral("Page loaded");
        paint();
    }
    void paint() {
        if (!isExposed()) return;
        xos::qt::frame_commit_receipt before{};
        if (!xos_qpa_frame_receipt(this, &before)) { QGuiApplication::exit(13); return; }
        backing_.resize(size()); const QRegion region(QRect(QPoint(0, 0), size()));
        backing_.beginPaint(region);
        QPainter painter(backing_.paintDevice());
        painter.fillRect(QRect(QPoint(0, 0), size()), QColor(238, 242, 248));
        painter.setFont(QFont(QStringLiteral("DejaVu Sans"), 12));
        painter.fillRect(QRect(20, 20, 448, 32), Qt::white); painter.setPen(QColor(25, 35, 50));
        painter.drawRect(QRect(20, 20, 448, 32));
        painter.save(); painter.setClipRect(QRect(26, 20, 436, 32));
        painter.drawText(QRect(28, 20, 432, 32), Qt::AlignVCenter, address_); painter.restore();
        painter.fillRect(QRect(476, 20, 60, 32), QColor(32, 90, 180)); painter.setPen(Qt::white);
        painter.drawText(QRect(476, 20, 60, 32), Qt::AlignCenter, QStringLiteral("Go"));
        painter.fillRect(QRect(544, 20, 72, 32), QColor(80, 90, 105));
        painter.drawText(QRect(544, 20, 72, 32), Qt::AlignCenter, QStringLiteral("Cancel"));
        painter.setPen(QColor(25, 35, 50)); painter.drawText(24, 82, status_);
        painter.fillRect(QRect(24, 100, viewport_width, viewport_height), Qt::white);
        if (!frame_.isNull()) painter.drawImage(QPoint(24, 100), frame_);
        painter.drawText(24, 316, QStringLiteral("WebCore DOM/CSS • isolated renderer and network"));
        painter.drawText(24, 344, QStringLiteral("Enter / F5: navigate    Esc: cancel    Ctrl+Q: close"));
        painter.end(); backing_.endPaint(); backing_.flush(region);
        xos::qt::frame_commit_receipt committed{};
        if (!xos_qpa_frame_receipt(this, &committed) || committed.version != 1 || committed.size != sizeof(committed) ||
            !committed.serial || committed.serial <= before.serial || committed.result) {
            QGuiApplication::exit(13); return;
        }
        if (pending_present_) {
            packet value{}; value.action = operation::presented; value.navigation = navigation_; value.length = 32;
            std::memcpy(value.data, frame_digest_.data(), 32);
            if (!send_packet(channel_, value, deadline_after(bootstrap_ns))) { QGuiApplication::exit(11); return; }
            pending_present_ = false;
            char hexadecimal[65];
            for (unsigned i = 0; i < 32; ++i) std::snprintf(hexadecimal + i * 2, 3, "%02x", frame_digest_[i]);
            std::printf("CLARKE_VIEWPORT_PRESENT navigation=%llu x=%d y=%d width=320 height=180 frame=%llu sha256=%s\n",
                        static_cast<unsigned long long>(navigation_), x()+24, y()+100,
                        static_cast<unsigned long long>(committed.serial), hexadecimal); std::fflush(stdout);
        }
    }
    ipc_channel channel_{};
    QBackingStore backing_;
    QString address_, status_;
    QImage frame_;
    std::vector<u8> partial_;
    std::array<u8, 32> frame_digest_{};
    sha256 hash_;
    u32 position_ = 0;
    u64 navigation_ = 0;
    bool awaiting_ = false, pending_present_ = false, select_all_ = false;
    std::atomic<bool> stopping_{false};
    std::thread worker_;
};
}
int main(int argc, char** argv) {
    u64 controller = 0;
    if (argc != 3 || !parse_pid(argv[1], controller)) return 2;
    bootstrap config{}; ipc_channel channel{};
    if (!child_bootstrap(controller, role::ui, config, channel)) return 3;
    QGuiApplication app(argc, argv);
    viewport window(channel, QString::fromUtf8(argv[2])); window.show();
    return app.exec();
}
