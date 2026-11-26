// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QEvent>
#include <QJSEngine>
#include <QPointer>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QUrl>
#include <QVariant>

#include <cstdio>
#include <memory>

namespace {

int fail(int code, const char *message)
{
    std::fprintf(stderr, "%s\n", message);
    return code;
}

int run_qml()
{
    QQmlEngine engine;
    engine.setImportPathList({QStringLiteral("qrc:/qt/qml"),
                              QStringLiteral("qrc:/qt-project.org/imports")});
    const QJSValue script = engine.evaluate(QStringLiteral(
        "[1, 2, 3, 4].map(n => n * n).reduce((a, b) => a + b, 0)"));
    if (script.isError() || !script.isNumber() || script.toInt() != 30) {
        std::fprintf(stderr, "JavaScript result: %s\n", qPrintable(script.toString()));
        return fail(1, "QML_PROBE_FAIL: JavaScript evaluation");
    }

    QQmlComponent component(&engine, QUrl(QStringLiteral("qrc:/e18/entry.qml")));
    std::unique_ptr<QObject> root(component.create());
    if (!root) {
        std::fprintf(stderr, "%s\n", qPrintable(component.errorString()));
        return fail(2, "QML_PROBE_FAIL: resource or static module");
    }
    if (root->property("result").toInt() != 42 || !root->setProperty("seed", 8)
        || root->property("result").toInt() != 72)
        return fail(3, "QML_PROBE_FAIL: property binding");

    QQmlComponent missing(&engine);
    missing.setData("import Xos.Missing 1.0\nMissing {}",
                    QUrl(QStringLiteral("qrc:/e18/missing.qml")));
    if (!missing.isError() || missing.errors().isEmpty()
        || !missing.errors().first().description().contains(QStringLiteral("Xos.Missing")))
        return fail(4, "QML_PROBE_FAIL: missing module diagnostic");

    QPointer<QObject> observed_root(root.get());
    root.reset();
    if (!observed_root.isNull())
        return fail(5, "QML_PROBE_FAIL: root lifetime");

    QPointer<QObject> observed_wrapper(new QObject);
    QJSEngine::setObjectOwnership(observed_wrapper, QJSEngine::JavaScriptOwnership);
    {
        const QJSValue wrapper = engine.newQObject(observed_wrapper);
        engine.collectGarbage();
        if (observed_wrapper.isNull() || wrapper.toQObject() != observed_wrapper)
            return fail(6, "QML_PROBE_FAIL: reachable JavaScript wrapper");
    }
    engine.collectGarbage();
    if (observed_wrapper)
        QCoreApplication::sendPostedEvents(observed_wrapper, QEvent::DeferredDelete);
    if (observed_wrapper)
        return fail(7, "QML_PROBE_FAIL: unreachable JavaScript wrapper");
    return 0;
}

}  // namespace

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    for (int cycle = 0; cycle < 3; ++cycle) {
        if (const int code = run_qml())
            return code;
    }
    std::puts("QML_PROBE_OK");
    return 0;
}
