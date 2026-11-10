// SPDX-License-Identifier: Apache-2.0
#ifndef STATUS_H
#define STATUS_H

#include <QWidget>
#include <QTimer>
#include <QImage>
#include <QPixmap>

class QLabel;

class Status : public QWidget
{
    Q_OBJECT

public:
    /** Create a transparent, proportionally sized clock strip. */
    explicit Status(QWidget *parent = nullptr);
    /** Recalculate the strip rectangle after its desktop parent changes size. */
    void refreshGeometry();
    /** Provide the wallpaper used to choose clock text contrast. */
    void setBackgroundImage(const QPixmap &image);

protected:
    void paintEvent(QPaintEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;

private:
    void updateClock();
    void updateTextContrast();
    QLabel *m_clock = nullptr;
    QTimer m_clockTimer;
    // A decoded copy keeps repeated luminance sampling independent of SVG/paint state.
    QImage m_wallpaper;
};

#endif // STATUS_H
