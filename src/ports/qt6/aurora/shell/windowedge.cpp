#include "windowedge.h"
#include <QEnterEvent>
#include <QCloseEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPushButton>
#include <QResizeEvent>
#include <QScreen>
#include <QVariantAnimation>
#include <functional>

// Animate a snapshot so the title, controls and four rounded corners scale together.
// The real window keeps its geometry and is restored when the transition finishes.
class WindowTransition final : public QWidget
{
public:
    explicit WindowTransition(QWidget *parent) : QWidget(parent)
    {
        setObjectName(QStringLiteral("WindowTransition"));
        setAttribute(Qt::WA_TransparentForMouseEvents);
        setAttribute(Qt::WA_NoSystemBackground);
    }
    QPixmap snapshot;
    QRectF frame;
    qreal opacity = 1;
protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.setRenderHint(QPainter::SmoothPixmapTransform);
        p.setOpacity(opacity);
        p.drawPixmap(frame, snapshot, QRectF(snapshot.rect()));
    }
};

class WindowControl final : public QPushButton
{
public:
    WindowControl(int action, QWidget *parent, std::function<void()> relayout)
        : QPushButton(parent), m_action(action), m_relayout(std::move(relayout)), m_animation(this)
    {
        setCursor(Qt::PointingHandCursor);
        setFocusPolicy(Qt::NoFocus);
        setAttribute(Qt::WA_NoSystemBackground);
        setAccessibleName(word());
        QFont controlFont = font();
        controlFont.setBold(true);
        setFont(controlFont);
        connect(&m_animation, &QVariantAnimation::valueChanged, this, [this](const QVariant &v) {
            m_progress = v.toReal(); m_relayout(); update();
        });
    }
    void setScale(qreal scale) { m_scale = scale; }
    int animatedWidth() const
    {
        QFont f = font(); f.setPixelSize(qMax(1, qRound(12 * m_scale)));
        const qreal expanded = QFontMetrics(f).horizontalAdvance(word()) + 20 * m_scale;
        return qMax(1, qRound(22 * m_scale + (expanded - 22 * m_scale) * m_progress));
    }
    void setRestored(bool restored) { m_restored = restored; setAccessibleName(word()); update(); }
protected:
    void enterEvent(QEnterEvent *e) override { QPushButton::enterEvent(e); animate(1); }
    void leaveEvent(QEvent *e) override { QPushButton::leaveEvent(e); animate(0); }
    void hideEvent(QHideEvent *e) override
    {
        QPushButton::hideEvent(e);
        m_animation.stop(); m_progress = 0; m_relayout();
    }
    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this); p.setRenderHint(QPainter::Antialiasing);
        QColor fill(m_action == 2 ? "#F45B63" : "#BFBFBF");
        if (isDown()) fill = fill.darker(110);
        p.setPen(Qt::NoPen); p.setBrush(fill);
        p.drawRoundedRect(QRectF(rect()), 6 * m_scale, 6 * m_scale);
        p.save(); p.setOpacity(1 - m_progress);
        p.translate(width() / 2.0, height() / 2.0); p.scale(m_scale, m_scale);
        p.setPen(QPen(Qt::white, 1.7, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
        p.setBrush(Qt::NoBrush);
        if (m_action == 0) p.drawLine(QPointF(-4, 0), QPointF(4, 0));
        else if (m_action == 1) {
            if (m_restored) p.drawRoundedRect(QRectF(-2, -5, 7, 7), 0.8, 0.8);
            p.drawRoundedRect(QRectF(-4, -3, 8, 7), 0.8, 0.8);
        } else {
            p.drawLine(QPointF(-4, -4), QPointF(4, 4));
            p.drawLine(QPointF(4, -4), QPointF(-4, 4));
        }
        p.restore(); p.setOpacity(m_progress); p.setPen(Qt::white);
        QFont f = font(); f.setPixelSize(qMax(1, qRound(12 * m_scale))); p.setFont(f);
        p.drawText(rect(), Qt::AlignCenter, word());
    }
private:
    QString word() const
    {
        if (m_action == 0) return QStringLiteral("Minimize");
        if (m_action == 1) return m_restored ? QStringLiteral("Restore") : QStringLiteral("Maximize");
        return QStringLiteral("Close");
    }
    void animate(qreal target)
    {
        m_animation.stop(); m_animation.setDuration(260);
        m_animation.setStartValue(m_progress); m_animation.setEndValue(target);
        m_animation.setEasingCurve(QEasingCurve::InOutCubic); m_animation.start();
    }
    int m_action;
    std::function<void()> m_relayout;
    QVariantAnimation m_animation;
    qreal m_progress = 0, m_scale = 1;
    bool m_restored = false;
};

