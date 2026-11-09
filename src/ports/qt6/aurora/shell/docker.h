#ifndef DOCKER_H
#define DOCKER_H

#include <QHash>
#include <QList>
#include <QRect>
#include <QVariantAnimation>
#include <QWidget>
#include <QTimer>

class QToolButton;
class QLabel;

class Docker : public QWidget
{
    Q_OBJECT
public:
    /** Dock marker states are synchronized with each managed application's lifecycle. */
    enum class ApplicationState { Closed, Running, Minimized };
    Q_ENUM(ApplicationState)
    /** Construct a Dock whose geometry is derived from its desktop parent. */
    explicit Docker(QWidget *parent = nullptr);
    /** Insert an application before Trash and animate the resulting layout change. */
    void addAppToDock(const QString &appName);
    /** Animate the marker corresponding to an application's lifecycle state. */
    void setApplicationState(const QString &appName, ApplicationState state);
    /** Return the tracked state, defaulting to Closed for an unknown app. */
    ApplicationState applicationState(const QString &appName) const;
    /** Return the icon slot in global coordinates for window transitions. */
    QRect applicationIconGeometry(const QString &appName) const;
    /** Keep the Dock visible while the app browser is active. */
    void setMenuOpen(bool open);
    /** Enable bottom-edge reveal and delayed slide-out behavior. */
    void setAutoHideEnabled(bool enabled);
    bool autoHideEnabled() const { return m_autoHideEnabled; }

signals:
    void expansionRequested();
    void applicationActivated(const QString &appName);

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
    void paintEvent(QPaintEvent *event) override;

private:
    void loadConfiguration();
    void updateGeometryFromBackground(bool animate = false, QToolButton *newButton = nullptr);
    QToolButton *createButton(const QString &name, const QString &iconPath);
    void updateNameLabelAppearance();
    void showNameLabel(QToolButton *button);
    void hideNameLabel();
    void updateDockPosition();
    void setDockRevealed(bool revealed);
    void checkPointerPosition();
    void updatePointerPosition(const QPoint &globalPosition);

    // Buttons remain in logical order while their slot rectangles are interpolated.
    QList<QToolButton *> m_appButtons;
    QLabel *m_nameLabel = nullptr;
    QToolButton *m_hoveredButton = nullptr;
    QHash<QString, QString> m_iconPaths;
    QHash<QString, ApplicationState> m_applicationStates;
    QString m_configPath;
    qreal m_cornerRadius = 0.0;
    qreal m_bottomMargin = 0.0;
    bool m_menuOpen = false;
    QVariantAnimation m_layoutAnimation;
    QRect m_layoutGeometry;
    QVariantAnimation m_visibilityAnimation;
    QTimer m_pointerTimer;
    QTimer m_hideDelay;
    // 0 is fully revealed; 1 places the Dock below the desktop canvas.
    qreal m_hideProgress = 0.0;
    bool m_autoHideEnabled = false;
    bool m_dockRevealed = true;
};

#endif // DOCKER_H
