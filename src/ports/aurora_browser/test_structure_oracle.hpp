// SPDX-License-Identifier: Apache-2.0
#pragma once
#ifndef XOS_SSG_TEST_ORACLE
#error "The structure oracle belongs only in the explicit test Browser build"
#endif
#include <litehtml.h>
#include <QtCore/QCryptographicHash>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonObject>
#include <functional>
#include <new>

namespace browser::test {
// A deliberately simple, bounded reference over the engine's actual document.
// This code knows nothing about SSG IDs, PageFrame, cursors, filters, budgets,
// rendering fragments, or the Provider's completion decision. It is not an IPC
// operation and is absent from the normal Browser build.
inline QJsonObject structure_oracle(const litehtml::element::ptr &root) {
    struct Limit {};
    constexpr int max_nodes = 4096, max_depth = 32, max_value_bytes = 262144;
    QJsonArray nodes;
    int value_bytes = 0;
    try {
        std::function<void(const litehtml::element::ptr &, const QString &,
                           const QString &, int, int)> visit;
        visit = [&](const litehtml::element::ptr &element, const QString &path,
                    const QString &parent, int child_index, int depth) {
            if (!element || nodes.size() >= max_nodes || depth > max_depth ||
                element->children().size() > unsigned(max_nodes)) throw Limit{};
            const char *tag = element->get_tagName();
            const QString name = QString::fromUtf8(tag ? tag : "");
            QJsonObject record{{"path", path}, {"parentPath", parent},
                {"ordinal", int(nodes.size())}, {"childIndex", child_index},
                {"childCount", int(element->children().size())}, {"tag", name},
                {"role", element->is_text() ? "text" : name == "a" ? "link" : "element"}};
            if (element->is_text()) {
                litehtml::string text;
                element->get_text(text);
                const QString value = QString::fromUtf8(text.c_str());
                value_bytes += value.toUtf8().size();
                record["text"] = value; // No trim, truncation, or whitespace merge.
            }
            if (name == "a") {
                const QString value = QString::fromUtf8(element->get_attr("href", ""));
                value_bytes += value.toUtf8().size();
                record["href"] = value;
            }
            if (value_bytes > max_value_bytes) throw Limit{};
            nodes.append(record);
            int index = 0;
            // A native recursive preorder, independent of the production DFS
            // continuation. Head, hidden and off-viewport subtrees stay present.
            for (const auto &child : element->children()) {
                visit(child, path + "/" + QString::number(index), path, index, depth + 1);
                ++index;
            }
        };
        visit(root, QStringLiteral("0"), QString(), 0, 0);

        // Canonical bytes are defined independently of Qt's JSON serialization.
        // Eleven UTF-8 netstrings per node, in the following fixed field order.
        QCryptographicHash hash(QCryptographicHash::Sha256);
        hash.addData(QByteArray("XOS-LITEHTML-STRUCTURE-V1\n"));
        auto field = [&](const QString &value) {
            const QByteArray bytes = value.toUtf8();
            hash.addData(QByteArray::number(bytes.size()) + ":" + bytes + ",");
        };
        for (const auto value : nodes) {
            const auto record = value.toObject();
            field(record["path"].toString());
            field(record["parentPath"].toString());
            field(QString::number(record["ordinal"].toInt()));
            field(QString::number(record["childIndex"].toInt()));
            field(QString::number(record["childCount"].toInt()));
            field(record["tag"].toString());
            field(record["role"].toString());
            field(record.contains("text") ? QStringLiteral("1") : QStringLiteral("0"));
            field(record["text"].toString());
            field(record.contains("href") ? QStringLiteral("1") : QStringLiteral("0"));
            field(record["href"].toString());
            hash.addData(QByteArray("\n"));
        }
        return {{"schema", "xos-litehtml-structure-oracle-v1"}, {"status", "OK"},
            {"canonicalFormat", "netstring-utf8-v1"},
            {"structureSha256", QString::fromLatin1(hash.result().toHex())},
            {"nodeCount", int(nodes.size())}, {"nodes", nodes},
            {"limits", QJsonObject{{"nodes", max_nodes}, {"depth", max_depth},
                                   {"valueUtf8Bytes", max_value_bytes}}}};
    } catch (const Limit &) {
        return {{"schema", "xos-litehtml-structure-oracle-v1"},
                {"status", "ORACLE_RESOURCE_LIMIT"}};
    } catch (const std::bad_alloc &) {
        return {{"schema", "xos-litehtml-structure-oracle-v1"},
                {"status", "ORACLE_ALLOCATION_FAILED"}};
    }
}
} // namespace browser::test
