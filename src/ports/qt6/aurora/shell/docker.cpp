// SPDX-License-Identifier: Apache-2.0
#include "docker.h"

#include <QCoreApplication>
#include <QDebug>
#include <QDir>
#include <QEvent>
#include <QFile>
#include <QFileInfo>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QPainter>
#include <QPainterPath>
#include <QPropertyAnimation>
#include <QScreen>
#include <QStyleHints>
#include "design_icon.h"
#include "system_context.h"
#include <QToolButton>
#include <QEasingCurve>
#include <QVariantAnimation>
#include <QResizeEvent>
#include <QCursor>
#include <QMouseEvent>

#include <algorithm>

namespace {
class DockNameLabel : public QLabel
{
public:
    DockNameLabel(QWidget *parent, Qt::WindowFlags flags)
        : QLabel(parent, flags)
    {
        setContentsMargins(10, 4, 10, 4);
        setAttribute(Qt::WA_TranslucentBackground);
    }

    void setColors(const QColor &background, const QColor &foreground)
    {
        m_background = background;
        m_foreground = foreground;
        update();
    }

protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing);
        painter.setPen(Qt::NoPen);
        painter.setBrush(m_background);
        painter.drawRoundedRect(QRectF(rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                                height() / 2.0, height() / 2.0);
        painter.setPen(m_foreground);
        painter.drawText(contentsRect(), alignment(), text());
    }

private:
    QColor m_background;
    QColor m_foreground;
};

// Layout position and hover offset are animated independently.
class DockIconButton : public QToolButton
{
public:
    DockIconButton(const QString &imagePath, QWidget *parent)
        : QToolButton(parent), m_renderer(imagePath), m_hoverAnimation(this), m_stateAnimation(this)
    {
        setFocusPolicy(Qt::NoFocus);
        setCursor(Qt::PointingHandCursor);
        setAttribute(Qt::WA_NoSystemBackground);
        connect(&m_hoverAnimation, &QVariantAnimation::valueChanged, this, [this](const QVariant &value) {
            m_lift = value.toReal();
            applyPosition();
        });
        connect(&m_stateAnimation, &QVariantAnimation::valueChanged, this, [this](const QVariant &value) {
            const qreal t = value.toReal();
            m_indicatorLength = m_startLength + (m_targetLength - m_startLength) * t;
            m_indicatorOpacity = m_startOpacity + (m_targetOpacity - m_startOpacity) * t;
            parentWidget()->update();
        });
    }

    QRect baseGeometry() const { return m_baseGeometry; }
    void setBaseGeometry(const QRect &geometry)
    {
        m_baseGeometry = geometry;
        resize(geometry.size());
        applyPosition();
    }
    void setAppearance(qreal scale) { m_iconScale = scale; update(); }
    qreal appearance() const { return m_iconScale; }
    qreal indicatorLength() const { return m_indicatorLength; }
    qreal indicatorOpacity() const { return m_indicatorOpacity; }
    void setApplicationState(Docker::ApplicationState state)
    {
        // Keep the lifecycle marker animated separately from icon appearance and hover lift.
        m_stateAnimation.stop();
        m_startLength = m_indicatorLength;
        m_startOpacity = m_indicatorOpacity;
        m_targetLength = state == Docker::ApplicationState::Minimized ? 0.065 : 0.30;
        m_targetOpacity = state == Docker::ApplicationState::Closed ? 0.0 : 1.0;
        m_stateAnimation.setDuration(260);
        m_stateAnimation.setStartValue(0.0);
        m_stateAnimation.setEndValue(1.0);
        m_stateAnimation.setEasingCurve(QEasingCurve::InOutCubic);
        m_stateAnimation.start();
    }

    void setMenuOpen(bool open)
    {
        m_menuOpen = open;
        // Keep muti lifted while its menu is visible, then animate back down.
        if (open && objectName() == QStringLiteral("muti"))
            m_hoverAnimation.stop();
        else
            setLift(0.0);
    }

protected:
    void enterEvent(QEnterEvent *event) override
    {
        QToolButton::enterEvent(event);
        if (!m_menuOpen)
            setLift(1.0);
    }
    void leaveEvent(QEvent *event) override
    {
        QToolButton::leaveEvent(event);
        if (!m_menuOpen)
            setLift(0.0);
    }
    void paintEvent(QPaintEvent *) override
    {
        if (m_iconScale <= 0.0)
            return;
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing);
        painter.translate(width() / 2.0, height() / 2.0);
        painter.scale(m_iconScale, m_iconScale);
        const QRectF image(-width() / 2.0, -height() / 2.0, width(), height());
        QPainterPath clip;
        clip.addRoundedRect(image, width() * 0.18, height() * 0.18);
        painter.setClipPath(clip);
        m_renderer.render(&painter, image);
    }

