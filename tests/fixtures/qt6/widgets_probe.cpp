// SPDX-License-Identifier: Apache-2.0
#include <QtWidgets/QApplication>
#include <QtWidgets/QWidget>
#include <QtWidgets/QLabel>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QPlainTextEdit>
#include <QtWidgets/QVBoxLayout>
#include <QtCore/QTimer>
#include <QtGui/QScreen>
#include <QtGui/QShortcut>
#include <QtCore/QtPlugin>
#include <cstdio>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
int main(int argc, char **argv) {
    QApplication app(argc,argv);
    QWidget window;
    auto *layout=new QVBoxLayout(&window);
    layout->addWidget(new QLabel("XylophoneOS | Qt Widgets 6.8.3"));
    auto *button=new QPushButton("Insert line");layout->addWidget(button);
    auto *text=new QPlainTextEdit;layout->addWidget(text);
    text->setPlainText("Real QWidget / QPlainTextEdit viewport\nEdit this text.\n");
    QObject::connect(button,&QPushButton::clicked,text,[text]{text->insertPlainText("button\n");});
    QObject::connect(text,&QPlainTextEdit::textChanged,text,[text]{
        std::printf("QT_WIDGETS_TEXT hex=%s\n",text->toPlainText().toUtf8().toHex().constData());
    });
    auto *exit=new QShortcut(QKeySequence(Qt::Key_Escape),&window);QObject::connect(exit,&QShortcut::activated,&app,&QApplication::quit);
    window.setGeometry(app.primaryScreen()->geometry()); window.showFullScreen();text->setFocus();
    QTimer::singleShot(200,[]{std::printf("QT_WIDGETS_READY\n");});
    if(argc>1) QTimer::singleShot(1800,&app,&QApplication::quit);
    const auto rc=app.exec();std::printf("QT_WIDGETS_OK\n");return rc;
}
