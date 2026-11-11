// SPDX-License-Identifier: Apache-2.0
#include "applicationbrowser.h"

#include <QDebug>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QGraphicsBlurEffect>
#include <QGraphicsPixmapItem>
#include <QGraphicsScene>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QResizeEvent>
#include <QScrollArea>
#include <QScrollBar>
#include <QSignalBlocker>
#include "design_icon.h"
#include "system_context.h"
#include <QToolButton>
#include <algorithm>

namespace {
constexpr int OpenDuration = 455;
constexpr int CloseDuration = 266;

// Draw the capsule from the actual widget bounds, without repolishing a style
// sheet on every animation frame (fractional CSS radii caused square frames).
class SearchField final : public QLineEdit
{
public:
    explicit SearchField(QWidget *parent) : QLineEdit(parent)
    {
        setFrame(false);
        setFocusPolicy(Qt::ClickFocus);
        setStyleSheet(QStringLiteral("QLineEdit { border: none; background: transparent; padding: 0; }"));
    }

    void setAppearance(qreal progress, qreal scale)
    {
        m_progress = progress;
        QPalette colors = palette();
        colors.setColor(QPalette::Text, QColor(30, 30, 35, qRound(255 * progress)));
        colors.setColor(QPalette::PlaceholderText, QColor(75, 75, 80, qRound(220 * progress)));
        setPalette(colors);
        QFont scaledFont = font();
        scaledFont.setPixelSize(qMax(1, qRound(14 * scale)));
        setFont(scaledFont);
        const int margin = qMax(1, qRound(12 * scale));
        setTextMargins(margin, 0, margin, 0);
        update();
    }

protected:
    void mousePressEvent(QMouseEvent *event) override
    {
        setFocus(Qt::MouseFocusReason);
        QLineEdit::mousePressEvent(event);
    }

    void paintEvent(QPaintEvent *event) override
    {
        {
            QPainter painter(this);
            painter.setRenderHint(QPainter::Antialiasing);
            painter.setPen(Qt::NoPen);
            painter.setBrush(QColor(222, 222, 226, qRound(205 * m_progress)));
            const QRectF capsule = QRectF(rect()).adjusted(0.5, 0.5, -0.5, -0.5);
            painter.drawRoundedRect(capsule, capsule.height() / 2.0, capsule.height() / 2.0);
        }
        QLineEdit::paintEvent(event);
    }

private:
    qreal m_progress = 0.0;
};

// The icon and its caption share a stable hit rectangle throughout the animation.
class ApplicationTile final : public QToolButton
{
public:
    ApplicationTile(const QString &name, const QString &path, QWidget *parent)
        : QToolButton(parent), m_name(name), m_svg(path)
    {
        setObjectName(QStringLiteral("app_%1").arg(name));
        setAccessibleName(name);
        setCursor(Qt::PointingHandCursor);
        setAutoFillBackground(false);
        setAttribute(Qt::WA_NoSystemBackground);
    }

    void setProgress(qreal progress) { m_progress = progress; update(); }

protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing);
        painter.setOpacity(m_progress);
        const qreal side = width();
        const qreal scaledSide = side * m_progress;
        const QRectF imageRect((side - scaledSide) / 2.0, (side - scaledSide) / 2.0,
                               scaledSide, scaledSide);
        if (m_svg.isValid() && scaledSide > 0.0) {
            painter.save();
            QPainterPath clip;
            clip.addRoundedRect(imageRect, scaledSide * 0.15, scaledSide * 0.15);
            painter.setClipPath(clip);
            // No button background: transparent SVG margins must stay transparent.
            m_svg.render(&painter, imageRect);
            painter.restore();
        }
        painter.setPen(QColor(245, 245, 248));
        painter.setFont(font());
        const QString caption = QFontMetrics(font()).elidedText(m_name, Qt::ElideRight, width());
        const QRectF captionRect(0, side + side * 0.07, width(), height() - side * 1.07);
        const QPointF center = captionRect.center();
        painter.translate(center);
        painter.scale(m_progress, m_progress);
        painter.translate(-center);
        painter.drawText(captionRect,
                         Qt::AlignHCenter | Qt::AlignTop, caption);
    }

