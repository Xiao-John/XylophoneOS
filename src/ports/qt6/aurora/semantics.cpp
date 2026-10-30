// SPDX-License-Identifier: Apache-2.0
#include "semantics.hpp"
#include <QtCore/QCoreApplication>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QEvent>
#include <QtCore/QCoreApplication>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QAbstractButton>
namespace aurora {
namespace {quint32 instances=0;QByteArray encode(const QJsonObject &o){return QJsonDocument(o).toJson(QJsonDocument::Compact);}}
Semantics::Semantics():epoch((quint64(QCoreApplication::applicationPid())<<32)|++instances){clock.start();}
bool Semantics::expose(QWidget *w,const QString &role,bool external) {
    if(!w || entries.size()>=32 || (role!="textbox" && role!="button"))return false;
    if((role=="textbox" && !qobject_cast<QLineEdit*>(w)) || (role=="button" && !qobject_cast<QAbstractButton*>(w)))return false;
    entries.append({w,role,external,0,{}});return true;
}
QJsonObject Semantics::describe(int i) {
    auto &e=entries[i];QJsonObject state{{"alive",!e.widget.isNull()}};
    if(e.widget){state["enabled"]=e.widget->isEnabled();state["visible"]=e.widget->isVisible();state["focused"]=e.widget->hasFocus();state["name"]=e.widget->accessibleName();
        // Content affects stale-state detection internally, but is never exported.
        if(auto *line=qobject_cast<QLineEdit*>(e.widget.data())){state["privateValue"]=line->text();state["readOnly"]=line->isReadOnly();state["sensitive"]=line->echoMode()!=QLineEdit::Normal;}}
    auto stable=state;stable.remove("focused");
    const auto bytes=encode(stable);if(bytes!=e.state){e.state=bytes;++e.revision;}
    state.remove("privateValue");state["id"]=QString::number(i+1);state["revision"]=QString::number(e.revision);
    state["role"]=e.role;state["externalEffect"]=e.external;
    state["action"]=e.role=="textbox"?(state["readOnly"].toBool() || state["sensitive"].toBool()?"inspect":"set_text"):"activate";state["nameTrust"]="untrusted-content";
    return state;
}
QJsonObject Semantics::observe() {
    QJsonArray controls;for(int i=0;i<entries.size();++i)controls.append(describe(i));
    return {{"version",1},{"scope","application-local-demo"},{"epoch",QString::number(epoch)},
        {"authority","discovery-grants-no-rights"},{"controls",controls}};
}
bool Semantics::validate(const QJsonObject &p,QString &error) {
    const QStringList keys={"version","epoch","id","revision","action","value"};
    for(auto it=p.begin();it!=p.end();++it)if(!keys.contains(it.key())){error="UNKNOWN_FIELD";return false;}
    if(p["version"]!=1 || !p["epoch"].isString() || p["epoch"].toString()!=QString::number(epoch)){error="WRONG_SCOPE";return false;}
    bool ok=false;const auto id=p["id"].toString().toUInt(&ok);
    if(!ok || id<1 || id>quint32(entries.size())){error="UNKNOWN_TARGET";return false;}
    const auto state=describe(int(id-1));auto &e=entries[int(id-1)];
    if(!e.widget){error="DEAD_TARGET";return false;}
    if(!p["revision"].isString() || p["revision"]!=state["revision"]){error="STALE_STATE";return false;}
    if(!e.widget->isEnabled() || !e.widget->isVisible()){error="UNAVAILABLE";return false;}
    if(e.role=="textbox"){
        auto *line=qobject_cast<QLineEdit*>(e.widget.data());
        if(line->isReadOnly() || line->echoMode()!=QLineEdit::Normal){error="ACTION_NOT_EXPOSED";return false;}
    }
    if(p["action"]!=state["action"]){error="ACTION_NOT_EXPOSED";return false;}
    if(e.role=="textbox" && (!p["value"].isString() || p["value"].toString().size()>1024)){error="BAD_VALUE";return false;}
    if(e.role=="button" && p.contains("value")){error="BAD_VALUE";return false;}
    error.clear();return true;
}
bool Semantics::propose(const QJsonObject &p,QString &error){return validate(p,error);}
Semantics::Grant Semantics::host_authorize(const QJsonObject &p,int ttl,QString &error) {
    Grant grant;if(ttl<0 || ttl>60000 || !validate(p,error))return grant;
    grant.binding=encode(p);grant.epoch=authorization_epoch;grant.expires=clock.elapsed()+ttl;grant.used=false;return grant;
}
void Semantics::revoke(){++authorization_epoch;}
QString Semantics::execute(const QJsonObject &p,Grant &g) {
    if(g.used || g.epoch!=authorization_epoch || clock.elapsed()>=g.expires || g.binding!=encode(p))return "DENIED";
    g.used=true;QString error;if(!validate(p,error))return error;
    const auto index=int(p["id"].toString().toUInt()-1);
    const QPointer<QWidget> target=entries.at(index).widget;
    const QString role=entries.at(index).role;
    if(role=="textbox"){
        auto *line=qobject_cast<QLineEdit*>(target.data());
        if(!line)return "UNKNOWN";
        const auto expected=p["value"].toString();line->setText(expected);
        // A synchronous handler can append entries (reallocating the vector),
        // destroy the widget, or queue deleteLater(). QPointer protects the
        // post-dispatch read; deferred deletion remains Qt's event-loop job.
        // The local value is verified only while the guarded target still lives.
        if(!target)return "UNKNOWN";
        auto *current=qobject_cast<QLineEdit*>(target.data());
        return current && current->text()==expected?"VERIFIED_LOCAL":"UNKNOWN";
    }
    auto *button=qobject_cast<QAbstractButton*>(target.data());if(!button)return "UNKNOWN";button->click();
    // Signal dispatch cannot prove an external transaction completed. Never replay.
    return "UNKNOWN";
}
}
