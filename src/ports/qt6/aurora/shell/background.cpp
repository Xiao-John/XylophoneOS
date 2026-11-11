// SPDX-License-Identifier: Apache-2.0
#include "system_context.h"
#include "background.h"
#include "applicationbrowser.h"
#include "docker.h"
#include "windowedge.h"
#include "status.h"

#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QPainter>
#include <QDebug>
#include <QResizeEvent>

Background::Background(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("Background"));
    setWindowFlag(Qt::Window, true);
    setWindowTitle(QStringLiteral("Background"));

    m_configPath = QStringLiteral(":/aurora/catalog");
    setWindowFlags(Qt::Window | Qt::FramelessWindowHint);
    setWindowTitle(QStringLiteral("Aurora"));
    m_desktop = new QWidget(this);
    m_desktop->setObjectName(QStringLiteral("Desktop"));
    m_desktop->setAttribute(Qt::WA_TransparentForMouseEvents);
    m_desktop->setAutoFillBackground(false);

    // Docker owns its layout and follows this widget's resize events.
    m_docker = new Docker(this);
    m_status = new Status(this);
    m_exampleWindow = new WindowEdge(this);
    m_exampleWindow->move((width() - m_exampleWindow->width()) / 2,
                          (height() - m_exampleWindow->height()) / 2);
    m_exampleWindow->hide();
    // Translate the sample window state into the Dock's independent marker state.
    connect(m_exampleWindow, &WindowEdge::stateChanged, this, [this](WindowEdge::State state) {
        Docker::ApplicationState dockState = Docker::ApplicationState::Closed;
        if (state == WindowEdge::State::Running) dockState = Docker::ApplicationState::Running;
        else if (state == WindowEdge::State::Minimized) dockState = Docker::ApplicationState::Minimized;
        m_docker->setApplicationState(QStringLiteral("examplewindow"), dockState);
        updateDockAutoHide();
    });
    connect(m_exampleWindow, &WindowEdge::maximizedChanged, this, [this] { updateDockAutoHide(); });
    connect(m_exampleWindow, &WindowEdge::stackingRequested, this, &Background::raiseShellLayers);
    connect(m_docker, &Docker::applicationActivated, this, [this](const QString &appName) {
        activateApplication(appName, true);
    });
    connect(m_docker, &Docker::expansionRequested, this, [this] {
        if (!m_applicationBrowser) {
            m_applicationBrowser = new ApplicationBrowser(this, m_configPath);
            connect(m_applicationBrowser, &ApplicationBrowser::applicationLaunched,
                    this, [this](const QString &appName) {
                        m_docker->addAppToDock(appName);
                        activateApplication(appName);
                    });
            connect(m_applicationBrowser, &ApplicationBrowser::dismissed,
                    this, [this] { m_docker->setMenuOpen(false); });
        }
        m_docker->setMenuOpen(true);
        m_applicationBrowser->open();
        raiseShellLayers();
    });

    const QJsonObject config = auroraSystemConfiguration();

    const QJsonObject background = config.value(QStringLiteral("background")).toObject();
    const int width = background.value(QStringLiteral("width")).toInt();
    const int height = background.value(QStringLiteral("height")).toInt();
    if (width > 0 && height > 0)
        setFixedSize(width, height);

    const QString imagePath = background.value(QStringLiteral("image")).toString();
    if (!imagePath.isEmpty()) {
        const QString resolvedImagePath = imagePath;
        if (!m_image.load(resolvedImagePath))
            qWarning() << "Unable to load background image:" << resolvedImagePath;
    }
    m_status->setBackgroundImage(m_image);

    m_exampleWindow->move((this->width() - m_exampleWindow->width()) / 2,
                          (this->height() - m_exampleWindow->height()) / 2);
    updateShellLayout();
    raiseShellLayers();
}

void Background::activateApplication(const QString &appName, bool toggleRunning)
{
    if (appName.compare(QStringLiteral("examplewindow"), Qt::CaseInsensitive) == 0) {
        if (toggleRunning && m_exampleWindow->state() == WindowEdge::State::Running)
            m_exampleWindow->minimizeAnimated();
        else
            m_exampleWindow->openAnimated(m_docker->applicationIconGeometry(appName));
        raiseShellLayers();
    }
}

void Background::updateDockAutoHide()
{
    m_docker->setAutoHideEnabled(m_exampleWindow->isMaximized()
                                && m_exampleWindow->state() == WindowEdge::State::Running);
}

void Background::raiseShellLayers()
{
    // Raise in order so the clock remains visible above the Dock and sample window.
    if (m_applicationBrowser && m_applicationBrowser->isVisible()) m_applicationBrowser->raise();
    if (m_docker) m_docker->raise();
    if (m_status) m_status->raise();
}

void Background::updateShellLayout()
{
    if (m_desktop) m_desktop->setGeometry(rect());
    if (!m_status || !m_exampleWindow) return;
    m_status->refreshGeometry();
    m_exampleWindow->setAvailableGeometry(QRect(0, m_status->height(), width(), height() - m_status->height()));
}

void Background::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    if (m_exampleWindow && m_exampleWindow->state() == WindowEdge::State::Closed)
        m_exampleWindow->move((width() - m_exampleWindow->width()) / 2,
                              (height() - m_exampleWindow->height()) / 2);
    updateShellLayout();
}

void Background::paintEvent(QPaintEvent *event)
{
    Q_UNUSED(event);

    QPainter painter(this);
    if (!m_image.isNull())
        painter.drawPixmap(rect(), m_image);
}
