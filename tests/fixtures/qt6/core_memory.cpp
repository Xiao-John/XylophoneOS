// SPDX-License-Identifier: Apache-2.0
#include <QByteArray>
#include <QCoreApplication>
#include <QThread>
#include <xos/thread_core.hpp>
#include <atomic>
#include <cstdio>

class Sampler : public QThread {
public:
    std::atomic<bool> stop{false};
    xos::u32 maxPages = 0;
    unsigned samples = 0;
    void run() override {
        do {
            xos::thread_stats stats{};
            if (xos::sdk::syscall(xos::sys_thread_stats, reinterpret_cast<xos::u64>(&stats)) == 0) {
                if (stats.process_user_pages > maxPages) maxPages = stats.process_user_pages;
                ++samples;
            }
            QThread::msleep(10);
        } while (!stop.load());
    }
};
int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    Sampler sampler;
    sampler.start();
    {
        QByteArray bytes(4 * 1024 * 1024, 'x');
        if (bytes.size() != 4 * 1024 * 1024 || bytes.at(0) != 'x' || bytes.at(bytes.size()-1) != 'x') return 50;
        QThread::msleep(100);
    }
    sampler.stop.store(true);
    if (!sampler.wait(3000) || sampler.samples < 2 || !sampler.maxPages) return 51;
    std::printf("QT_MEMORY_SAMPLE_OK sampled_peak_user_pages=%u samples=%u page_bytes=4096\n", sampler.maxPages, sampler.samples);
    return 0;
}