private:
    void setLift(qreal lift)
    {
        m_hoverAnimation.stop();
        m_hoverAnimation.setDuration(154);
        m_hoverAnimation.setStartValue(m_lift);
        m_hoverAnimation.setEndValue(lift);
        m_hoverAnimation.setEasingCurve(QEasingCurve::InOutCubic);
        m_hoverAnimation.start();
    }
    void applyPosition()
    {
        move(m_baseGeometry.topLeft() - QPoint(0, qRound(height() * 0.1 * m_lift)));
    }
    DesignIcon m_renderer;
    QVariantAnimation m_hoverAnimation;
    QVariantAnimation m_stateAnimation;
    qreal m_indicatorLength = 0.30, m_indicatorOpacity = 0.0;
    qreal m_startLength = 0.30, m_targetLength = 0.30;
    qreal m_startOpacity = 0.0, m_targetOpacity = 0.0;
    QRect m_baseGeometry;
    qreal m_iconScale = 1.0;
    qreal m_lift = 0.0;
    bool m_menuOpen = false;
};
}

Docker::Docker(QWidget *parent)
    : QWidget(parent), m_layoutAnimation(this), m_visibilityAnimation(this)
{
    setObjectName(QStringLiteral("Docker"));
    // A child widget composites the translucent surface over Background's image.
    setAutoFillBackground(false);
    connect(&m_visibilityAnimation, &QVariantAnimation::valueChanged, this, [this](const QVariant &v) {
        m_hideProgress = v.toReal();
        updateDockPosition();
    });
    // Polling complements mouse events when the pointer moves over child widgets or gaps.
    m_pointerTimer.setInterval(50);
    connect(&m_pointerTimer, &QTimer::timeout, this, &Docker::checkPointerPosition);
    m_hideDelay.setSingleShot(true);
    m_hideDelay.setInterval(400);
    connect(&m_hideDelay, &QTimer::timeout, this, [this] {
        if (m_autoHideEnabled && !m_menuOpen) setDockRevealed(false);
    });

    m_nameLabel = new DockNameLabel(parentWidget(), Qt::Widget);
    m_nameLabel->hide();
    m_nameLabel->setObjectName(QStringLiteral("DockNameLabel"));
    m_nameLabel->setAlignment(Qt::AlignCenter);
    m_nameLabel->setAttribute(Qt::WA_ShowWithoutActivating);
    m_nameLabel->setAttribute(Qt::WA_TransparentForMouseEvents);
    updateNameLabelAppearance();

    m_configPath = QStringLiteral(":/aurora/catalog");

    loadConfiguration();
    QCoreApplication::instance()->installEventFilter(this);
    connect(QGuiApplication::styleHints(), &QStyleHints::colorSchemeChanged,
            this, [this] {
                update();
                updateNameLabelAppearance();
            });
    updateGeometryFromBackground();
}

void Docker::loadConfiguration()
{
    const QJsonObject docker = auroraSystemConfiguration().value(QStringLiteral("docker")).toObject();

    const QJsonObject icons = docker.value(QStringLiteral("icon")).toObject();
    for (auto it = icons.begin(); it != icons.end(); ++it)
        m_iconPaths.insert(it.key(), it.value().toString());

    // The reserved expansion button always occupies the first slot.
    QToolButton *muti = createButton(QStringLiteral("muti"), QStringLiteral("icon/muti.svg"));
    connect(muti, &QToolButton::clicked, this, &Docker::expansionRequested);

    const QJsonArray frontApps = docker.value(QStringLiteral("frontapps")).toArray();
    for (const QJsonValue &appValue : frontApps) {
        const QString appName = appValue.toString().trimmed();
        if (appName.isEmpty() || appName == QStringLiteral("muti"))
            continue;

        createButton(appName, m_iconPaths.value(appName));
    }
}