private:
    QString m_name;
    DesignIcon m_svg;
    qreal m_progress = 0.0;
};
}

ApplicationBrowser::ApplicationBrowser(QWidget *background, const QString &configPath)
    : QWidget(background), m_configPath(configPath), m_transition(this)
{
    setObjectName(QStringLiteral("ApplicationBrowser"));
    setFocusPolicy(Qt::StrongFocus);
    setAttribute(Qt::WA_NoSystemBackground);

    m_search = new SearchField(this);
    m_search->setObjectName(QStringLiteral("ApplicationSearch"));
    m_search->setPlaceholderText(tr("Search"));
    m_search->setAlignment(Qt::AlignCenter);
    m_search->setClearButtonEnabled(true);
    m_search->installEventFilter(this);

    m_scrollArea = new QScrollArea(this);
    m_scrollArea->setObjectName(QStringLiteral("ApplicationGroups"));
    m_scrollArea->setFrameShape(QFrame::NoFrame);
    m_scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_scrollArea->setWidgetResizable(false);
    m_scrollArea->setStyleSheet(QStringLiteral(
        "QScrollArea { background: transparent; border: none; }"
        "QScrollBar:vertical { background: transparent; width: 6px; }"
        "QScrollBar::handle:vertical { background: rgba(255,255,255,90); min-height: 24px; border-radius: 3px; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"));
    m_scrollArea->viewport()->setAutoFillBackground(false);
    m_scrollArea->viewport()->installEventFilter(this);
    m_content = new QWidget;
    m_content->setObjectName(QStringLiteral("ApplicationGroupContainer"));
    m_content->setAutoFillBackground(false);
    m_content->installEventFilter(this);
    m_scrollArea->setWidget(m_content);
    m_content->setAutoFillBackground(false);

    connect(m_search, &QLineEdit::textChanged, this, [this] { rebuildGroups(); });
    connect(&m_transition, &QVariantAnimation::valueChanged, this,
            [this](const QVariant &value) { applyProgress(value.toReal()); });
    connect(&m_transition, &QVariantAnimation::finished, this, [this] {
        if (m_state == State::Closing) {
            const QString app = m_pendingApp;
            m_pendingApp.clear();
            m_state = State::Closed;
            hide();
            emit dismissed();
            if (!app.isEmpty())
                emit applicationLaunched(app);
        } else if (m_state == State::Opening) {
            m_state = State::Open;
        }
    });
    background->installEventFilter(this);
    hide();
}

void ApplicationBrowser::loadApplications()
{
    // Re-read the catalog on every fresh opening so configuration edits take effect immediately.
    m_applications.clear();
    m_icons.clear();
    const QJsonObject config = auroraSystemConfiguration().value(QStringLiteral("docker")).toObject();
    for (const auto &value : config.value(QStringLiteral("allapps")).toArray()) {
        const QString name = value.toString().trimmed();
        if (!name.isEmpty() && !m_applications.contains(name, Qt::CaseInsensitive))
            m_applications.append(name);
    }
    std::sort(m_applications.begin(), m_applications.end(), [](const QString &a, const QString &b) {
        return QString::compare(a, b, Qt::CaseInsensitive) < 0;
    });
    const auto icons = config.value(QStringLiteral("icon")).toObject();
    for (auto it = icons.begin(); it != icons.end(); ++it)
        m_icons.insert(it.key(), it.value().toString());
}

QString ApplicationBrowser::iconPathFor(const QString &appName) const
{
    return auroraIconPath(appName, m_icons.value(appName));
}

