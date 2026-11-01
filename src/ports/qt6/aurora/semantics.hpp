// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QtCore/QJsonObject>
#include <QtCore/QPointer>
#include <QtCore/QElapsedTimer>
#include <QtCore/QVector>
#include <QtWidgets/QWidget>
#include <utility>
namespace aurora {
// App-local adapter, not an authenticated cross-process transport or OS grant.
// Only the trusted host creates Grants. Model proposals contain no grant field.
class semantics {
    struct Entry {QPointer<QWidget> widget;QString role;bool external=false;quint64 revision=0;QByteArray state;};
    QVector<Entry> entries;
    quint64 epoch,authorization_epoch=1;
    QElapsedTimer clock;
    QJsonObject describe(int index);
    bool validate(const QJsonObject &proposal,QString &error);
public:
    class Grant {
        friend class semantics;
        QByteArray binding;
        quint64 epoch=0;
        qint64 expires=0;
        bool used=true;
    public:
        Grant()=default;
        Grant(const Grant &)=delete;
        Grant &operator=(const Grant &)=delete;
        Grant(Grant &&other) noexcept :binding(std::move(other.binding)),epoch(other.epoch),expires(other.expires),used(other.used){other.used=true;}
        Grant &operator=(Grant &&other) noexcept {
            if(this!=&other){binding=std::move(other.binding);epoch=other.epoch;expires=other.expires;used=other.used;other.used=true;}return *this;
        }
    };
    semantics();
    semantics(const semantics &)=delete;
    semantics &operator=(const semantics &)=delete;
    semantics(semantics &&)=delete;
    semantics &operator=(semantics &&)=delete;
    bool expose(QWidget *widget,const QString &role,bool external_effect=false);
    QJsonObject observe();
    bool propose(const QJsonObject &proposal,QString &error);
    Grant host_authorize(const QJsonObject &proposal,int ttl_ms,QString &error);
    void revoke();
    // VERIFIED_LOCAL means actual widget state checked; dispatch is never proof
    // of external success. UNKNOWN is terminal for this one-shot grant.
    QString execute(const QJsonObject &proposal,Grant &grant);
};
}