QToolButton *Docker::createButton(const QString &name, const QString &iconPath)
{
    auto *button = new DockIconButton(auroraIconPath(name, iconPath), this);
    button->setObjectName(name);
    button->setAccessibleName(name);
    m_appButtons.append(button);
    button->installEventFilter(this);
    button->setMenuOpen(m_menuOpen);
    connect(button, &QToolButton::clicked, this, [this, name] {
        hideNameLabel();
        emit applicationActivated(name);
    });
    return button;
}

void Docker::addAppToDock(const QString &appName)
{
    if (appName.isEmpty() || appName == QStringLiteral("muti"))
        return;
    QToolButton *button = nullptr;
    qsizetype oldIndex = -1;
    for (qsizetype i = 0; i < m_appButtons.size(); ++i) {
        if (m_appButtons[i]->objectName().compare(appName, Qt::CaseInsensitive) == 0) {
            button = m_appButtons[i];
            oldIndex = i;
            break;
        }
    }
    if (button && button->objectName() == QStringLiteral("trash"))
        return;

    if (button)
        m_appButtons.removeAt(oldIndex);
    else {
        button = createButton(appName, m_iconPaths.value(appName));
        m_appButtons.removeOne(button);
    }

    // Trash remains the final system action when an app is selected from the browser.
    auto trash = std::find_if(m_appButtons.cbegin(), m_appButtons.cend(), [](QToolButton *candidate) {
        return candidate->objectName() == QStringLiteral("trash");
    });
    const qsizetype targetIndex = trash == m_appButtons.cend()
                                      ? m_appButtons.size()
                                      : std::distance(m_appButtons.cbegin(), trash);
    m_appButtons.insert(targetIndex, button);
    updateGeometryFromBackground(true, oldIndex < 0 ? button : nullptr);
}

Docker::ApplicationState Docker::applicationState(const QString &appName) const
{
    return m_applicationStates.value(appName.toLower(), ApplicationState::Closed);
}

void Docker::setApplicationState(const QString &appName, ApplicationState state)
{
    if (appName.isEmpty() || appName == QStringLiteral("muti") || appName == QStringLiteral("trash"))
        return;
    if (applicationState(appName) == state)
        return;
    m_applicationStates.insert(appName.toLower(), state);
    for (auto *button : m_appButtons) {
        if (button->objectName().compare(appName, Qt::CaseInsensitive) == 0) {
            static_cast<DockIconButton *>(button)->setApplicationState(state);
            break;
        }
    }
}

QRect Docker::applicationIconGeometry(const QString &appName) const
{
    for (auto *button : m_appButtons) {
        if (button->objectName().compare(appName, Qt::CaseInsensitive) == 0) {
            const QRect slot = static_cast<DockIconButton *>(button)->baseGeometry();
            const QPoint origin = parentWidget() ? parentWidget()->mapToGlobal(m_layoutGeometry.topLeft())
                                                  : mapToGlobal(QPoint());
            return QRect(origin + slot.topLeft(), slot.size());
        }
    }
    return QRect();
}