void ApplicationBrowser::rebuildGroups()
{
    qDeleteAll(m_tiles);
    qDeleteAll(m_headings);
    m_tiles.clear();
    m_headings.clear();
    const int side = qMax(1, qRound(92 * m_scale));
    const int gap = qMax(1, qRound(20 * m_scale));
    const int tileHeight = qMax(side + 1, qRound(124 * m_scale));
    const int headingHeight = qMax(1, qRound(32 * m_scale));
    // Reserve scrollbar width so crossing the scroll threshold cannot change columns.
    const int availableWidth = qMax(1, m_scrollArea->width() - 8);
    const int columns = qMax(1, (availableWidth + gap) / (side + gap));
    // Lay each alphabetical section out as a stable row-major grid.
    QChar currentLetter;
    int y = 0;
    int groupIndex = 0;
    const QString query = m_search->text().trimmed();
    for (const QString &name : m_applications) {
        if (!name.contains(query, Qt::CaseInsensitive))
            continue;
        QChar letter = name.front().toUpper();
        if (letter < QLatin1Char('A') || letter > QLatin1Char('Z'))
            letter = QLatin1Char('#');
        if (letter != currentLetter) {
            if (!currentLetter.isNull())
                y += ((groupIndex + columns - 1) / columns) * (tileHeight + gap) + qRound(6 * m_scale);
            currentLetter = letter;
            groupIndex = 0;
            auto *heading = new QLabel(QString(letter), m_content);
            heading->setObjectName(QStringLiteral("group_%1").arg(letter));
            QFont font = heading->font();
            font.setPixelSize(qMax(1, qRound(28 * m_scale)));
            heading->setFont(font);
            heading->setGeometry(qRound(8 * m_scale), y, availableWidth - qRound(8 * m_scale), headingHeight);
            heading->setAttribute(Qt::WA_TransparentForMouseEvents);
            m_headings.append(heading);
            heading->show();
            y += headingHeight + qRound(10 * m_scale);
        }
        auto *tile = new ApplicationTile(name, iconPathFor(name), m_content);
        QFont font = tile->font();
        font.setPixelSize(qMax(1, qRound(18 * m_scale)));
        tile->setFont(font);
        tile->setGeometry((groupIndex % columns) * (side + gap),
                          y + (groupIndex / columns) * (tileHeight + gap), side, tileHeight);
        tile->installEventFilter(this);
        connect(tile, &QToolButton::clicked, this, [this, name] { closeAnimated(name); });
        m_tiles.append(tile);
        tile->show();
        ++groupIndex;
    }
    if (groupIndex)
        y += ((groupIndex + columns - 1) / columns) * (tileHeight + gap);
    m_content->resize(availableWidth, qMax(y, m_scrollArea->viewport()->height()));
    applyProgress(m_progress);
}

void ApplicationBrowser::updateLayout()
{
    // Fit the browser layout to the smaller axis so the grid keeps a consistent visual scale.
    m_scale = qMax(0.1, qMin(width() / 1024.0, height() / 768.0));
    const int searchHeight = qMax(1, qRound(30 * m_scale));
    const int searchWidth = qMin(qRound(260 * m_scale), qRound(width() * 0.65));
    m_searchTarget = QRect((width() - searchWidth) / 2, qRound(52 * m_scale), searchWidth, searchHeight);
    const int left = qRound(width() * 0.084);
    const int top = qRound(120 * m_scale);
    m_scrollArea->setGeometry(left, top, qMax(1, width() - 2 * left),
                              qMax(1, height() - top - qRound(28 * m_scale)));
    rebuildGroups();
}

void ApplicationBrowser::applyProgress(qreal progress)
{
    // Every foreground element shares this progress to keep entry and exit synchronized.
    m_progress = qBound(0.0, progress, 1.0);
    const qreal searchScale = 0.65 + 0.35 * m_progress;
    const QSize searchSize(qMax(1, qRound(m_searchTarget.width() * searchScale)),
                           qMax(1, qRound(m_searchTarget.height() * searchScale)));
    const QPointF center = QRectF(m_searchTarget).center();
    m_search->setGeometry(qRound(center.x() - searchSize.width() / 2.0),
                          qRound(center.y() - searchSize.height() / 2.0), searchSize.width(), searchSize.height());
    static_cast<SearchField *>(m_search)->setAppearance(m_progress, m_scale * searchScale);
    m_search->setVisible(m_progress > 0.01);
    for (QToolButton *tile : m_tiles)
        static_cast<ApplicationTile *>(tile)->setProgress(m_progress);
    for (QLabel *heading : m_headings) {
        QPalette palette = heading->palette();
        palette.setColor(QPalette::WindowText, QColor(245, 245, 248, qRound(235 * m_progress)));
        heading->setPalette(palette);
    }
    update();
}

