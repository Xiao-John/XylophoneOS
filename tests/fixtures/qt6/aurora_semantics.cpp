// SPDX-License-Identifier: Apache-2.0
#include "../../../src/ports/qt6/aurora/desktop.hpp"
#include "../../../src/ports/qt6/aurora/style.hpp"
#include "../../../src/ports/qt6/aurora/semantics.hpp"
#include "../../../src/ports/qt6/aurora/ssg.hpp"
#include <QtWidgets/QVBoxLayout>
#include <QtWidgets/QLabel>
#include <QtWidgets/QLineEdit>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonArray>
#include <QtGui/QScreen>
#include <QtGui/QShortcut>
#include <QtCore/QtPlugin>
#include <cstdlib>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
int main(int argc,char **argv) {
    QApplication app(argc,argv);aurora::initialize(app);aurora::DesktopSurface window;
    auto *root=new QVBoxLayout(&window);root->setContentsMargins(60,46,60,46);
    auto *panel=new aurora::GlassPanel(&window);root->addWidget(panel);auto *l=new QVBoxLayout(panel);l->setContentsMargins(28,24,28,24);l->setSpacing(12);
    l->addWidget(new QLabel("AI0  /  Intent & UI Semantics"));
    l->addWidget(new QLabel("Observe > Propose > Authorize > Execute > Verify"));
    auto *target=new QLineEdit("original");target->setAccessibleName("Draft title");target->setObjectName("draft-title");target->setMinimumHeight(36);l->addWidget(target);
    auto *password=new QLineEdit("never-export-secret");password->setEchoMode(QLineEdit::Password);password->setObjectName("protected-password");l->addWidget(password);
    auto *hidden=new QLabel("hidden text",panel);hidden->setObjectName("hidden-label");hidden->hide();
    auto *layer=new QWidget;layer->setFixedHeight(34);l->addWidget(layer);
    auto *covered=new QPushButton("Covered fixture",layer);covered->setObjectName("covered-button");covered->setGeometry(0,0,240,32);
    auto *cover=new QLabel("Opaque overlay fixture",layer);cover->setGeometry(0,0,240,32);cover->setAutoFillBackground(true);cover->raise();
    auto *proposal=new QLineEdit;proposal->setMinimumHeight(36);proposal->setPlaceholderText("Paste a structured local proposal");l->addWidget(proposal);
    auto *authorize=new QPushButton("Authorize once (local fixture)");authorize->setMinimumHeight(38);l->addWidget(authorize);
    auto *notice=new QLabel("Discovery grants no rights. No model, network or external side effects.");notice->setWordWrap(true);l->addWidget(notice);
    aurora::Semantics registry;registry.expose(target,"textbox");aurora::QtScene scene(&window);
    QObject::connect(authorize,&QPushButton::clicked,[&]{
        QJsonParseError parse;const auto request=QJsonDocument::fromJson(proposal->text().toUtf8(),&parse).object();
        QString error;if(parse.error!=QJsonParseError::NoError || !registry.propose(request,error)){notice->setText("Rejected proposal: "+error);std::printf("SEMANTIC_REJECT %s\n",error.toUtf8().constData());return;}
        aurora::Semantics::Grant no_grant;
        const auto denied=registry.execute(request,no_grant);std::printf("SEMANTIC_WITHOUT_GRANT %s\n",denied.toUtf8().constData());
        auto grant=registry.host_authorize(request,10000,error);const auto result=registry.execute(request,grant);
        notice->setText(result);std::printf("SEMANTIC_EXECUTE %s value=%s replay=%s\n",result.toUtf8().constData(),target->text().toUtf8().constData(),registry.execute(request,grant).toUtf8().constData());
        std::printf("SSG_AGENT_RESULT %s\n",QJsonDocument(scene.snapshot()).toJson(QJsonDocument::Compact).constData());
    });
    auto *quit=new QShortcut(QKeySequence(Qt::Key_Escape),&window);QObject::connect(quit,&QShortcut::activated,&app,&QApplication::quit);
    window.setGeometry(app.primaryScreen()->geometry());window.showFullScreen();
    QTimer::singleShot(250,[&]{
        auto make=[&]{const auto snap=registry.observe();const auto e=snap["controls"].toArray()[0].toObject();return QJsonObject{{"version",1},{"epoch",snap["epoch"]},{"id",e["id"]},{"revision",e["revision"]},{"action","set_text"},{"value","local-test"}};};
        auto check=[](bool condition,const char *name){std::printf("SEMANTIC_CHECK %s=%s\n",name,condition?"PASS":"FAIL");if(!condition)std::abort();};
        QString error;auto p=make();aurora::Semantics::Grant empty;check(registry.execute(p,empty)=="DENIED","no_authority_from_discovery");
        auto g=registry.host_authorize(p,10000,error);check(registry.execute(p,g)=="VERIFIED_LOCAL","actual_widget_verification");check(registry.execute(p,g)=="DENIED","no_replay");
        p=make();auto revoked=registry.host_authorize(p,10000,error);registry.revoke();check(registry.execute(p,revoked)=="DENIED","revocation");
        auto expired=registry.host_authorize(p,0,error);check(registry.execute(p,expired)=="DENIED","expiry");
        auto stale=registry.host_authorize(p,10000,error);target->setText("changed");check(registry.execute(p,stale)=="STALE_STATE","stale_state");
        p=make();auto changed=p;changed["value"]="tampered";auto bound=registry.host_authorize(p,10000,error);check(registry.execute(changed,bound)=="DENIED","exact_proposal_binding");
        changed=p;changed["epoch"]="wrong";check(!registry.propose(changed,error),"scope");
        changed=p;changed["authorized"]=true;check(!registry.propose(changed,error),"model_authorization_rejected");
        target->setReadOnly(true);p=make();check(!registry.propose(p,error),"readonly_action_refused");target->setReadOnly(false);
        target->setEchoMode(QLineEdit::Password);p=make();check(!registry.propose(p,error),"password_action_refused");target->setEchoMode(QLineEdit::Normal);
        auto *external=new QPushButton("Fixture transaction",panel);external->setAccessibleName("External effect fixture");external->show();
        aurora::Semantics external_registry;external_registry.expose(external,"button",true);
        auto snap=external_registry.observe();auto item=snap["controls"].toArray()[0].toObject();
        QJsonObject ext{{"version",1},{"epoch",snap["epoch"]},{"id",item["id"]},{"revision",item["revision"]},{"action","activate"}};
        auto ext_grant=external_registry.host_authorize(ext,10000,error);check(external_registry.execute(ext,ext_grant)=="UNKNOWN","external_unknown");check(external_registry.execute(ext,ext_grant)=="DENIED","unknown_not_retried");
        auto dead=external_registry.host_authorize(ext,10000,error);delete external;check(external_registry.execute(ext,dead)=="DEAD_TARGET","target_lifetime");
        target->setText("original");const auto snapshot=registry.observe();
        check(!QJsonDocument(snapshot).toJson().contains("original"),"content_redaction");
        std::printf("SEMANTIC_SNAPSHOT %s\n",QJsonDocument(snapshot).toJson(QJsonDocument::Compact).constData());
        check(scene.snapshot()["status"]=="DENIED","ssg_observation_default_denied");
        scene.host_allow_observation(true);auto first=scene.snapshot();const auto first_version=first["sceneVersion"].toString().toULongLong();const auto epoch=first["sourceEpoch"].toString();
        check(first["status"]=="OK" && !QJsonDocument(first).toJson().contains("never-export-secret"),"ssg_password_redaction");
        bool hidden_ok=false;for(auto v:first["nodes"].toArray()){auto n=v.toObject();if(n["nativeName"]=="hidden-label")hidden_ok=n["visibility"]=="hidden";}
        check(hidden_ok,"ssg_hidden_not_visible");
        bool covered_ok=false;for(auto v:first["nodes"].toArray()){auto n=v.toObject();if(n["nativeName"]=="covered-button")covered_ok=n["visibility"]=="locally-occluded-or-clipped";}
        check(covered_ok,"ssg_local_occlusion");
        scene.set_node_limit(0);check(scene.snapshot()["status"]=="RESOURCE_LIMIT","ssg_budget_denial");scene.set_node_limit(96);
        // The full tree above is intentionally bounded and may be capped. A
        // filtered complete query is the appropriate basis for this diff test.
        const auto before_edit=scene.snapshot(false,"textbox");
        check(before_edit["status"]=="OK" && !before_edit["capped"].toBool(),"ssg_targeted_snapshot_complete");
        target->setText("changed for diff");auto second=scene.snapshot(false,"textbox");
        auto delta=scene.diff(before_edit["sceneVersion"].toString().toULongLong(),before_edit["sourceEpoch"].toString());
        bool changed_target=false;for(auto v:delta["changed"].toArray()){auto n=v.toObject();if(n["nativeName"]=="draft-title" && n["text"]=="changed for diff")changed_target=true;}
        check(!second["capped"].toBool() && delta["status"]=="OK" && changed_target,"ssg_incremental_change");
        check(QJsonDocument(delta).toJson().size()<QJsonDocument(second).toJson().size(),"ssg_diff_smaller");
        auto *ephemeral=new QLabel("temporary",panel);ephemeral->setObjectName("ephemeral");ephemeral->show();
        const auto with_node=scene.snapshot(false,"label");QString removed_id;
        for(auto v:with_node["nodes"].toArray()){auto n=v.toObject();if(n["nativeName"]=="ephemeral")removed_id=n["id"].toString();}
        delete ephemeral;scene.snapshot(false,"label");
        const auto removal=scene.diff(with_node["sceneVersion"].toString().toULongLong(),with_node["sourceEpoch"].toString());
        check(!removed_id.isEmpty() && removal["removed"].toArray().contains(removed_id),"ssg_destroyed_node_removed");
        scene.revoke();check(scene.snapshot()["status"]=="DENIED","ssg_revocation");scene.host_allow_observation(true);
        check(scene.diff(first_version,epoch)["status"]=="UNAVAILABLE","ssg_old_epoch_invalid");
        target->setText("original");auto ssg=scene.snapshot();auto native_nodes=ssg["nodes"].toArray();
        const auto reference=registry.observe();const auto intent=reference["controls"].toArray()[0].toObject();
        for(int i=0;i<native_nodes.size();++i){auto n=native_nodes[i].toObject();if(n["nativeName"]=="draft-title"){
            n["intentRef"]=QJsonObject{{"epoch",reference["epoch"]},{"id",intent["id"]},{"revision",intent["revision"]}};native_nodes[i]=n;}}
        ssg["nodes"]=native_nodes;std::printf("SSG_AGENT_SNAPSHOT %s\n",QJsonDocument(ssg).toJson(QJsonDocument::Compact).constData());
        for(auto pair:{qMakePair("proposal",static_cast<QWidget*>(proposal)),qMakePair("authorize",static_cast<QWidget*>(authorize))}){const auto point=pair.second->mapTo(&window,pair.second->rect().center());std::printf("SEMANTIC_POINT name=%s xy=%d,%d\n",pair.first,point.x(),point.y());}
        std::printf("SEMANTIC_READY\n");
    });return app.exec();
}