WindowEdge::WindowEdge(QWidget *parent) : QWidget(parent), m_windowAnimation(this)
{
    setObjectName(QStringLiteral("ExampleWindow"));
    setWindowTitle(QStringLiteral("Example Window"));
    setAttribute(Qt::WA_TranslucentBackground); setAutoFillBackground(false);
    setMouseTracking(true);
    if (!parent) setWindowFlags(Qt::Window | Qt::FramelessWindowHint);
    resize(418, 418);
    const char *names[] = { "MinimizeButton", "MaximizeButton", "CloseButton" };
    for (int i = 0; i < 3; ++i) {
        m_controls[i] = new WindowControl(i, this, [this] { updateChildGeometry(); update(); });
        m_controls[i]->setObjectName(QLatin1String(names[i]));
    }
    connect(m_controls[0], &QPushButton::clicked, this, &WindowEdge::minimizeAnimated);
    connect(m_controls[1], &QPushButton::clicked, this, &WindowEdge::toggleMaximized);
    connect(m_controls[2], &QPushButton::clicked, this, &QWidget::close);
    if (parent) parent->installEventFilter(this);
    if (parent) {
        m_transition = new WindowTransition(parent);
        m_transition->hide();
    }
    connect(&m_windowAnimation, &QVariantAnimation::finished, this, [this] {
        m_geometryAnimating = false;
        if (m_transition) m_transition->hide();
        if (m_opening && m_state == State::Running) {
            show(); raise();
            emit stackingRequested();
        }
    });
    updateChildGeometry();
}

void WindowEdge::setState(State state)
{
    // State changes are observed by Background and reflected in the Dock marker.
    if (m_state == state) return;
    m_state = state;
    emit stateChanged(state);
}

void WindowEdge::openAnimated(const QRect &dockIconGlobalGeometry)
{
    m_dockIconGeometry = dockIconGlobalGeometry;
    if (m_state == State::Running && m_windowAnimation.state() != QAbstractAnimation::Running) {
        show(); raise(); emit stackingRequested(); return;
    }
    if (m_state == State::Running && m_opening) return;
    const bool restoring = m_state == State::Minimized;
    setState(State::Running);
    animateWindow(true, restoring);
}

void WindowEdge::minimizeAnimated()
{
    if (m_state != State::Running) return;
    setState(State::Minimized);
    m_dragging = false;
    m_resizeEdges = {};
    animateWindow(false);
}

