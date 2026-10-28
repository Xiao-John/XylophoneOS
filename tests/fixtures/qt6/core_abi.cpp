// SPDX-License-Identifier: Apache-2.0
#include <QByteArray>
#include <QCoreApplication>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <new>
#include <stdexcept>
#include <thread>
#include <typeinfo>

static int initialized;
struct StaticInit { StaticInit() { initialized = 73; } };
static StaticInit staticInit;
static std::atomic<int> tlsDestroyed{0};
struct TlsValue { ~TlsValue() { ++tlsDestroyed; } };
thread_local TlsValue tlsValue;
struct Base { virtual ~Base() = default; };
struct Derived : Base { int value = 17; };
struct alignas(64) Aligned { char data[64]; };
int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    if (initialized != 73) return 40;
    QByteArray bytes("abi");
    if (bytes.size() != 3) return 41;
    Base *object = new Derived;
    Derived *derived = dynamic_cast<Derived *>(object);
    if (!derived || derived->value != 17 || typeid(*object) != typeid(Derived)) return 42;
    delete object;
    auto *aligned = new Aligned;
    if (reinterpret_cast<std::uintptr_t>(aligned) % alignof(Aligned)) return 43;
    delete aligned;
    try { throw std::runtime_error("xos"); }
    catch (const std::runtime_error &e) { if (QByteArray(e.what()) != "xos") return 44; }
    std::thread worker([] { (void)tlsValue; });
    worker.join();
    if (tlsDestroyed.load() != 1) return 45;
    std::puts("QT_ABI_OK cxx17 static-init rtti aligned-new exception tls-dtor qtcore");
    return 0;
}
