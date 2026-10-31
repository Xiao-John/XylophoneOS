// SPDX-License-Identifier: Apache-2.0
// Deterministic, independent, read-only consumer of the private pipe protocol.
#include "../ssg/pipe_wire.hpp"
#include "../ssg/page_continuity.hpp"
#include "../ssg/baseline_diff.hpp"
#include "../ssg/browser_adapter.hpp"
#include <QtCore/QCoreApplication>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QJsonParseError>
#include <QtCore/QSet>
#include <QtCore/QVector>
#include <cstdio>
using namespace ssg_pipe;
static void frame_log(const char *direction,unsigned seq,const QByteArray &bytes){
    const auto encoded=bytes.toBase64();
    std::printf("SSG_FRAME_BEGIN %s %u %d %d\n",direction,seq,int(bytes.size()),int(encoded.size()));
    for(int i=0;i<encoded.size();i+=96){const auto chunk=encoded.mid(i,96);std::printf("SSG_FRAME_PART %s %u %d %s\n",direction,seq,i,chunk.constData());}
    std::printf("SSG_FRAME_END %s %u\n",direction,seq);
}
class Client {
    Watchdog watchdog;unsigned sequence=0;QByteArray last_request;bool record_frames=true;
public:
    void set_frame_logging(bool enabled){record_frames=enabled;}
    QJsonObject request(const QJsonObject &object,bool *transport_ok=nullptr,unsigned hold_seconds=0){
        const unsigned seq=++sequence;const auto bytes=QJsonDocument(object).toJson(QJsonDocument::Compact);
        last_request=bytes;if(record_frames)frame_log("REQ",seq,bytes);auto result=send(bytes,seq,max_request,watchdog);
        QByteArray response;unsigned actual=0;
        if(result==Result::ok && hold_seconds){
            std::printf("SSG_CONSUMER_HOLD_READ seconds=%u\n",hold_seconds);
            xos::thread::sleep_until(xos::thread::clock()+xos::u64(hold_seconds)*1000000000ull);
        }
        if(result==Result::ok)result=receive(response,actual,max_response,watchdog,false);
        if(result!=Result::ok || actual!=seq){std::printf("SSG_CONSUMER_TRANSPORT seq=%u result=%s received=%u\n",seq,name(result),actual);if(transport_ok)*transport_ok=false;return {};}
        if(record_frames)frame_log("RESP",seq,response);QJsonParseError error{};const auto parsed=QJsonDocument::fromJson(response,&error);
        if(error.error!=QJsonParseError::NoError || !parsed.isObject()){if(transport_ok)*transport_ok=false;return {};}
        if(transport_ok)*transport_ok=true;return parsed.object();
    }
    Result await_eof(){QByteArray response;unsigned seq=0;return receive(response,seq,max_response,watchdog,false);}
    bool replay_last(){
        auto result=send(last_request,sequence,max_request,watchdog);QByteArray response;unsigned received=0;
        if(result==Result::ok)result=receive(response,received,max_response,watchdog,false);
        const auto status=QJsonDocument::fromJson(response).object().value("status").toString();
        std::printf("SSG_REPLAY seq=%u status=%s\n",sequence,status.toUtf8().constData());
        return result==Result::ok && received==sequence && status=="STALE_MESSAGE";
    }
};
static QJsonObject query(QString role={},bool visible=false,int limit=96){return {{"op","snapshot"},{"role",role},{"visibleOnly",visible},{"maxNodes",limit}};}
static QJsonObject reference(const QJsonObject &scene,const char *op,const QString &role){return {{"op",op},{"role",role},{"sourceInstance",scene.value("sourceInstance")},{"sourceEpoch",scene.value("sourceEpoch")},{"sceneVersion",scene.value("sceneVersion")}};}
static void display(const QJsonObject &object){
    std::printf("SSG_RESULT status=%s instance=%s epoch=%s version=%s capped=%d\n",object.value("status").toString().toUtf8().constData(),object.value("sourceInstance").toString().toUtf8().constData(),object.value("sourceEpoch").toString().toUtf8().constData(),object.value("sceneVersion").toString().toUtf8().constData(),int(object.value("capped").toBool()));
    auto nodes=object.value("nodes").toArray();if(object.value("node").isObject())nodes.append(object.value("node"));
    for(const auto value:object.value("changed").toArray())nodes.append(value);
    if(object.value("removed").isArray())std::printf("SSG_REMOVED %s\n",QJsonDocument(object.value("removed").toArray()).toJson(QJsonDocument::Compact).constData());
    if(object.value("metadata").isObject() && object.value("metadata").toObject().contains("scrollY"))
        std::printf("SSG_SCROLL value=%d\n",object.value("metadata").toObject().value("scrollY").toInt());
    for(const auto v:nodes){const auto n=v.toObject();const auto bounds=QJsonDocument(n.value("bounds").toArray()).toJson(QJsonDocument::Compact);
        QJsonArray shown;if(n.value("text").isString())shown.append(n.value("text").toString().left(100));
        const auto text=QJsonDocument(shown).toJson(QJsonDocument::Compact);
        std::printf("SSG_NODE id=%s role=%s native=%s visibility=%s bounds=%s text=%s textStatus=%s textScope=%s\n",n.value("id").toString().toUtf8().constData(),n.value("role").toString().toUtf8().constData(),n.value("nativeName").toString().toUtf8().constData(),n.value("visibility").toString().toUtf8().constData(),bounds.constData(),text.constData(),n.value("textStatus").toString().toUtf8().constData(),n.value("textScope").toString().toUtf8().constData());}
}
static int scenario(Client &client){
    int failures=0;auto check=[&](bool ok,const char *name){std::printf("SSG_CONSUMER_CHECK %s=%s\n",name,ok?"PASS":"FAIL");if(!ok)++failures;};
    bool transport=false;
    auto field=client.request(query("textbox"),&transport);check(transport && field.value("status")=="OK" && !field.value("nodes").toArray().isEmpty(),"live_line_edit");display(field);
    auto whole=client.request(query(),&transport,8);
    check(transport && whole.value("status")=="OK" && QJsonDocument(whole).toJson(QJsonDocument::Compact).size()>4096,"large_snapshot_crosses_pipe_capacity");
    auto first=client.request(query("document"),&transport);auto nodes=first.value("nodes").toArray();
    check(transport && first.value("status")=="OK" && !first.value("capped").toBool() && !nodes.isEmpty(),"live_document_snapshot");display(first);
    if(nodes.isEmpty())return 3;
    const auto before=nodes.first().toObject();
    check(before.value("nativeName")=="document" && before.value("bounds").toArray().size()==4 && before.value("text").isString(),"parsed_node_text_geometry");
    std::printf("SSG_CONSUMER_WAIT_EDIT seconds=8\n");
    xos::thread::sleep_until(xos::thread::clock()+8000000000ull);
    auto delta=client.request(reference(first,"diff","document"),&transport);
    check(transport && delta.value("status")=="OK" && !delta.value("changed").toArray().isEmpty(),"live_edit_diff");display(delta);
    auto after=client.request(query("document"),&transport);nodes=after.value("nodes").toArray();
    check(transport && !nodes.isEmpty() && nodes.first().toObject().value("text")!=before.value("text"),"live_edit_snapshot");display(after);
    auto stale=reference(first,"detail","document");stale["nodeId"]=before.value("id");
    check(client.request(stale).value("status")=="STALE_REFERENCE","stale_node_version_refused");
    auto detail=reference(after,"detail","document");detail["nodeId"]=before.value("id");
    auto actual=client.request(detail);check(actual.value("status")=="OK" && actual.value("node").toObject().value("id")==before.value("id"),"live_node_detail");display(actual);
    std::printf("SSG_CONSUMER_WAIT_SCROLL seconds=8\n");
    xos::thread::sleep_until(xos::thread::clock()+8000000000ull);
    auto scroll_diff=client.request(reference(after,"diff","document"),&transport);
    check(transport && scroll_diff.value("status")=="OK" && !scroll_diff.value("changed").toArray().isEmpty(),"scroll_diff");
    auto scrolled=client.request(query("document"),&transport);auto scroll_nodes=scrolled.value("nodes").toArray();
    check(transport && !scroll_nodes.isEmpty() && scroll_nodes.first().toObject().value("scrollY").toInt()>0,"live_scroll_state");
    after=scrolled;
    auto old=reference(after,"diff","document");old["sourceEpoch"]="0";check(client.request(old).value("status")=="SOURCE_REPLACED","stale_epoch_refused");
    old["sourceInstance"]="old-instance";check(client.request(old).value("status")=="SOURCE_REPLACED","old_provider_instance_refused");
    auto scope=reference(after,"diff","textbox");check(client.request(scope).value("status")=="RESET_REQUIRED","changed_scope_requires_snapshot");
    auto capped=client.request(query({},false,1));check(capped.value("capped").toBool(),"node_limit_reports_truncation");
    auto capped_diff=reference(capped,"diff",{});capped_diff["maxNodes"]=1;check(client.request(capped_diff).value("status")=="RESET_REQUIRED","truncated_diff_refused");
    check(client.replay_last(),"replayed_message_refused");
    std::printf("SSG_CONSUMER_DONE failures=%d waiting_for_provider_exit=1\n",failures);
    const auto eof=client.await_eof();check(eof==Result::eof,"provider_exit_eof");
    std::printf("SSG_CONSUMER_EXIT failures=%d\n",failures);return failures?1:0;
}
static int browser_scenario(Client &client){
    int failures=0;auto check=[&](bool ok,const char *name){std::printf("SSG_CONSUMER_CHECK %s=%s\n",name,ok?"PASS":"FAIL");if(!ok)++failures;};
    bool transport=false;
    auto complete_snapshot=[&]{
        QJsonObject result;
        for(int i=0;i<4;++i){
            result=client.request(query("content"),&transport);
            if(!transport || result.value("status")!="OK" || !result.value("capped").toBool())break;
            std::printf("SSG_CONSUMER_BROWSER_RESYNC capped=1 attempt=%d\n",i+1);
            xos::thread::sleep_until(xos::thread::clock()+200000000ull);
        }
        return result;
    };
    auto first=complete_snapshot();
    bool link=false,text=false,fragments=false;
    for(const auto value:first.value("nodes").toArray()){const auto n=value.toObject();
        if(n.value("role")=="link" && !n.value("href").toString().isEmpty())link=true;
        if(n.value("role")=="text" && !n.value("text").toString().isEmpty())text=true;
        if(!n.value("fragments").toArray().isEmpty() && !n.value("visibleFragments").toArray().isEmpty())fragments=true;
    }
    check(transport && first.value("status")=="OK" && !first.value("capped").toBool() && link && text && fragments,"browser_real_text_link_fragments");display(first);
    std::printf("SSG_CONSUMER_WAIT_BROWSER_SCROLL seconds=8\n");xos::thread::sleep_until(xos::thread::clock()+8000000000ull);
    auto delta=client.request(reference(first,"diff","content"),&transport);
    bool scroll_ok=transport && delta.value("status")=="OK" && delta.value("metadata").toObject().value("scrollY").toInt()>0 && !delta.value("changed").toArray().isEmpty();
    if(transport && delta.value("status")=="RESET_REQUIRED"){
        auto baseline=complete_snapshot();
        std::printf("SSG_CONSUMER_WAIT_BROWSER_RETRY_SCROLL seconds=8\n");xos::thread::sleep_until(xos::thread::clock()+8000000000ull);
        delta=client.request(reference(baseline,"diff","content"),&transport);
        scroll_ok=transport && baseline.value("status")=="OK" && !baseline.value("capped").toBool() &&
            delta.value("status")=="OK" && delta.value("metadata").toObject().value("scrollY").toInt()!=baseline.value("metadata").toObject().value("scrollY").toInt() &&
            !delta.value("changed").toArray().isEmpty();
    }
    check(scroll_ok,"browser_scroll_diff");
    auto scrolled=complete_snapshot();
    std::printf("SSG_CONSUMER_WAIT_BROWSER_RELOAD seconds=8\n");xos::thread::sleep_until(xos::thread::clock()+8000000000ull);
    auto old=client.request(reference(scrolled,"diff","content"),&transport);
    check(transport && old.value("status")=="SOURCE_REPLACED","browser_navigation_invalidates_old_epoch");
    auto old_node=reference(scrolled,"detail","content");
    if(!scrolled.value("nodes").toArray().isEmpty())old_node["nodeId"]=scrolled.value("nodes").toArray().first().toObject().value("id");
    check(client.request(old_node).value("status")=="SOURCE_REPLACED","browser_destroyed_document_node_refused");
    auto fresh=client.request(query("content"),&transport);
    check(transport && fresh.value("status")=="OK" && fresh.value("sourceEpoch")!=first.value("sourceEpoch"),"browser_reload_new_real_scene");
    auto fresh_node=reference(fresh,"detail","content");
    if(!fresh.value("nodes").toArray().isEmpty())fresh_node["nodeId"]=fresh.value("nodes").toArray().first().toObject().value("id");
    check(client.request(fresh_node).value("status")=="OK","browser_current_document_node_detail");
    auto links=client.request(query("link",true),&transport);
    check(transport && links.value("status")=="OK" && !links.value("nodes").toArray().isEmpty(),"browser_visible_link_query");
    std::printf("SSG_CONSUMER_BROWSER_DONE failures=%d waiting_for_provider_exit=1\n",failures);
    check(client.await_eof()==Result::eof,"browser_provider_exit_eof");
    std::printf("SSG_CONSUMER_BROWSER_EXIT failures=%d\n",failures);return failures?1:0;
}
static int browser_pages(Client &client){
    bool transport=false;QSet<QString> ids;QVector<QString> ancestors;
    PageContinuity continuity;
    QString instance,epoch,revision,session,cursor;int pages=0,nodes=0;bool done=false;
    auto decimal_id=[](const QJsonValue &value){
        if(!value.isString())return false;const auto s=value.toString();
        if(s.isEmpty() || s=="0" || s.startsWith('0'))return false;
        for(const auto c:s)if(c<'0' || c>'9')return false;
        bool ok=false;s.toULongLong(&ok);return ok;
    };
    auto exact_bool=[](const QJsonObject &o,const char *key,bool expected){
        return o.value(key).isBool() && o.value(key).toBool()==expected;
    };
    QJsonObject request{{"op","snapshot_begin"},{"maxNodes",8}};
    for(int i=0;i<1024;++i){
        auto result=client.request(request,&transport);++pages;
        if(!transport || result.value("status")!="OK" || result.value("pageSequence").toString()!=QString::number(pages))break;
        if(pages==1){instance=result.value("sourceInstance").toString();epoch=result.value("sourceEpoch").toString();revision=result.value("sourceRevision").toString();session=result.value("sessionId").toString();}
        if(instance.isEmpty() || epoch.isEmpty() || revision.isEmpty() || session.isEmpty() || result.value("sourceInstance")!=instance || result.value("sourceEpoch")!=epoch || result.value("sourceRevision")!=revision || result.value("sessionId")!=session)break;
        if(!result.value("nodes").isArray() || !result.value("complete").isBool() ||
           result.value("query")!="" || !exact_bool(result,"visibleOnly",false) ||
           !exact_bool(result,"sourceValid",true) || !result.value("cursor").isString())break;
        const auto page_nodes=result.value("nodes").toArray();
        const bool exhausted=result.value("complete").toBool();
        const auto scroll_value=result.value("scrollY");
        const int scroll=scroll_value.toInt(-1);
        if(!scroll_value.isDouble() || scroll_value.toDouble()!=scroll ||
           !continuity.accept(instance.toStdString(),epoch.toStdString(),revision.toStdString(),
                              unsigned(pages),scroll,exhausted,result.value("cursor").toString().toStdString()))break;
        const int visited=result.value("visited").toInt(-1);
        if(page_nodes.size()>8 || visited<page_nodes.size() || visited>16 ||
           result.value("visited").toDouble(-1)!=visited || (!exhausted && visited==0) ||
           !exact_bool(result,"hasData",!page_nodes.isEmpty()) ||
           !exact_bool(result,"hasNext",!exhausted) ||
           !exact_bool(result,"traversalComplete",exhausted) ||
           result.value("stopReason")!=(exhausted?"EXHAUSTED":"PAGE_BUDGET"))break;
        bool valid=true;
        for(const auto value:page_nodes){
            if(!value.isObject()){valid=false;break;}
            const auto n=value.toObject();const auto id=n.value("id").toString();
            const auto parent=n.value("parent").toString();
            if(!decimal_id(n.value("id")) || ids.contains(id) || ids.size()>=4096 ||
               !n.value("parent").isString() || !n.value("tag").isString() ||
               n.value("source")!="litehtml-model-and-render-layout") {valid=false;break;}
            if(ids.isEmpty()){
                if(parent!="0"){valid=false;break;}
            }else{
                // An unfiltered preorder must keep every parent, and cannot
                // return to a subtree that has already been closed.
                const auto parent_index=ancestors.lastIndexOf(parent);
                if(parent_index<0){valid=false;break;}
                ancestors.resize(parent_index+1);
            }
            ancestors.append(id);ids.insert(id);++nodes;
            const auto role=n.value("role").toString();
            if(role!="text" && role!="link" && role!="element"){valid=false;break;}
            if(role=="text"){
                const auto range=n.value("textRange").toArray();
                if(!n.value("text").isString() || n.value("text").toString().size()>1024 ||
                   !exact_bool(n,"textTruncated",false) || range.size()!=2 ||
                   range[0]!=QJsonValue(0) || range[1]!=QJsonValue(int(n.value("text").toString().size()))) {valid=false;break;}
            }
            if(role=="link" && (!n.value("href").isString() || n.value("tag")!="a")){valid=false;break;}
        }
        if(!valid)break;
        done=exhausted;const auto next=result.value("cursor").toString();
        std::printf("SSG_PAGED_CONSUMER page=%d nodes=%d visited=%d elapsed_ms=%s complete=%d\n",pages,int(page_nodes.size()),visited,result.value("elapsedMs").toString().toUtf8().constData(),int(done));
        if(done){if(!next.isEmpty())done=false;break;}
        if(next.isEmpty() || next==cursor)break;cursor=next;
        request={{"op","snapshot_next"},{"sourceInstance",instance},{"cursor",cursor}};
    }
    // Local consistency still cannot discover a missing whole subtree. Only
    // the independent test Oracle can qualify structure/text completeness.
    std::printf("SSG_PAGED_CONSUMER_DONE pages=%d nodes=%d complete=%d completeness=ORACLE_REQUIRED\n",pages,nodes,int(done));
    return done && nodes>0?0:1;
}
static bool commit_baseline(BaselineCollector &c,const char *label){
    if(!c.commit())return false;const auto &b=*c.committed();
    std::printf("SSG_BASELINE_%s_COMMITTED nodes=%u instance=%s epoch=%s revision=%s session=%s scrollY=%d\n",label,unsigned(b.nodes.size()),b.instance.c_str(),b.epoch.c_str(),b.revision.c_str(),b.session.c_str(),b.scroll);return true;
}
static int browser_pages_diff(Client &client, bool recover=false, bool exhaust=false){
    BaselineCollector a,b;
    if(!collect_baseline(client,a) || !commit_baseline(a,"A"))return 1;
    if(recover){
        bool complete=false;
        for(unsigned attempt=0;attempt<=2;++attempt){
            bool stale=false;
            if(collect_baseline(client,b,exhaust || attempt==0,&stale)){
                if(attempt==0){b.cancel();std::printf("SSG_RECOVERY_FAILED status=RESET_REQUIRED no_interruption=1\n");return 1;}
                complete=true;break;
            }
            if(!stale){std::printf("SSG_RECOVERY_FAILED status=RESET_REQUIRED\n");return 1;}
            std::printf("SSG_RECOVERY_LAST_GOOD session=%s nodes=%u\n",a.committed()->session.c_str(),unsigned(a.committed()->nodes.size()));
        }
        if(!complete){std::printf("SSG_RECOVERY_FAILED status=RESET_REQUIRED budget=2\n");return 1;}
    } else {
        std::printf("SSG_CONSUMER_WAIT_AB_SCROLL seconds=15\n");xos::thread::sleep_until(xos::thread::clock()+15000000000ull);
        if(!collect_baseline(client,b))return 1;
    }
    if(!commit_baseline(b,"B"))return 1;
    const auto d=compare_baselines(*a.committed(),*b.committed());QJsonArray changes;
    for(const auto &c:d.changes){QJsonObject item{{"kind",QString::fromStdString(c.kind)},{"id",QString::fromStdString(c.id)}};
        if(c.kind=="ScrollChanged"){item["before"]=std::stoi(c.before);item["after"]=std::stoi(c.after);}
        else if(c.kind=="WindowGeometryChanged" || c.kind=="VisibilityChanged"){item["before"]=QJsonDocument::fromJson(QByteArray::fromStdString(c.before)).object();item["after"]=QJsonDocument::fromJson(QByteArray::fromStdString(c.after)).object();}
        else {item["before"]=QString::fromStdString(c.before);item["after"]=QString::fromStdString(c.after);}changes.append(item);}
    QJsonObject result{{"status",d.status==DiffStatus::ok?"OK":d.status==DiffStatus::resource_limit?"RESOURCE_LIMIT":"RESET_REQUIRED"},{"geometryComplete",d.geometry_complete},{"changes",changes}};
    std::printf("SSG_CONSUMER_DIFF_JSON %s\n",QJsonDocument(result).toJson(QJsonDocument::Compact).constData());
    std::printf("SSG_CONSUMER_DIFF_DONE status=%s\n",result.value("status").toString().toUtf8().constData());return d.status==DiffStatus::ok?0:1;
}
static int browser_pages_reload(Client &client){
    bool transport=false;
    const auto scene=client.request(query("content"),&transport);
    if(!transport || scene.value("status")!="OK" || scene.value("nodes").toArray().isEmpty())return 1;
    BaselineCollector a, staging, c;
    if(!collect_baseline(client,a) || !commit_baseline(a,"A"))return 1;
    bool stale=false;
    if(collect_baseline(client,staging,true,&stale) || !stale){std::printf("SSG_RELOAD_FAILED no_stale=1\n");return 1;}
    auto old_node=reference(scene,"detail","content");
    old_node["nodeId"]=scene.value("nodes").toArray().first().toObject().value("id");
    const auto old=client.request(old_node,&transport);
    if(!transport || old.value("status")!="SOURCE_REPLACED")return 1;
    std::printf("SSG_RELOAD_OLD_NODE status=SOURCE_REPLACED\n");
    if(!collect_baseline(client,c) || !commit_baseline(c,"C"))return 1;
    const auto d=compare_baselines(*a.committed(),*c.committed());
    std::printf("SSG_RELOAD_DIFF status=%s changes=%u old_session=%s\n",d.status==DiffStatus::reset_required?"RESET_REQUIRED":"UNEXPECTED",unsigned(d.changes.size()),a.committed()->session.c_str());
    return d.status==DiffStatus::reset_required && d.changes.empty()?0:1;
}
static int browser_guard(Client &client){
    const auto first=client.request(query("content"));
    std::printf("SSG_CONSUMER_WAIT_BROWSER_GUARD seconds=8\n");
    xos::thread::sleep_until(xos::thread::clock()+8000000000ull);
    const auto second=client.request(query("content"));
    int failures=first.value("status")=="DENIED" && second.value("status")=="DENIED"?0:1;
    std::printf("SSG_CONSUMER_BROWSER_GUARD_DONE failures=%d\n",failures);
    if(client.await_eof()!=Result::eof)++failures;
    std::printf("SSG_CONSUMER_BROWSER_GUARD_EXIT failures=%d\n",failures);return failures?1:0;
}
// A range read is a bounded transaction. Nothing staged is published until
// every response has been checked against the same document revision.
static int text_range_live(Client &client,bool expect_refusal=false){
    constexpr int max_units=131072, max_pages=512, max_attempts=3;
    bool injected=false;
    for(int attempt=0;attempt<max_attempts;++attempt){
        bool ok=false;const auto base=client.request(query("document"),&ok);
        const auto nodes=base.value("nodes").toArray();
        if(!ok || base.value("status")!="OK" || base.value("capped").toBool() || nodes.size()!=1 ||
           base.value("sourceInstance").toString().isEmpty() || base.value("sourceEpoch").toString().isEmpty()){
            std::printf("SSG_TEXT_TRANSACTION INVALID snapshot\n");return 1;
        }
        const auto node=nodes.first().toObject();
        if(node.value("id").toString().isEmpty() || node.value("textStatus").toString()=="PROTECTED" || node.value("textStatus").toString()=="NOT_AUTHORIZED"){
            std::printf("SSG_TEXT_TRANSACTION INVALID authorization\n");return 1;
        }
        QJsonObject req{{"op","text_range"},{"sourceInstance",base.value("sourceInstance")},
            {"sourceEpoch",base.value("sourceEpoch")},{"nodeId",node.value("id")},{"maxLength",512}};
        QString staged,revision;int offset=0,total=-1;bool reset=false;
        std::printf("SSG_TEXT_TRANSACTION STAGING attempt=%d\n",attempt+1);
        for(int page=0;page<max_pages;++page){
            req["start"]=offset;if(!revision.isEmpty())req["documentRevision"]=revision;
            const auto part=client.request(req,&ok);const auto status=part.value("status").toString();
            if(ok && status=="RESET_REQUIRED" && part.value("sourceInstance")==base.value("sourceInstance") &&
               !revision.isEmpty() && !part.value("documentRevision").toString().isEmpty() && part.value("documentRevision").toString()!=revision){
                std::printf("SSG_TEXT_TRANSACTION INVALID revision old=%s new=%s\n",revision.toUtf8().constData(),part.value("documentRevision").toString().toUtf8().constData());
                const int discarded=staged.size();staged.clear();
                std::printf("SSG_TEXT_TRANSACTION DISCARDED units=%d reason=RESET_REQUIRED\n",discarded);
                reset=true;break;
            }
            if(ok && (status=="DENIED" || status=="PROTECTED")){
                const int discarded=staged.size();staged.clear();
                std::printf("SSG_TEXT_TRANSACTION DISCARDED units=%d reason=%s\n",discarded,status.toUtf8().constData());
                if(!expect_refusal || part.contains("text") || part.value("sourceInstance")!=base.value("sourceInstance"))return 1;
                // A fresh range request is still subject to the owner's restriction.
                req["start"]=0;req.remove("documentRevision");
                const auto retry=client.request(req,&ok);
                if(!ok || retry.value("status").toString()!=status || retry.contains("text") ||
                   retry.value("sourceInstance")!=base.value("sourceInstance"))return 1;
                std::printf("SSG_TEXT_TRANSACTION REFUSAL_CONFIRMED status=%s\n",status.toUtf8().constData());return 0;
            }
            if(!ok || status!="OK" || part.value("sourceInstance")!=base.value("sourceInstance") ||
               part.value("sourceEpoch")!=base.value("sourceEpoch") || part.value("nodeId")!=node.value("id") ||
               part.value("start").toInt(-1)!=offset || (!revision.isEmpty() && part.value("documentRevision").toString()!=revision)){
                std::printf("SSG_TEXT_TRANSACTION INVALID status=%s\n",status.toUtf8().constData());return 1;
            }
            revision=part.value("documentRevision").toString();
            if(total<0)total=part.value("documentLength").toInt(-1);
            const int end=part.value("end").toInt(-1);const auto value=part.value("text").toString();
            if(revision.isEmpty() || total<0 || total>max_units || total!=part.value("documentLength").toInt(-1) ||
               end<offset || end>total || (end==offset && end!=total) || value.size()!=end-offset ||
               part.value("remaining").toInt(-1)!=total-end){std::printf("SSG_TEXT_TRANSACTION INVALID range\n");return 1;}
            staged+=value;offset=end;
#ifdef XOS_SSG_TEST_DIAGNOSTICS
            if(!injected && page==1 && offset<total){
                injected=true;std::printf("SSG_NOTES_EDIT_INJECTION_READY\n");
                xos::thread::sleep_until(xos::thread::clock()+8000000000ull);
            }
#endif
            if(offset==total){
                if(expect_refusal){std::printf("SSG_TEXT_TRANSACTION INVALID expected_refusal\n");return 1;}
                std::printf("SSG_TEXT_TRANSACTION COMMITTED units=%d revision=%s\n",total,revision.toUtf8().constData());
#ifdef XOS_SSG_TEST_DIAGNOSTICS
                frame_log("TEXT",0,staged.toUtf8());
#endif
                return 0;
            }
        }
        if(!reset){std::printf("SSG_TEXT_TRANSACTION INVALID budget\n");return 1;}
    }
    std::printf("SSG_TEXT_TRANSACTION INVALID retry_budget\n");return 1;
}
static void consumer_qt_message(QtMsgType,const QMessageLogContext &,const QString &message){
    std::printf("SSG_CONSUMER_QT %s\n",message.toUtf8().constData());
}
int main(int argc,char **argv){
    qInstallMessageHandler(consumer_qt_message);
    if(xos::sdk::syscall(xos::sys_process_stdio,0,0)!=0 || xos::sdk::syscall(xos::sys_process_stdio,0,2)!=0){std::printf("SSG_CONSUMER_BAD_WIRING\n");return 2;}
    QCoreApplication app(argc,argv);std::printf("SSG_CONSUMER_START pid=%llu\n",(unsigned long long)xos::sdk::pid());Client client;
    const QString mode=argc>1?QString::fromUtf8(argv[1]):QStringLiteral("snapshot");
    if(mode=="scenario")return scenario(client);
    if(mode=="browser-scenario")return browser_scenario(client);
    if(mode=="browser-pages")return browser_pages(client);
    if(mode=="browser-pages-diff")return browser_pages_diff(client);
    if(mode=="browser-pages-recover")return browser_pages_diff(client,true);
    if(mode=="browser-pages-retry-exhaust")return browser_pages_diff(client,true,true);
    if(mode=="browser-pages-reload")return browser_pages_reload(client);
    if(mode=="browser-guard")return browser_guard(client);
    if(mode=="truncated"){
        char header[12]={'S','S','G','1'};put32(header+4,32);put32(header+8,1);
        const bool wrote=write_all(header,12)==Result::ok && write_all("{}",2)==Result::ok;
        xos::sdk::close(2);const auto result=client.await_eof();
        std::printf("SSG_CONSUMER_FAULT truncated_sent=%d result=%s\n",int(wrote),name(result));
        return wrote && result==Result::eof?0:1;
    }
    if(mode=="oversize"){
        char header[12]={'S','S','G','1'};put32(header+4,max_request+1);put32(header+8,1);
        const bool wrote=write_all(header,12)==Result::ok;
        const auto result=client.await_eof();
        std::printf("SSG_CONSUMER_FAULT oversized_header=%d result=%s\n",int(wrote),name(result));
        return wrote && result==Result::eof?0:1;
    }
    if(mode=="partial-timeout"){
        char header[12]={'S','S','G','1'};put32(header+4,32);put32(header+8,1);
        const bool wrote=write_all(header,12)==Result::ok && write_all("{}",2)==Result::ok;
        xos::thread::sleep_until(xos::thread::clock()+37000000000ull);
        const auto result=client.await_eof();
        std::printf("SSG_CONSUMER_FAULT partial_sent=%d result=%s\n",int(wrote),name(result));
        return wrote && result==Result::eof?0:1;
    }
    if(mode=="timeout"){
        const auto result=client.await_eof();std::printf("SSG_CONSUMER_FAULT idle_result=%s\n",name(result));
        return result==Result::timeout?0:1;
    }
    if((mode=="ref-diff" && argc>=6) || (mode=="ref-detail" && argc>=7)){
        QJsonObject req{{"op",mode=="ref-diff"?"diff":"detail"},{"sourceInstance",argv[2]},
            {"sourceEpoch",argv[3]},{"sceneVersion",argv[4]},{"role",argv[5]}};
        if(mode=="ref-detail")req["nodeId"]=argv[6];
        bool ok=false;const auto result=client.request(req,&ok);display(result);
        return ok && result.value("status")=="OK"?0:1;
    }
    if(mode=="text-range-live"){
#ifndef XOS_SSG_TEST_DIAGNOSTICS
        client.set_frame_logging(false);
#endif
        return text_range_live(client);
    }
#ifdef XOS_SSG_TEST_DIAGNOSTICS
    if(mode=="text-range-live-refusal")return text_range_live(client,true);
#endif
    if(mode=="text-range"){
        bool ok=false;const auto base=client.request(query("document"),&ok);
        const auto nodes=base.value("nodes").toArray();
        if(!ok || base.value("status")!="OK" || base.value("capped").toBool() || nodes.size()!=1)return 1;
        QJsonObject req{{"op","text_range"},{"sourceInstance",base.value("sourceInstance")},
            {"sourceEpoch",base.value("sourceEpoch")},{"nodeId",nodes.first().toObject().value("id")},
            {"start",0},{"maxLength",512}};
        int offset=0,total=-1;QString revision;int pages=0;
        while(pages++<256){
            req["start"]=offset;if(!revision.isEmpty())req["documentRevision"]=revision;
            const auto part=client.request(req,&ok);
            if(!ok || part.value("status")!="OK" || part.value("sourceInstance")!=base.value("sourceInstance") ||
               part.value("sourceEpoch")!=base.value("sourceEpoch") || part.value("start").toInt(-1)!=offset ||
               (!revision.isEmpty() && part.value("documentRevision").toString()!=revision))return 1;
            revision=part.value("documentRevision").toString();
            if(total<0)total=part.value("documentLength").toInt(-1);
            if(total!=part.value("documentLength").toInt(-1) || revision.isEmpty())return 1;
            const int end=part.value("end").toInt(-1);
            if(end<offset || end>total || (end==offset && end!=total) || part.value("text").toString().size()!=end-offset || part.value("remaining").toInt(-1)!=total-end)return 1;
            offset=end;if(offset==total){std::printf("SSG_TEXT_RANGE_COMPLETE pages=%d units=%d revision=%s\n",pages,total,revision.toUtf8().constData());return 0;}
        }
        std::printf("SSG_TEXT_RANGE_INCOMPLETE offset=%d total=%d\n",offset,total);return 1;
    }
    if(mode=="detail"){
        const QString role=argc>2?QString::fromUtf8(argv[2]):QString();
        const QString requested_id=argc>3?QString::fromUtf8(argv[3]):QString();
        bool ok=false;const auto base=client.request(query(role),&ok);
        QJsonObject selected;
        for(const auto value:base.value("nodes").toArray()){
            const auto node=value.toObject();
            if(requested_id.isEmpty() || node.value("id").toString()==requested_id){selected=node;break;}
        }
        if(!ok || selected.isEmpty()){std::printf("SSG_DETAIL_NOT_FOUND_OR_INCOMPLETE\n");return 1;}
        auto req=reference(base,"detail",role);req["nodeId"]=selected.value("id");
        const auto result=client.request(req,&ok);display(result);return ok && result.value("status")=="OK"?0:1;
    }
    if(mode=="diff" || mode=="watch"){
        const QString role=argc>2?QString::fromUtf8(argv[2]):QString();
        bool valid=false;const int seconds=argc>3?QString::fromUtf8(argv[3]).toInt(&valid):5;
        if((argc>3 && !valid) || seconds<1 || seconds>25)return 2;
        bool ok=false;auto base=client.request(query(role),&ok);if(!ok || base.value("status")!="OK")return 1;display(base);
        for(int i=0;i<(mode=="watch"?3:1);++i){
            std::printf("SSG_WATCH_NEXT seconds=%d\n",seconds);xos::thread::sleep_until(xos::thread::clock()+xos::u64(seconds)*1000000000ull);
            const auto change=client.request(reference(base,"diff",role),&ok);if(!ok)return 1;display(change);
            const auto status=change.value("status").toString();
            if(status!="OK" && status!="RESET_REQUIRED" && status!="SOURCE_REPLACED")return 1;
            base=client.request(query(role),&ok);if(!ok || base.value("status")!="OK")return 1;display(base);
        }
        return 0;
    }
    QJsonObject req;
    if(mode=="snapshot")req=query(argc>2?QString::fromUtf8(argv[2]):QString());
    else if(mode=="root")req=query();
    else if(mode=="visible")req=query({},true);
    else if(mode=="visible-text")req=query(argc>2 && QByteArray(argv[2])=="browser"?"text":"label",true);
    else if(mode=="clickable")req=query(argc>2 && QByteArray(argv[2])=="browser"?"link":"button",true);
    else {std::printf("SSG_USAGE snapshot [role] | root | visible | visible-text [browser] | clickable [browser] | detail [role] [id] | diff [role] [seconds] | watch [role] [seconds] | ref-detail instance epoch version role id | ref-diff instance epoch version role | scenario\n");return 2;}
    bool ok=false;auto result=client.request(req,&ok);
    if(mode=="root" && !result.value("nodes").toArray().isEmpty())result["nodes"]=QJsonArray{result.value("nodes").toArray().first()};
    display(result);return ok && result.value("status")=="OK"?0:1;
}
