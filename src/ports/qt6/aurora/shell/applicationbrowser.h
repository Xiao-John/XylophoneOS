#ifndef APPLICATIONBROWSER_H
#define APPLICATIONBROWSER_H

#include <QHash>
#include <QPixmap>
#include <QVariantAnimation>
#include <QWidget>

class QLineEdit;
class QScrollArea;
class QToolButton;
class QLabel;

class ApplicationBrowser : public QWidget
{
    Q_OBJECT

public:
    /** Create a browser overlay bound to the desktop and its JSON configuration. */
    explicit ApplicationBrowser(QWidget *background, const QString &configPath);
    /** Load app entries, capture the desktop, and animate the browser open. */
    void open();
    /** Dismiss through the normal close transition. */
    void dismiss();

signals:
    void applicationLaunched(const QString &appName);
    void dismissed();

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
    void paintEvent(QPaintEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void keyPressEvent(QKeyEvent *event) override;

private:
    /** Opening and closing remain explicit so a transition can be reversed safely. */
    enum class State { Closed, Opening, Open, Closing };
    void loadApplications();
    void rebuildGroups();
    void updateLayout();
    void applyProgress(qreal progress);
    void closeAnimated(const QString &appName = QString());
    void captureBackground();
    QString iconPathFor(const QString &appName) const;

    QString m_configPath;
    QStringList m_applications;
    QHash<QString, QString> m_icons;
    QLineEdit *m_search = nullptr;
    QScrollArea *m_scrollArea = nullptr;
    QWidget *m_content = nullptr;
    QList<QToolButton *> m_tiles;
    QList<QLabel *> m_headings;
    // Both images are cached for one open session to avoid per-frame blur work.
    QPixmap m_snapshot;
    QPixmap m_blurredSnapshot;
    QRect m_searchTarget;
    QVariantAnimation m_transition;
    State m_state = State::Closed;
    qreal m_progress = 0.0;
    qreal m_scale = 1.0;
    QString m_pendingApp;
};

#endif // APPLICATIONBROWSER_H
