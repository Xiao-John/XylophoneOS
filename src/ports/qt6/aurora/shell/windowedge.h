#ifndef WINDOWEDGE_H
#define WINDOWEDGE_H

#include <QWidget>
#include <QVariantAnimation>

class WindowControl;
class QMouseEvent;
class QPaintEvent;
class QResizeEvent;
class QCloseEvent;
class WindowTransition;

class WindowEdge : public QWidget
{
    Q_OBJECT

public:
    /** Window lifecycle state; maximization is tracked independently. */
    enum class State { Closed, Running, Minimized };
    Q_ENUM(State)
    /** Construct the rounded Example Window surface and its title controls. */
    explicit WindowEdge(QWidget *parent = nullptr);
    /** Set both the native window title and the custom painted title text. */
    void setWindowName(const QString &name);
    /** Launch or restore using the current Dock icon as the transition origin. */
    void openAnimated(const QRect &dockIconGlobalGeometry);
    /** Transition the live window toward its Dock icon and mark it minimized. */
    void minimizeAnimated();
    /** Set the usable desktop area, excluding shell surfaces such as the status bar. */
    void setAvailableGeometry(const QRect &geometry);
    bool isMaximized() const { return m_maximized; }
    State state() const { return m_state; }

signals:
    void stateChanged(WindowEdge::State state);
    void maximizedChanged(bool maximized);
    void stackingRequested();

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;
    void mouseDoubleClickEvent(QMouseEvent *event) override;
    void paintEvent(QPaintEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;
    void closeEvent(QCloseEvent *event) override;
    void leaveEvent(QEvent *event) override;

private:
    void updateChildGeometry();
    void toggleMaximized();
    void animateWindow(bool opening, bool useDockAnchor = true);
    void setState(State state);
    void animateFrame(const QRectF &from, const QRectF &to, qreal fromOpacity,
                      qreal toOpacity, int duration, QEasingCurve::Type easing);
    Qt::Edges resizeEdgesAt(const QPointF &position) const;
    QRect availableGeometry() const;

    WindowControl *m_controls[3] = {};
    qreal m_scale = 1.0;
    QPoint m_dragOffset;
    // Preserve the user's last windowed geometry across maximize/restore cycles.
    QRect m_normalGeometry;
    bool m_dragging = false;
    bool m_maximized = false;
    State m_state = State::Closed;
    QRect m_dockIconGeometry;
    WindowTransition *m_transition = nullptr;
    QVariantAnimation m_windowAnimation;
    bool m_opening = false;
    bool m_geometryAnimating = false;
    QRect m_geometryTarget;
    QRect m_availableGeometry;
    Qt::Edges m_resizeEdges;
    QRect m_resizeStartGeometry;
    QPoint m_resizeStartGlobal;
};

#endif // WINDOWEDGE_H
