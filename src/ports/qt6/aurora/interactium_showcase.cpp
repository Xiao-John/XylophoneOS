// SPDX-License-Identifier: Apache-2.0
#include "desktop.hpp"
#include "style.hpp"
#include <QtWidgets/QApplication>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QLabel>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QPlainTextEdit>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QVBoxLayout>
#include <QtGui/QShortcut>
#include <QtCore/QtPlugin>

Q_IMPORT_PLUGIN(QXosIntegrationPlugin)

int main(int argc, char** argv) {
    QApplication app(argc, argv);
    aurora::initialize(app);

    aurora::desktop_surface counter_window;
    counter_window.setWindowTitle(QStringLiteral("Aurora Counter"));
    counter_window.setGeometry(48, 72, 320, 260);
    auto* counter_layout = new QVBoxLayout(&counter_window);
    counter_layout->setContentsMargins(24, 20, 24, 20);
    counter_layout->setSpacing(14);
    auto* counter_heading = new QLabel(QStringLiteral("Counter"));
    QFont heading_font = counter_heading->font();
    heading_font.setPixelSize(24);
    heading_font.setBold(true);
    counter_heading->setFont(heading_font);
    counter_layout->addWidget(counter_heading);
    auto* count_label = new QLabel(QStringLiteral("0"));
    count_label->setAlignment(Qt::AlignCenter);
    QFont count_font = count_label->font();
    count_font.setPixelSize(42);
    count_label->setFont(count_font);
    counter_layout->addWidget(count_label, 1);
    auto* increment = new QPushButton(QStringLiteral("Increment"));
    counter_layout->addWidget(increment);
    QObject::connect(increment, &QPushButton::clicked, &counter_window,
                     [count_label, count = 0]() mutable {
        count_label->setText(QString::number(++count));
    });
    auto* close_counter = new QPushButton(QStringLiteral("Close counter"));
    counter_layout->addWidget(close_counter);
    QObject::connect(close_counter, &QPushButton::clicked, &counter_window,
                     &QWidget::close);

    aurora::desktop_surface notes_window;
    notes_window.setWindowTitle(QStringLiteral("Aurora Notes"));
    notes_window.setGeometry(408, 174, 360, 320);
    auto* notes_layout = new QVBoxLayout(&notes_window);
    notes_layout->setContentsMargins(24, 20, 24, 20);
    notes_layout->setSpacing(12);
    notes_layout->addWidget(new QLabel(QStringLiteral("Quick note")));
    auto* entry = new QLineEdit;
    entry->setPlaceholderText(QStringLiteral("Type a note"));
    notes_layout->addWidget(entry);
    auto* note = new QPlainTextEdit;
    note->setPlainText(QStringLiteral("Your notes appear here."));
    notes_layout->addWidget(note, 1);
    auto* actions = new QHBoxLayout;
    auto* add_note = new QPushButton(QStringLiteral("Add note"));
    auto* close_notes = new QPushButton(QStringLiteral("Close notes"));
    actions->addWidget(add_note);
    actions->addWidget(close_notes);
    notes_layout->addLayout(actions);
    QObject::connect(add_note, &QPushButton::clicked, &notes_window,
                     [entry, note] {
        const QString text = entry->text().trimmed();
        if (text.isEmpty()) return;
        note->appendPlainText(text);
        entry->clear();
        entry->setFocus();
    });
    QObject::connect(entry, &QLineEdit::returnPressed, add_note,
                     &QPushButton::click);
    QObject::connect(close_notes, &QPushButton::clicked, &notes_window,
                     &QWidget::close);

    auto* quit = new QShortcut(QKeySequence(Qt::Key_Escape), &counter_window);
    QObject::connect(quit, &QShortcut::activated, &app, &QApplication::quit);
    counter_window.show();
    notes_window.show();
    return app.exec();
}
