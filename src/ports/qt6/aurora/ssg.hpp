// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QtCore/QJsonObject>
#include <QtCore/QJsonArray>
#include <QtCore/QPointer>
#include <QtCore/QVector>
#include <QtCore/QSharedPointer>
#include <QtGui/QTextDocument>
#include <QtWidgets/QWidget>
namespace aurora {
// Bounded app-owned stream. No discovery endpoint, cross-process reads or grants.
class SceneStream {
    QJsonObject current,previous;
    quint64 version=0,epoch;
public:
    SceneStream();
    void invalidate();
    QString source_epoch() const;
    // Optional metadata.queryScope identifies every query/authorization filter;
    // without it any metadata change requires a fresh snapshot. Node IDs must
    // be nonempty unique strings. A capped result cannot be diffed as complete.
    QJsonObject publish(const QJsonArray &nodes,const QJsonObject &metadata,bool capped=false);
    QJsonObject diff(quint64 since,const QString &expected_epoch) const;
};
class QtScene {
    struct Identity {QPointer<QWidget> widget;quint64 id; QPointer<QTextDocument> document; QSharedPointer<quint64> revision; QMetaObject::Connection connection;};
    QPointer<QWidget> root;
    QVector<Identity> identities;
    quint64 next_id=1;
    bool permitted=false,text_permitted=false;
    unsigned node_limit=96;
    SceneStream stream;
public:
    explicit QtScene(QWidget *application_root):root(application_root){}
    ~QtScene();
    void clear_identities();
    // Trusted application host only; this is not an OS authorization API.
    void host_allow_observation(bool read_text);
    void revoke();
    void set_node_limit(unsigned value){node_limit=qMin(value,96u);}
    QJsonObject snapshot(bool visible_only=false,const QString &role={});
    QJsonObject text_range(const QString &epoch,const QString &id,int start,int maximum,const QString &revision);
    QJsonObject diff(quint64 since,const QString &epoch) const {return stream.diff(since,epoch);}
};
}