void Docker::updateGeometryFromBackground(bool animate, QToolButton *newButton)
{
    // Compute the target from icon count; all dimensions use the desktop-height scale.
    m_layoutAnimation.stop();
    disconnect(&m_layoutAnimation, nullptr, this, nullptr);
    const int backgroundHeight = parentWidget() ? parentWidget()->height() : 768;
    const qreal scale = backgroundHeight / 768.0;
    const qreal dockHeight = 63.0 * scale;
    const qreal side = dockHeight * 0.7142;
    const qreal gap = side * 0.1778;
    const int targetWidth = qMax(1, qRound(m_appButtons.size() * side + (m_appButtons.size() + 1) * gap));
    const int targetHeight = qMax(1, qRound(dockHeight));
    m_cornerRadius = 13.0 * scale;
    m_bottomMargin = backgroundHeight * 0.007;
    const QRect target(qRound(((parentWidget() ? parentWidget()->width() : targetWidth) - targetWidth) / 2.0),
                       parentWidget() ? parentWidget()->height() - targetHeight - qRound(m_bottomMargin) : 0,
                       targetWidth, targetHeight);
    QList<QRect> starts;
    QList<QRect> targets;
    QList<qreal> startScales;
    for (qsizetype i = 0; i < m_appButtons.size(); ++i) {
        auto *button = static_cast<DockIconButton *>(m_appButtons[i]);
        const QRect slot(qRound(gap + i * (side + gap)), qRound((dockHeight - side) / 2.0),
                          qMax(1, qRound(side)), qMax(1, qRound(side)));
        starts.append(button == newButton ? slot : button->baseGeometry());
        targets.append(slot);
        startScales.append(button == newButton ? 0.0 : button->appearance());
        if (button == newButton) {
            button->setBaseGeometry(slot);
            button->setAppearance(0.0);
            button->show();
        }
    }
    // Preserve the logical resting geometry while the visible widget may be sliding away.
    const QRect start = m_layoutGeometry.isValid() ? m_layoutGeometry : geometry();
    auto apply = [this, start, target, starts, targets, startScales](qreal progress) {
        const auto interpolate = [progress](int a, int b) { return qRound(a + (b - a) * progress); };
        m_layoutGeometry = QRect(interpolate(start.x(), target.x()), interpolate(start.y(), target.y()),
                                 interpolate(start.width(), target.width()), interpolate(start.height(), target.height()));
        updateDockPosition();
        for (qsizetype i = 0; i < m_appButtons.size(); ++i) {
            const QRect from = starts[i];
            const QRect to = targets[i];
            static_cast<DockIconButton *>(m_appButtons[i])->setBaseGeometry(
                QRect(interpolate(from.x(), to.x()), interpolate(from.y(), to.y()),
                      interpolate(from.width(), to.width()), interpolate(from.height(), to.height())));
            static_cast<DockIconButton *>(m_appButtons[i])->setAppearance(
                startScales[i] + (1.0 - startScales[i]) * progress);
        }
        update();
    };
    if (animate && isVisible()) {
        m_layoutAnimation.setDuration(364);
        m_layoutAnimation.setStartValue(0.0);
        m_layoutAnimation.setEndValue(1.0);
        m_layoutAnimation.setEasingCurve(QEasingCurve::OutCubic);
        connect(&m_layoutAnimation, &QVariantAnimation::valueChanged, this,
                [apply](const QVariant &value) { apply(value.toReal()); });
        m_layoutAnimation.start();
    } else {
        apply(1.0);
    }
}

void Docker::setMenuOpen(bool open)
{
    m_menuOpen = open;
    if (open) {
        m_hideDelay.stop();
        setDockRevealed(true);
    } else if (m_autoHideEnabled) checkPointerPosition();
    hideNameLabel();
    for (QToolButton *button : m_appButtons)
        static_cast<DockIconButton *>(button)->setMenuOpen(open);
}

void Docker::setAutoHideEnabled(bool enabled)
{
    if (m_autoHideEnabled == enabled) return;
    m_autoHideEnabled = enabled;
    m_hideDelay.stop();
    if (enabled) {
        m_pointerTimer.start();
        setDockRevealed(m_menuOpen);
    } else {
        m_pointerTimer.stop();
        setDockRevealed(true);
    }
}

void Docker::updateDockPosition()
{
    // Auto-hide changes only the surface position; icon slot coordinates remain stable.
    QRect position = m_layoutGeometry;
    if (parentWidget())
        position.moveTop(qRound(position.y() + (parentWidget()->height() - position.y()) * m_hideProgress));
    setGeometry(position);
}

void Docker::setDockRevealed(bool revealed)
{
    if (m_dockRevealed == revealed) return;
    m_dockRevealed = revealed;
    if (!revealed) hideNameLabel();
    m_visibilityAnimation.stop();
    m_visibilityAnimation.setDuration(300);
    m_visibilityAnimation.setStartValue(m_hideProgress);
    m_visibilityAnimation.setEndValue(revealed ? 0.0 : 1.0);
    m_visibilityAnimation.setEasingCurve(QEasingCurve::InOutCubic);
    m_visibilityAnimation.start();
    raise();
}

void Docker::checkPointerPosition()
{
    updatePointerPosition(QCursor::pos());
}

