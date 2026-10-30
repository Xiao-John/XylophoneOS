// SPDX-License-Identifier: Apache-2.0
// Deterministic, independent, read-only consumer of the private pipe protocol.
#include "../ssg/pipe_wire.hpp"
#include <QtCore/QCoreApplication>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QJsonParseError>
#include <cstdio>
using namespace ssg_pipe;
static void frame_log(const char *direction,unsigned seq,const QByteArray &bytes){
    const auto encoded=bytes.toBase64();
    std::printf("SSG_FRAME_BEGIN %s %u %d %d\n",direction,seq,int(bytes.size()),int(encoded.size()));
    for(int i=0;i<encoded.size();i+=96){const auto chunk=encoded.mid(i,96);std::printf("SSG_FRAME_PART %s %u %d %s\n",direction,seq,i,chunk.constData());}
    std::printf("SSG_FRAME_END %s %u\n",direction,seq);
}
class Client {
    Watchdog watchdog;unsigned sequence=0;QByteArray last_request;
public:
    QJsonObject request(const QJsonObject &object,bool *transport_ok=nullptr,unsigned hold_seconds=0){
        const unsigned seq=++sequence;const auto bytes=QJsonDocument(object).toJson(QJsonDocument::Compact);
        last_request=bytes;frame_log("REQ",seq,bytes);auto result=send(bytes,seq,max_request,watchdog);
        QByteArray response;unsigned actual=0;
        if(result==Result::ok && hold_seconds){
            std::printf("SSG_CONSUMER_HOLD_READ seconds=%u\n",hold_seconds);
            xos::thread::sleep_until(xos::thread::clock()+xos::u64(hold_seconds)*1000000000ull);
        }
        if(result==Result::ok)result=receive(response,actual,max_response,watchdog,false);
        if(result!=Result::ok || actual!=seq){std::printf("SSG_CONSUMER_TRANSPORT seq=%u result=%s received=%u\n",seq,name(result),actual);if(transport_ok)*transport_ok=false;return {};}
        frame_log("RESP",seq,response);QJsonParseError error{};const auto parsed=QJsonDocument::fromJson(response,&error);
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
