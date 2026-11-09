#include "status.h"
#include <QDateTime>
#include <QLabel>
#include <QLocale>
#include <QPainter>
#include <QPainterPath>
#include <QResizeEvent>
#include <cmath>

namespace {
class ClockLabel final : public QLabel
{
public:
    explicit ClockLabel(QWidget *parent) : QLabel(parent)
    {
        setAttribute(Qt::WA_NoSystemBackground);
    }
protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing);
        const QFontMetricsF metrics(font());
        const qreal baseline = (height() - metrics.height()) / 2.0 + metrics.ascent();
        QPainterPath glyphs;
        glyphs.addText(QPointF(0, baseline), font(), text());
        const QColor foreground = palette().color(QPalette::WindowText);
        QColor outline(foreground.lightness() > 128 ? Qt::black : Qt::white);
        outline.setAlpha(145);
        // A thin contrasting outline keeps text readable across mixed wallpaper details.
        painter.setPen(QPen(outline, qMax(1.0, height() / 28.0 * 1.25), Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
        painter.setBrush(Qt::NoBrush);
        painter.drawPath(glyphs);
        painter.fillPath(glyphs, foreground);
    }
};

qreal luminance(const QColor &color)
{
    // Convert sRGB channels to linear light before applying relative-luminance weights.
    const auto linear = [](qreal channel) {
        return channel <= 0.04045 ? channel / 12.92 : std::pow((channel + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * linear(color.redF()) + 0.7152 * linear(color.greenF()) + 0.0722 * linear(color.blueF());
}
}

Status::Status(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("Status"));
    setAttribute(Qt::WA_NoSystemBackground);
    m_clock = new ClockLabel(this);
    m_clock->setObjectName(QStringLiteral("StatusClock"));
    m_clock->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    m_clock->setAttribute(Qt::WA_TransparentForMouseEvents);
    // Reserve the right side for future volume, time/calendar and input method controls.
    // These controls are intentionally not created until their behavior is implemented.
    connect(&m_clockTimer, &QTimer::timeout, this, &Status::updateClock);
    m_clockTimer.start(1000);
    refreshGeometry();
    updateClock();
}

void Status::refreshGeometry()
{
    if (!parentWidget()) return;
    const qreal scale = parentWidget()->height() / 768.0;
    setGeometry(0, 0, parentWidget()->width(), qMax(1, qRound(28 * scale)));
}

void Status::updateClock()
{
    const QDateTime now = QDateTime::currentDateTime();
    const QLocale locale(QLocale::English);
    m_clock->setText(locale.toString(now, QStringLiteral("HH:mm   yyyy/M/d   ddd")));
    updateTextContrast();
}

void Status::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    const qreal scale = height() / 28.0;
    QFont textFont = font();
    textFont.setPixelSize(qMax(1, qRound(12 * scale)));
    m_clock->setFont(textFont);
    const int margin = qRound(12 * scale);
    m_clock->setGeometry(margin, 0, qMax(0, width() - margin * 2), height());
    updateTextContrast();
}

void Status::paintEvent(QPaintEvent *)
{
    // The status bar is transparent; only the clock label paints its glyphs.
}

void Status::setBackgroundImage(const QPixmap &image)
{
    m_wallpaper = image.toImage();
    updateTextContrast();
}

void Status::updateTextContrast()
{
    if (!m_clock || !parentWidget()) return;
    qreal light = luminance(parentWidget()->palette().color(QPalette::Window));
    if (!m_wallpaper.isNull()) {
        const int textWidth = qMin(m_clock->width(), QFontMetrics(m_clock->font()).horizontalAdvance(m_clock->text()));
        const QRect textArea(mapToParent(m_clock->pos()), QSize(textWidth, m_clock->height()));
        qreal total = 0;
        // Sample only the wallpaper underneath the displayed text, not the empty right side.
        for (int row = 0; row < 8; ++row) {
            for (int col = 0; col < 48; ++col) {
                const qreal x = textArea.x() + (col + 0.5) * textArea.width() / 48.0;
                const qreal y = textArea.y() + (row + 0.5) * textArea.height() / 8.0;
                const int sourceX = qBound(0, int(x * m_wallpaper.width() / qMax(1, parentWidget()->width())), m_wallpaper.width() - 1);
                const int sourceY = qBound(0, int(y * m_wallpaper.height() / qMax(1, parentWidget()->height())), m_wallpaper.height() - 1);
                total += luminance(m_wallpaper.pixelColor(sourceX, sourceY));
            }
        }
        light = total / (48 * 8);
    }
    // Select the foreground with the stronger WCAG-style contrast ratio against sampled wallpaper.
    const qreal whiteContrast = 1.05 / (light + 0.05);
    const qreal blackContrast = (light + 0.05) / 0.05;
    QPalette colors = m_clock->palette();
    colors.setColor(QPalette::WindowText, whiteContrast >= blackContrast ? Qt::white : Qt::black);
    m_clock->setPalette(colors);
    m_clock->update();
}