void WindowEdge::animateWindow(bool opening, bool useDockAnchor)
{
    m_opening = opening;
    if (!m_transition || !parentWidget()) {
        if (opening) show(); else hide();
        return;
    }
    // Snapshot transitions can be reversed from their current frame and opacity.
    const bool interrupted = m_windowAnimation.state() == QAbstractAnimation::Running;
    const bool geometryInterrupted = interrupted && m_geometryAnimating;
    const QRectF previous = geometryInterrupted ? QRectF(geometry()) : m_transition->frame;
    const qreal previousOpacity = geometryInterrupted ? 1.0 : m_transition->opacity;
    m_windowAnimation.stop();
    disconnect(&m_windowAnimation, &QVariantAnimation::valueChanged, this, nullptr);
    if (!interrupted || geometryInterrupted) m_transition->snapshot = grab();
    if (geometryInterrupted) {
        hide();
        setGeometry(m_geometryTarget);
    }
    m_geometryAnimating = false;
    m_transition->setGeometry(parentWidget()->rect());
    const QRectF full(geometry());
    // New launches grow from the desktop center; minimize/restore use the Dock.
    QPointF anchor = QRectF(parentWidget()->rect()).center();
    if (useDockAnchor && m_dockIconGeometry.isValid())
        anchor = parentWidget()->mapFromGlobal(m_dockIconGeometry.center());
    const QSizeF smallSize = full.size() * 0.08;
    const QRectF small(anchor - QPointF(smallSize.width()/2, smallSize.height()/2), smallSize);
    const QRectF from = interrupted ? previous : (opening ? small : full);
    const QRectF to = opening ? full : small;
    const qreal opacityFrom = interrupted ? previousOpacity : (opening ? 0.0 : 1.0);
    const qreal opacityTo = opening ? 1.0 : 0.0;
    animateFrame(from, to, opacityFrom, opacityTo, opening ? 380 : 320,
                 opening ? QEasingCurve::OutCubic : QEasingCurve::InOutCubic);
}

void WindowEdge::animateFrame(const QRectF &from, const QRectF &to, qreal opacityFrom,
                              qreal opacityTo, int duration, QEasingCurve::Type easing)
{
    // Draw into the parent canvas so the animated sample is independent of child clipping.
    auto apply = [this, from, to, opacityFrom, opacityTo](qreal t) {
        m_transition->frame = QRectF(from.topLeft() + (to.topLeft() - from.topLeft()) * t,
                                     from.size() + (to.size() - from.size()) * t);
        m_transition->opacity = opacityFrom + (opacityTo - opacityFrom) * t;
        m_transition->update();
    };
    hide();
    apply(0);
    m_transition->show(); m_transition->raise();
    emit stackingRequested();
    m_windowAnimation.setDuration(duration);
    m_windowAnimation.setStartValue(0.0); m_windowAnimation.setEndValue(1.0);
    m_windowAnimation.setEasingCurve(easing);
    connect(&m_windowAnimation, &QVariantAnimation::valueChanged, this,
            [apply](const QVariant &v) { apply(v.toReal()); });
    m_windowAnimation.start();
}

void WindowEdge::closeEvent(QCloseEvent *event)
{
    m_windowAnimation.stop();
    if (m_geometryAnimating) {
        hide();
        setGeometry(m_geometryTarget);
        m_geometryAnimating = false;
    }
    if (m_transition) m_transition->hide();
    setState(State::Closed);
    QWidget::closeEvent(event);
}

void WindowEdge::setWindowName(const QString &name) { setWindowTitle(name); update(); }

bool WindowEdge::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == parentWidget() && event->type() == QEvent::Resize) {
        // Complete any pending transition before changing the desktop coordinate space.
        if (m_windowAnimation.state() == QAbstractAnimation::Running) {
            m_windowAnimation.stop();
            if (m_geometryAnimating) setGeometry(m_geometryTarget);
            m_geometryAnimating = false;
            if (m_transition) m_transition->hide();
            if (m_state == State::Running) {
                show(); raise(); emit stackingRequested();
            }
        }
        const qreal scale = parentWidget()->height() / 768.0;
        if (!qFuzzyCompare(scale, m_scale)) {
            const qreal ratio = scale / m_scale;
            const auto scaled = [ratio](const QRect &r) {
                return QRect(qRound(r.x() * ratio), qRound(r.y() * ratio),
                             qRound(r.width() * ratio), qRound(r.height() * ratio));
            };
            m_scale = scale;
            if (m_normalGeometry.isValid())
                m_normalGeometry = scaled(m_normalGeometry);
            if (!m_maximized) setGeometry(scaled(geometry()));
        }
        if (m_maximized) setGeometry(availableGeometry());
        updateChildGeometry(); update();
    }
    return QWidget::eventFilter(watched, event);
}

