// SPDX-License-Identifier: Apache-2.0
#ifndef BACKGROUND_H
#define BACKGROUND_H

#include <QPixmap>
#include <QWidget>

class ApplicationBrowser;
class Docker;
class WindowEdge;
class Status;

class Background : public QWidget
{
    Q_OBJECT

public:
    /** Create the configured desktop canvas and its shell components. */
    explicit Background(QWidget *parent = nullptr);

protected:
    void paintEvent(QPaintEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;

private:
    /** Route a Dock or app-browser selection to the prototype application. */
    void activateApplication(const QString &appName, bool toggleRunning = false);
    /** Recompute status-strip and maximized-window available geometry. */
    void updateShellLayout();
    /** Raise shell surfaces in their intended interaction order. */
    void raiseShellLayers();
    /** Keep Dock auto-hide enabled only for a running maximized app. */
    void updateDockAutoHide();

    // The desktop owns these widgets; the application browser is created on first use.
    QWidget *m_desktop = nullptr;
    QPixmap m_image;
    QString m_configPath;
    Docker *m_docker = nullptr;
    WindowEdge *m_exampleWindow = nullptr;
    Status *m_status = nullptr;
    ApplicationBrowser *m_applicationBrowser = nullptr;
};

#endif // BACKGROUND_H
