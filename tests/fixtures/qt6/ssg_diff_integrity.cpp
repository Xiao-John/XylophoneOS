// SPDX-License-Identifier: Apache-2.0
// Exercise the actual application-local stream on the XOS guest.
#include "../../../src/ports/qt6/aurora/ssg.hpp"
#include <QtCore/QCoreApplication>
#include <QtCore/QJsonArray>
#include <cstdio>

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    int failures = 0;
    auto check = [&](bool ok, const char *name) {
        std::printf("SSG_DIFF_CHECK %s=%s\n", name, ok ? "PASS" : "FAIL");
        if (!ok) ++failures;
    };
    auto node = [](const char *id, const char *text) {
        return QJsonObject{{"id", id}, {"text", text}};
    };
    auto meta = [](const char *query, int scroll) {
        return QJsonObject{{"queryScope", QJsonObject{{"query", query}}}, {"scrollY", scroll}};
    };
    aurora::SceneStream stream;
    check(stream.diff(0, "missing")["status"] == "UNAVAILABLE", "unpublished_unavailable");
    const auto a = stream.publish(QJsonArray{node("1", "one"), node("2", "two")}, meta("all", 0));
    const auto epoch = a["sourceEpoch"].toString();
    auto version = a["sceneVersion"].toString().toULongLong();
    auto same = stream.diff(version, epoch);
    check(same["status"] == "OK" && same["changed"].toArray().isEmpty() && same["removed"].toArray().isEmpty(), "complete_unchanged");
    const auto b = stream.publish(QJsonArray{node("1", "changed")}, meta("all", 1));
    const auto delta = stream.diff(version, epoch);
    check(delta["status"] == "OK" && delta["changed"].toArray().size() == 1 && delta["removed"].toArray().contains("2"), "complete_change_and_real_removal");
    check(delta["metadata"].toObject()["scrollY"] == 1 && !delta["capped"].toBool(true), "metadata_delivered_with_diff");
    version = b["sceneVersion"].toString().toULongLong();
    const auto filtered = stream.publish(QJsonArray{node("1", "changed")}, meta("filtered", 1));
    check(stream.diff(version, epoch)["status"] == "RESET_REQUIRED", "query_scope_change_resets");
    version = filtered["sceneVersion"].toString().toULongLong();
    const auto partial = stream.publish(QJsonArray{node("1", "changed")}, meta("filtered", 1), true);
    check(stream.diff(version, epoch)["status"] == "RESET_REQUIRED", "partial_current_resets");
    version = partial["sceneVersion"].toString().toULongLong();
    check(stream.diff(version, epoch)["status"] == "RESET_REQUIRED", "partial_unchanged_is_not_complete");
    const auto complete = stream.publish(QJsonArray{node("1", "changed")}, meta("filtered", 1));
    check(stream.diff(version, epoch)["status"] == "RESET_REQUIRED", "partial_previous_resets");
    version = complete["sceneVersion"].toString().toULongLong();
    const auto duplicate = stream.publish(QJsonArray{node("1", "first"), node("1", "second")}, meta("filtered", 1));
    check(duplicate["status"] == "BAD_NODES" && stream.diff(version, epoch)["status"] == "OK", "duplicate_id_rejected_without_changing_history");
    check(stream.publish(QJsonArray{QJsonObject{{"text", "missing id"}}}, meta("filtered", 1))["status"] == "BAD_NODES", "missing_id_rejected");
    aurora::SceneStream legacy;
    auto old = legacy.publish(QJsonArray{node("1", "one")}, QJsonObject{{"query", "all"}, {"scrollY", 0}});
    legacy.publish(QJsonArray{node("1", "one")}, QJsonObject{{"query", "all"}, {"scrollY", 1}});
    check(legacy.diff(old["sceneVersion"].toString().toULongLong(), old["sourceEpoch"].toString())["status"] == "RESET_REQUIRED", "legacy_metadata_change_conservatively_resets");
    stream.invalidate();stream.publish(QJsonArray{node("1", "new epoch")}, meta("filtered", 0));
    check(stream.diff(version, epoch)["status"] == "SOURCE_REPLACED", "old_epoch_rejected");
    std::printf("SSG_DIFF_TEST_DONE failures=%d\n", failures);
    return failures ? 1 : 0;
}
