// SPDX-License-Identifier: Apache-2.0
#include "../../../src/ports/qt6/aurora/desktop.hpp"
#include "../../../src/ports/qt6/aurora/style.hpp"
#include <QtWidgets/QVBoxLayout>
#include <QtWidgets/QLabel>
#include <QtWidgets/QLineEdit>
#include <QtGui/QScreen>
#include <QtGui/QShortcut>
#include <QtCore/QtPlugin>
#include <xos/thread_core.hpp>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
class MeasuredSurface final : public aurora::DesktopSurface {
    bool event(QEvent *event) override {
        if(event->type()!=QEvent::UpdateRequest)return DesktopSurface::event(event);
        // Pinned Qt 6.8.3 QWidget::event -> syncBackingStore -> paintAndFlush.
        // Log only the existing public event; no Qt/QPA/kernel modification.
        const auto begin=xos::thread::clock();std::printf("RENDER_UPDATE_BEGIN\n");
        const auto result=DesktopSurface::event(event);
        std::printf("RENDER_UPDATE_END ns=%llu\n",(unsigned long long)(xos::thread::clock()-begin));
        return result;
    }
};
int main(int argc,char **argv) {
    QApplication app(argc,argv);aurora::initialize(app);const QByteArray mode=argc>1?argv[1]:"balanced";
    auto p=aurora::preferences();if(mode=="high")p.quality=aurora::Quality::high;
    if(mode=="low")p.quality=aurora::Quality::low;if(mode=="safe")p.quality=aurora::Quality::safe;
    if(mode=="off")p.glass_enabled=false;if(mode=="opaque")p.reduce_transparency=true;
    aurora::set_preferences(p);MeasuredSurface window;
    auto *root=new QVBoxLayout(&window);root->setContentsMargins(64,64,64,64);
    auto *panel=new aurora::GlassPanel(&window);root->addWidget(panel);auto *l=new QVBoxLayout(panel);l->setContentsMargins(28,28,28,28);l->setSpacing(18);
    l->addWidget(new QLabel("Aurora  /  Matched material scene"));
    l->addWidget(new QLabel("Identical wallpaper, layout and input sequence in each run."));
    auto *field=new QLineEdit;field->setMinimumHeight(40);l->addWidget(field);
    auto *button=new QPushButton("A native control");button->setMinimumHeight(40);l->addWidget(button);l->addStretch();
    int edits=0;QObject::connect(field,&QLineEdit::textChanged,[&]{const auto info=window.render_info();std::printf("RENDER_EDIT count=%d generations=%u\n",++edits,info.generations);});
    auto *quit=new QShortcut(QKeySequence(Qt::Key_Escape),&window);QObject::connect(quit,&QShortcut::activated,&app,&QApplication::quit);
    window.setGeometry(app.primaryScreen()->geometry());window.showFullScreen();field->setFocus();
    if(mode=="budget")window.set_cache_budget(0);
    QTimer::singleShot(350,[&]{const auto info=window.render_info();xos::thread_stats s{};xos::sdk::syscall(xos::sys_thread_stats,reinterpret_cast<xos::u64>(&s));
        std::printf("RENDER_READY mode=%s requested=%d effective=%d fallback=%d bytes=%lld cache_ns=%lld generations=%u pages=%u threads=%u\n",mode.constData(),int(p.quality),int(info.effective),info.fallback,(long long)info.cache_bytes,(long long)info.cache_ns,info.generations,s.process_user_pages,s.threads);
        std::printf("RENDER_CSS %s\n",aurora::theme_css_variables().constData());
    });return app.exec();
}