void WindowEdge::updateChildGeometry()
{
    int right = width() - qRound(8 * m_scale);
    // Lay out from the right: expanding a control moves only its left neighbours.
    for (int i = 2; i >= 0; --i) {
        if (!m_controls[i]) continue;
        m_controls[i]->setScale(m_scale);
        const int w = m_controls[i]->animatedWidth();
        m_controls[i]->setGeometry(right - w, qRound(9 * m_scale), w, qMax(1, qRound(22 * m_scale)));
        right -= w + qRound(6 * m_scale);
    }
}

void WindowEdge::paintEvent(QPaintEvent *)
{
    QPainter p(this); p.setRenderHint(QPainter::Antialiasing);
    QPainterPath silhouette;
    silhouette.addRoundedRect(QRectF(rect()), 12 * m_scale, 12 * m_scale);
    // Clip both surfaces to the same shape, preserving all four rounded corners.
    p.setClipPath(silhouette);
    p.fillRect(rect(), Qt::black);
    p.fillRect(QRectF(0, 0, width(), 40 * m_scale), QColor("#E6E6E6"));
    p.setPen(QColor("#3B3B3B"));
    QFont f = font(); f.setPixelSize(qMax(1, qRound(14 * m_scale))); f.setBold(true); p.setFont(f);
    const int reserve = width() - m_controls[0]->x() + qRound(8 * m_scale);
    const QRect titleRect(reserve, 0, qMax(0, width() - reserve * 2), qRound(40 * m_scale));
    p.drawText(titleRect, Qt::AlignCenter,
               QFontMetrics(f).elidedText(windowTitle(), Qt::ElideRight, titleRect.width()));
}

void WindowEdge::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event); updateChildGeometry();
}

void WindowEdge::mousePressEvent(QMouseEvent *event)
{
    if (event->button() == Qt::LeftButton) {
        raise();
        emit stackingRequested();
        m_resizeEdges = resizeEdgesAt(event->position());
        if (m_resizeEdges) {
            m_resizeStartGeometry = geometry();
            m_resizeStartGlobal = event->globalPosition().toPoint();
            event->accept();
            return;
        }
    }
    if (event->button() == Qt::LeftButton && event->position().y() < 40 * m_scale) {
        m_dragging = !m_maximized && m_windowAnimation.state() != QAbstractAnimation::Running;
        m_dragOffset = event->globalPosition().toPoint() - mapToGlobal(QPoint()); event->accept();
    } else QWidget::mousePressEvent(event);
}

void WindowEdge::mouseMoveEvent(QMouseEvent *event)
{
    if (m_resizeEdges && (event->buttons() & Qt::LeftButton)) {
        const QPoint delta = event->globalPosition().toPoint() - m_resizeStartGlobal;
        QRect target = m_resizeStartGeometry;
        const QRect area = availableGeometry();
        const int minWidth = qMin(area.width(), qRound(280 * m_scale));
        const int minHeight = qMin(area.height(), qRound(160 * m_scale));
        if (m_resizeEdges & Qt::LeftEdge)
            target.setLeft(qBound(area.left(), target.left() + delta.x(), target.right() - minWidth + 1));
        if (m_resizeEdges & Qt::RightEdge)
            target.setRight(qBound(target.left() + minWidth - 1, target.right() + delta.x(), area.right()));
        if (m_resizeEdges & Qt::BottomEdge)
            target.setBottom(qBound(target.top() + minHeight - 1, target.bottom() + delta.y(), area.bottom()));
        setGeometry(target);
        event->accept();
        return;
    }
    const Qt::Edges edges = resizeEdgesAt(event->position());
    if ((edges & Qt::BottomEdge) && (edges & Qt::LeftEdge)) setCursor(Qt::SizeBDiagCursor);
    else if ((edges & Qt::BottomEdge) && (edges & Qt::RightEdge)) setCursor(Qt::SizeFDiagCursor);
    else if (edges & Qt::BottomEdge) setCursor(Qt::SizeVerCursor);
    else if (edges) setCursor(Qt::SizeHorCursor);
    else unsetCursor();
    if (m_dragging && (event->buttons() & Qt::LeftButton)) {
        const QPoint target = event->globalPosition().toPoint() - m_dragOffset;
        QPoint position = parentWidget() ? parentWidget()->mapFromGlobal(target) : target;
        if (parentWidget()) {
            const QRect area = availableGeometry();
            position.setX(qBound(area.left(), position.x(), qMax(area.left(), area.right() - width() + 1)));
            position.setY(qBound(area.top(), position.y(), qMax(area.top(), area.bottom() - height() + 1)));
        }
        move(position); event->accept();
    } else QWidget::mouseMoveEvent(event);
}