void Docker::updatePointerPosition(const QPoint &globalPosition)
{
    if (!m_autoHideEnabled || !parentWidget()) return;
    const QPoint pointer = parentWidget()->mapFromGlobal(globalPosition);
    const qreal scale = parentWidget()->height() / 768.0;
    // Reveal at the physical edge of this desktop canvas or while the pointer uses the Dock.
    const bool atBottom = parentWidget()->rect().contains(pointer)
        && pointer.y() >= parentWidget()->height() - qMax(4, qRound(12 * scale));
    const bool overDock = m_dockRevealed && geometry().adjusted(-8, -8, 8, 0).contains(pointer);
    if (m_menuOpen || atBottom || overDock) {
        m_hideDelay.stop();
        setDockRevealed(true);
    } else if (m_dockRevealed && !m_hideDelay.isActive()) {
        m_hideDelay.start();
    }
}
void Docker::showNameLabel(QToolButton *button)
{
    if (!button || !button->isVisible())
        return;
    if (m_menuOpen)
        return;

    m_hoveredButton = button;
    m_nameLabel->setText(button->accessibleName());
    m_nameLabel->adjustSize();

    QScreen *screen = QGuiApplication::screenAt(button->mapToGlobal(button->rect().center()));
    if (!screen)
        screen = QGuiApplication::primaryScreen();
    if (!screen)
        return;

    const QRect screenGeometry = screen->availableGeometry();
    const QPoint dockTopLeft = mapToGlobal(QPoint(0, 0));
    // Anchor the name capsule to the screen rather than to the hovered icon.
    const int screenGap = qRound(screen->geometry().height() * 0.05);
    const int x = screenGeometry.left() + (screenGeometry.width() - m_nameLabel->width()) / 2;
    const int y = dockTopLeft.y() - screenGap - m_nameLabel->height();

    m_nameLabel->move(parentWidget()->mapFromGlobal(QPoint(x, y)));
    m_nameLabel->show();
    m_nameLabel->raise();
}

void Docker::updateNameLabelAppearance()
{
    // Follow the active Qt color scheme, with the palette as fallback when unspecified.
    const Qt::ColorScheme scheme = QGuiApplication::styleHints()->colorScheme();
    const bool darkMode = scheme == Qt::ColorScheme::Dark
        || (scheme == Qt::ColorScheme::Unknown && palette().window().color().lightness() < 128);
    QColor background(darkMode ? QStringLiteral("#3A3A3A") : QStringLiteral("#DEDEDE"));
    background.setAlphaF(0.5);
    auto *label = static_cast<DockNameLabel *>(m_nameLabel);
    label->setColors(background, darkMode ? Qt::white : QColor(QStringLiteral("#202020")));
}

void Docker::hideNameLabel()
{
    m_hoveredButton = nullptr;
    m_nameLabel->hide();
}

bool Docker::eventFilter(QObject *watched, QEvent *event)
{
    if (event->type() == QEvent::MouseMove)
        updatePointerPosition(static_cast<QMouseEvent *>(event)->globalPosition().toPoint());
    if (watched == parentWidget()
        && (event->type() == QEvent::Resize || event->type() == QEvent::Show)) {
        updateGeometryFromBackground();
    } else if (auto *button = qobject_cast<QToolButton *>(watched)) {
        if (m_appButtons.contains(button)) {
            if (event->type() == QEvent::Enter)
                showNameLabel(button);
            else if (event->type() == QEvent::Leave && button == m_hoveredButton)
                hideNameLabel();
        }
    }

    return QWidget::eventFilter(watched, event);
}

void Docker::paintEvent(QPaintEvent *event)
{
    Q_UNUSED(event);

    const Qt::ColorScheme scheme = QGuiApplication::styleHints()->colorScheme();
    const bool darkMode = scheme == Qt::ColorScheme::Dark
        || (scheme == Qt::ColorScheme::Unknown && palette().window().color().lightness() < 128);
    QColor backgroundColor(darkMode ? QStringLiteral("#3A3A3A") : QStringLiteral("#DEDEDE"));
    backgroundColor.setAlphaF(0.5);

    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.setPen(Qt::NoPen);
    painter.setBrush(backgroundColor);
    painter.drawRoundedRect(QRectF(rect()), m_cornerRadius, m_cornerRadius);
    // Indicators stay below the stable icon slots, independent of hover lift.
    for (auto *button : m_appButtons) {
        const auto *icon = static_cast<DockIconButton *>(button);
        if (icon->indicatorOpacity() <= 0.0)
            continue;
        const QRectF slot = icon->baseGeometry();
        const qreal thickness = slot.width() * 0.065;
        const qreal length = slot.width() * icon->indicatorLength();
        const qreal centerY = (slot.bottom() + height()) / 2.0;
        QColor color(darkMode ? "#F5F5F5" : "#303030");
        color.setAlphaF(icon->indicatorOpacity() * icon->appearance());
        painter.setBrush(color);
        painter.drawRoundedRect(QRectF(slot.center().x() - length / 2.0,
                                      centerY - thickness / 2.0, length, thickness),
                                thickness / 2.0, thickness / 2.0);
    }
}