void ApplicationBrowser::captureBackground()
{
    // Cache both desktop states once; the transition only crossfades these images.
    m_snapshot = parentWidget()->grab();
    // Blur once per opening, then crossfade cached images during the animation.
    // This avoids running a full-window blur on every frame or blurring the controls.
    QGraphicsScene scene;
    auto *item = scene.addPixmap(m_snapshot);
    auto *blur = new QGraphicsBlurEffect;
    blur->setBlurHints(QGraphicsBlurEffect::QualityHint);
    blur->setBlurRadius(18 * m_scale);
    item->setGraphicsEffect(blur);
    QPixmap result(size() * m_snapshot.devicePixelRatio());
    result.setDevicePixelRatio(m_snapshot.devicePixelRatio());
    result.fill(Qt::transparent);
    QPainter painter(&result);
    scene.render(&painter, QRectF(rect()), QRectF(rect()));
    painter.end();
    m_blurredSnapshot = result;
}

void ApplicationBrowser::open()
{
    if (m_state == State::Open || m_state == State::Opening)
        return;
    // Reversing a close keeps its current progress instead of rebuilding the snapshot.
    const bool reversing = m_state == State::Closing;
    m_transition.stop();
    m_pendingApp.clear();
    if (!reversing) {
        hide();
        loadApplications();
        const QSignalBlocker blocker(m_search);
        m_search->clear();
        setGeometry(parentWidget()->rect());
        updateLayout();
        m_scrollArea->verticalScrollBar()->setValue(0);
        captureBackground();
        applyProgress(0.0);
    }
    m_state = State::Opening;
    show();
    raise();
    m_search->clearFocus();
    setFocus(Qt::OtherFocusReason);
    m_transition.setDuration(qMax(1, qRound(OpenDuration * (1.0 - m_progress))));
    m_transition.setEasingCurve(QEasingCurve::OutCubic);
    m_transition.setStartValue(m_progress);
    m_transition.setEndValue(1.0);
    m_transition.start();
}

void ApplicationBrowser::dismiss() { closeAnimated(); }

void ApplicationBrowser::closeAnimated(const QString &appName)
{
    if (m_state == State::Closed || m_state == State::Closing)
        return;
    m_transition.stop();
    // Launch the selected app only after the browser has finished its exit animation.
    m_pendingApp = appName;
    m_state = State::Closing;
    m_transition.setDuration(CloseDuration);
    m_transition.setEasingCurve(QEasingCurve::InOutCubic);
    m_transition.setStartValue(m_progress);
    m_transition.setEndValue(0.0);
    m_transition.start();
}

bool ApplicationBrowser::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == parentWidget() && event->type() == QEvent::Resize) {
        setGeometry(parentWidget()->rect());
    } else if (isVisible() && event->type() == QEvent::KeyPress
               && static_cast<QKeyEvent *>(event)->key() == Qt::Key_Escape) {
        dismiss();
        return true;
    } else if (isVisible() && event->type() == QEvent::MouseButtonPress
               && (watched == m_content || watched == m_scrollArea->viewport())) {
        if (static_cast<QMouseEvent *>(event)->button() == Qt::LeftButton) {
            dismiss();
            return true;
        }
    }
    return QWidget::eventFilter(watched, event);
}

void ApplicationBrowser::paintEvent(QPaintEvent *)
{
    QPainter painter(this);
    painter.drawPixmap(rect(), m_snapshot);
    painter.setOpacity(m_progress);
    painter.drawPixmap(rect(), m_blurredSnapshot);
    painter.setOpacity(1.0);
    // Paint the dimming above the snapshot, below the search and app controls.
    painter.fillRect(rect(), QColor(0, 0, 0, qRound(128 * m_progress)));
}

void ApplicationBrowser::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updateLayout();
}

void ApplicationBrowser::mousePressEvent(QMouseEvent *event)
{
    if (event->button() == Qt::LeftButton)
        dismiss();
    else
        QWidget::mousePressEvent(event);
}

void ApplicationBrowser::keyPressEvent(QKeyEvent *event)
{
    if (event->key() == Qt::Key_Escape)
        dismiss();
    else
        QWidget::keyPressEvent(event);
}