void WindowEdge::mouseReleaseEvent(QMouseEvent *event)
{
    m_dragging = false; m_resizeEdges = {}; QWidget::mouseReleaseEvent(event);
}

void WindowEdge::mouseDoubleClickEvent(QMouseEvent *event)
{
    if (event->button() == Qt::LeftButton && event->position().y() < 40 * m_scale) {
        toggleMaximized(); event->accept();
    } else QWidget::mouseDoubleClickEvent(event);
}

void WindowEdge::toggleMaximized()
{
    if (m_windowAnimation.state() == QAbstractAnimation::Running) return;
    if (parentWidget()) {
        const QRect from = geometry();
        const QRect to = m_maximized ? m_normalGeometry : availableGeometry();
        if (!m_maximized) m_normalGeometry = from;
        disconnect(&m_windowAnimation, &QVariantAnimation::valueChanged, this, nullptr);
        m_maximized = !m_maximized;
        m_opening = true;
        m_geometryAnimating = true;
        m_geometryTarget = to;
        // Resize live widgets so the title bar is never stretched with a snapshot.
        m_windowAnimation.setDuration(380);
        m_windowAnimation.setStartValue(0.0);
        m_windowAnimation.setEndValue(1.0);
        m_windowAnimation.setEasingCurve(QEasingCurve::InOutCubic);
        connect(&m_windowAnimation, &QVariantAnimation::valueChanged, this,
                [this, from, to](const QVariant &value) {
            const qreal t = value.toReal();
            const auto lerp = [t](int a, int b) { return qRound(a + (b - a) * t); };
            setGeometry(lerp(from.x(), to.x()), lerp(from.y(), to.y()),
                        lerp(from.width(), to.width()), lerp(from.height(), to.height()));
        });
        m_windowAnimation.start();
    } else {
        m_maximized = !m_maximized;
        if (m_maximized) showMaximized(); else showNormal();
    }
    m_controls[1]->setRestored(m_maximized); updateChildGeometry(); update();
    emit maximizedChanged(m_maximized);
}

QRect WindowEdge::availableGeometry() const
{
    // Background supplies an area that excludes the top status strip.
    if (m_availableGeometry.isValid()) return m_availableGeometry;
    return parentWidget() ? parentWidget()->rect() : screen()->availableGeometry();
}

void WindowEdge::setAvailableGeometry(const QRect &geometry)
{
    m_availableGeometry = geometry;
    if (m_maximized) setGeometry(geometry);
}

Qt::Edges WindowEdge::resizeEdgesAt(const QPointF &position) const
{
    // The upper edge is intentionally excluded; only left, right, and bottom are resizable.
    if (m_maximized || m_windowAnimation.state() == QAbstractAnimation::Running) return {};
    const qreal border = qMax(4.0, 6 * m_scale);
    Qt::Edges edges;
    if (position.x() < border) edges |= Qt::LeftEdge;
    else if (position.x() >= width() - border) edges |= Qt::RightEdge;
    if (position.y() >= height() - border) edges |= Qt::BottomEdge;
    return edges;
}

void WindowEdge::leaveEvent(QEvent *event)
{
    if (!m_resizeEdges) unsetCursor();
    QWidget::leaveEvent(event);
}
