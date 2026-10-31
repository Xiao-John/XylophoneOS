// SPDX-License-Identifier: Apache-2.0
// Trusted user-space supervisor and read-only dual-source consumer.
#include "../ssg/multi_source.hpp"
#include "../ssg/baseline_diff.hpp"
#include "../ssg/aggregate_diff.hpp"
#include <QtCore/QCoreApplication>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <cstdio>
#include <cstring>
using namespace xos;
using namespace ssg_multi;

struct Source {
    const char *slot;char instance[33]{};u32 input=0,output=0;i64 pid=-1;
    bool reaped=false;process_status status{};
};
static void close_token(u32 &token){if(token){sdk::syscall(sys_pipe_close,token);token=0;}}
static bool random_instance(char *out){
    u8 data[16];const char hex[]="0123456789abcdef";
    if(sdk::syscall(sys_random_bytes,reinterpret_cast<u64>(data),sizeof(data))!=0)return false;
    for(unsigned i=0;i<sizeof(data);++i){out[i*2]=hex[data[i]>>4];out[i*2+1]=hex[data[i]&15];}
    out[32]=0;return true;
}
static bool launch(Source &s,const char *program,const char *document,bool text,bool hidden_test=false,const char *fault=nullptr){
    pipe_handles request{},response{};
    if(!random_instance(s.instance) || sdk::syscall(sys_pipe_create,reinterpret_cast<u64>(&request))!=0)return false;
    if(sdk::syscall(sys_pipe_create,reinterpret_cast<u64>(&response))!=0){close_token(request.read_token);close_token(request.write_token);return false;}
    sdk::spawn_options options{};options.stdio[0]=request.read_token;options.stdio[2]=response.write_token;
    const char *args[7]={program,document,"--ssg-ipc-provider",s.instance};unsigned count=4;
    if(text)args[count++]="--ssg-ipc-text";
    if(hidden_test)args[count++]=std::strcmp(s.slot,"notes")==0?"--ssg-session-hidden":"--ssg-hidden-test";
    if(fault)args[count++]=fault;
    s.pid=sdk::spawn_file_options(program,count,args,options);
    close_token(request.read_token);close_token(response.write_token);
    if(s.pid<0){close_token(request.write_token);close_token(response.read_token);return false;}
    s.input=response.read_token;s.output=request.write_token;
    std::printf("P3B_SOURCE slot=%s supervisor=%llu provider=%lld instance=%s channel=independent\n",s.slot,(unsigned long long)sdk::pid(),(long long)s.pid,s.instance);
    return true;
}
static bool alive(Source &s){
    if(s.pid<0 || s.reaped)return false;
    const auto result=sdk::syscall(sys_process_wait,u64(s.pid),reinterpret_cast<u64>(&s.status),1);
    if(result==process_error_would_block)return true;
    if(result==0)s.reaped=true;
    return false;
}
static QJsonObject identity(const char *slot,const QString &instance,const QString &epoch,const QString &local){
    return {{"slot",slot},{"sourceInstance",instance},{"sourceEpoch",epoch},{"localNodeId",local}};
}
static QJsonObject unavailable_result(const Source &source,u64 start,u64 end,const QString &status,const QString &failure,bool hidden){
    const bool browser=std::strcmp(source.slot,"browser")==0;
    return {{"slot",source.slot},{"status",status},{"completeness","NOT_OBSERVED"},{"freshness","NOT_CURRENT"},{"failure",failure},{"instance",QString::fromLatin1(source.instance)},
            {"epoch",QJsonValue(QJsonValue::Null)},{"revision",QJsonValue(QJsonValue::Null)},
            {"scope",browser?"unfiltered-litehtml":"document-range-UTF-16"},
            {"presentation",hidden?(browser?"hidden-test-no-surface-no-input":"hidden-session-no-surface-no-input"):"visible-surface"},
            {"startedMonotonicNs",QString::number(start)},{"endedMonotonicNs",QString::number(end)}};
}
static QString client_failure(const Client &client){
    if(!client.error().isEmpty())return client.error();
    if(!client.status().isEmpty() && client.status()!="OK")return client.status();
    return QStringLiteral("COLLECTION_OR_LIVENESS");
}
static QString source_failure(const QString &reason){return reason.isEmpty()?QStringLiteral("COLLECTION_OR_LIVENESS"):reason;}
static QJsonObject browser_result(const ssg_pipe::Baseline &b,u64 start,u64 end,bool hidden){
    QJsonArray nodes;
    for(const auto &n:b.nodes){
        QJsonObject node{{"id",identity("browser",QString::fromStdString(b.instance),QString::fromStdString(b.epoch),QString::fromStdString(n.id))},
                         {"parent",QString::fromStdString(n.parent)},{"role",QString::fromStdString(n.role)},{"tag",QString::fromStdString(n.tag)}};
        if(n.has_text)node["text"]=QString::fromStdString(n.text);
        if(n.has_href)node["href"]=QString::fromStdString(n.href);
        if(n.geometry_known){
            const auto array=[](const std::string &value){return QJsonDocument::fromJson(QByteArray::fromStdString(value)).array();};
            node["bounds"]=array(n.bounds);node["visibleBounds"]=array(n.visible_bounds);
            node["fragments"]=array(n.fragments);node["visibleFragments"]=array(n.visible_fragments);
            node["visibility"]=QString::fromStdString(n.visibility);node["fragmentsComplete"]=n.fragments_complete;
        }
        nodes.append(node);
    }
    return {{"slot","browser"},{"status","OBSERVED_COMPLETE"},{"completeness","LOCALLY_COMPLETE_ORACLE_REQUIRED"},{"freshness","UNVERIFIED_AFTER_OBSERVATION"},{"instance",QString::fromStdString(b.instance)},{"epoch",QString::fromStdString(b.epoch)},
            {"revision",QString::fromStdString(b.revision)},{"session",QString::fromStdString(b.session)},{"scope","unfiltered-litehtml"},{"scrollY",b.scroll},
            {"presentation",hidden?"hidden-test-no-surface-no-input":"visible-surface"},
            {"startedMonotonicNs",QString::number(start)},{"endedMonotonicNs",QString::number(end)},{"nodes",nodes}};
}
static QJsonObject notes_result(const NotesBaseline &n,u64 start,u64 end,bool hidden){
    return {{"slot","notes"},{"status","OBSERVED_COMPLETE"},{"completeness","REVISION_CONSISTENT_OWNER_ORACLE_REQUIRED"},{"freshness","UNVERIFIED_AFTER_OBSERVATION"},{"instance",n.instance},{"epoch",n.epoch},{"revision",n.revision},
            {"scope","document-range-UTF-16"},{"presentation",hidden?"hidden-session-no-surface-no-input":"visible-surface"},
            {"startedMonotonicNs",QString::number(start)},{"endedMonotonicNs",QString::number(end)},
            {"document",QJsonObject{{"id",identity("notes",n.instance,n.epoch,n.node)},{"utf16Units",n.units},{"text",n.text}}}};
}
struct PairObservation {QJsonObject aggregate;bool browser_ok=false,notes_ok=false;};
// Recheck both processes after both sequential transactions. A source that
// exited while its peer was being read cannot be republished as current.
static PairObservation collect_pair(Client &bc,Client &nc,Source &b,Source &n,bool hidden_browser,bool hidden_notes,bool inject_note=false){
    BaselineCollector browser;const u64 bs=thread::clock();
    bool browser_ok=collect_baseline(bc,browser) && browser.commit();const u64 be=thread::clock();
    const bool browser_before=alive(b),notes_before=alive(n);
    NotesBaseline note;QString failure;const u64 ns=thread::clock();
    bool notes_ok=collect_notes(nc,note,failure,inject_note);const u64 ne=thread::clock();
    const bool browser_after=alive(b),notes_after=alive(n);
    browser_ok=browser_ok && browser_before && browser_after;notes_ok=notes_ok && notes_before && notes_after;
    const auto browser_source=browser_ok?browser_result(*browser.committed(),bs,be,hidden_browser):
        unavailable_result(b,bs,be,browser_after && bc.status()=="DENIED"?"DENIED":"UNAVAILABLE",client_failure(bc),hidden_browser);
    const auto notes_source=notes_ok?notes_result(note,ns,ne,hidden_notes):
        unavailable_result(n,ns,ne,notes_after && failure=="DENIED"?"DENIED":notes_after && failure=="PROTECTED"?"PROTECTED":"UNAVAILABLE",source_failure(failure),hidden_notes);
    return {{{"status",browser_ok&&notes_ok?"AGGREGATE_COMPLETE_OBSERVED":"AGGREGATE_PARTIAL"},
             {"semantics","sequential-per-source-non-atomic"},{"globalAtomicSnapshot","NOT_IMPLEMENTED"},
             {"sources",QJsonArray{browser_source,notes_source}}},browser_ok,notes_ok};
}
static void log_aggregate_diff(const QJsonObject &before,const QJsonObject &after){
    const auto diff=QJsonDocument(ssg_multi::aggregate_diff(before,after)).toJson(QJsonDocument::Compact);
    std::printf("P3B_AGGREGATE_DIFF %s\n",diff.constData());
}
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
static bool capture_next(const QJsonObject &next){
    const auto payload=QJsonDocument(next).toJson(QJsonDocument::Compact);
    if(payload.size()>4*1024*1024){std::printf("P3B_NEXT status=AGGREGATE_PARTIAL reason=RESOURCE_LIMIT\n");return false;}
    capture("aggregate","BASELINE",1,payload);return true;
}
#endif
static void finish(Source &s){
    close_token(s.output);close_token(s.input);
}
static bool shutdown(Source &a,Source &b){
    const u64 started=thread::clock();
    finish(a);finish(b);
    const u64 until=thread::clock()+20000000000ull;
    while(thread::clock()<until){const bool aa=alive(a),bb=alive(b);if(!aa && !bb)break;thread::sleep_until(thread::clock()+100000000ull);}
    bool clean=true;
    for(Source *s:{&a,&b}){
        bool cancelled=false;
        if(alive(*s)){cancelled=true;sdk::syscall(sys_process_cancel,u64(s->pid));}
        const u64 limit=thread::clock()+5000000000ull;
        while(!s->reaped && thread::clock()<limit){if(!alive(*s))break;thread::sleep_until(thread::clock()+100000000ull);}
        std::printf("P3B_SOURCE_EXIT slot=%s reaped=%d cancelled=%d outcome=%u code=%lld\n",s->slot,int(s->reaped),int(cancelled),unsigned(s->status.outcome),(long long)s->status.code);
        if(s->pid>=0 && (cancelled || !s->reaped || s->status.outcome!=process_outcome::exited || s->status.code!=0))clean=false;
    }
    std::printf("P3B_SHUTDOWN elapsed_ns=%llu clean=%d\n",(unsigned long long)(thread::clock()-started),int(clean));
    return clean;
}
int main(int argc,char **argv){
    QCoreApplication app(argc,argv);
    const char *browser=argc>1?argv[1]:"/web/ssg.html",*notes=argc>2?argv[2]:"/synthetic.txt";
    // Each text scope is an independent, explicit session grant. A refusal
    // takes precedence if contradictory switches are supplied.
    const bool notes_text=app.arguments().contains("--notes-text") && !app.arguments().contains("--notes-denied");
    const bool browser_text=app.arguments().contains("--browser-text") && !app.arguments().contains("--browser-denied");
    std::printf("P3B_SCOPE browser_text=%d notes_text=%d\n",int(browser_text),int(notes_text));
    Source b{"browser"},n{"notes"};
    bool hidden_notes=app.arguments().contains("--notes-hidden"),hidden_browser=false,dynamic=false;
    const char *notes_fault=nullptr;
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
    dynamic=argc>3 && std::strncmp(argv[3],"--test-",7)==0;
    const bool browser_exit_test=dynamic && std::strcmp(argv[3],"--test-browser-exit")==0;
    const bool browser_revoke_test=dynamic && std::strcmp(argv[3],"--test-browser-revoke")==0;
    const bool browser_reload_test=dynamic && std::strcmp(argv[3],"--test-browser-reload")==0;
    const bool browser_scroll_test=dynamic && std::strcmp(argv[3],"--test-browser-scroll")==0;
    const bool cross_exit_test=dynamic && std::strcmp(argv[3],"--test-browser-exit-during-notes")==0;
    const bool pipe_isolation_test=dynamic && std::strcmp(argv[3],"--test-pipe-isolation")==0;
    const bool timeout_test=dynamic && std::strcmp(argv[3],"--test-notes-timeout")==0;
    const bool truncated_test=dynamic && std::strcmp(argv[3],"--test-notes-truncated")==0;
    const bool cancel_test=dynamic && std::strcmp(argv[3],"--test-notes-cancel")==0;
    if(timeout_test)notes_fault="--ssg-test-timeout";
    if(truncated_test)notes_fault="--ssg-test-truncated";
    if(cancel_test)notes_fault="--ssg-test-cancel-stall";
    hidden_notes=!dynamic || browser_exit_test || browser_revoke_test || browser_reload_test || browser_scroll_test || cross_exit_test || pipe_isolation_test || timeout_test || truncated_test || cancel_test;
    hidden_browser=dynamic && !hidden_notes;
#endif
    if(!launch(b,"/bin/browser.elf",browser,browser_text,hidden_browser) || !launch(n,"/bin/notes.elf",notes,notes_text,hidden_notes,notes_fault)){
        std::printf("P3B_LAUNCH FAILED\n");shutdown(b,n);return 2;
    }
    if(std::strcmp(b.instance,n.instance)==0){std::printf("P3B_LAUNCH INSTANCE_COLLISION\n");shutdown(b,n);return 2;}
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
    const u32 old_tokens[4]={b.input,b.output,n.input,n.output};
#endif
    std::printf("P3B_BOTH_STARTED supervisor=%llu browser=%lld notes=%lld\n",(unsigned long long)sdk::pid(),(long long)b.pid,(long long)n.pid);
    Client bc(b.slot,b.input,b.output,b.instance,b.pid),nc(n.slot,n.input,n.output,n.instance,n.pid);
    BaselineCollector collector;const u64 bstart=thread::clock();
    bool bok=collect_baseline(bc,collector) && collector.commit();const u64 bend=thread::clock();
    const bool browser_alive=alive(b),notes_alive_before=alive(n);
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
    std::printf("P3B_BUDGET browser_remaining_ns=%llu notes_before_ns=%llu\n",(unsigned long long)bc.remaining_budget_ns(),(unsigned long long)nc.remaining_budget_ns());
#endif
    NotesBaseline note;QString failure;const u64 nstart=thread::clock();
    bool nok=collect_notes(nc,note,failure);const u64 nend=thread::clock();
    const bool browser_alive_after=alive(b),notes_alive_after=alive(n);
    bok=bok && browser_alive && browser_alive_after;nok=nok && notes_alive_before && notes_alive_after;
    QJsonObject browser_source=bok?browser_result(*collector.committed(),bstart,bend,hidden_browser):unavailable_result(b,bstart,bend,browser_alive_after && bc.status()=="DENIED"?"DENIED":"UNAVAILABLE",client_failure(bc),hidden_browser);
    QJsonObject notes_source=nok?notes_result(note,nstart,nend,hidden_notes):unavailable_result(n,nstart,nend,notes_alive_after && failure=="DENIED"?"DENIED":notes_alive_after && failure=="PROTECTED"?"PROTECTED":"UNAVAILABLE",source_failure(failure),hidden_notes);
    const QJsonObject aggregate{{"status",bok&&nok?"AGGREGATE_COMPLETE_OBSERVED":"AGGREGATE_PARTIAL"},
        {"semantics","sequential-per-source-non-atomic"},{"globalAtomicSnapshot","NOT_IMPLEMENTED"},{"sources",QJsonArray{browser_source,notes_source}}};
    const auto encoded=QJsonDocument(aggregate).toJson(QJsonDocument::Compact);
    if(encoded.size()>4*1024*1024){std::printf("P3B_AGGREGATE status=AGGREGATE_PARTIAL reason=RESOURCE_LIMIT\n");shutdown(b,n);return 1;}
    std::printf("P3B_AGGREGATE status=%s browser=%d notes=%d browser_alive=%d notes_alive=%d bytes=%d semantics=sequential-non-atomic\n",bok&&nok?"AGGREGATE_COMPLETE_OBSERVED":"AGGREGATE_PARTIAL",int(bok),int(nok),int(browser_alive_after),int(notes_alive_after),encoded.size());
    capture("aggregate","BASELINE",0,encoded);
#ifndef XOS_SSG_P3B_TEST_DIAGNOSTICS
    // Full data is emitted only on explicit request; ordinary operation logs
    // status and counts, never the document or source response frames.
    if(app.arguments().contains("--emit-aggregate"))emit_frame("aggregate","BASELINE",0,encoded);
#endif
    bool success=bok&&nok;
#ifndef XOS_SSG_P3B_TEST_DIAGNOSTICS
    if(success && app.arguments().contains("--sample-twice")){
        unsigned seconds=5;const int interval=app.arguments().indexOf("--sample-interval");
        if(interval>=0){bool valid=false;seconds=interval+1<app.arguments().size()?app.arguments().at(interval+1).toUInt(&valid):0;
            if(!valid || seconds<1 || seconds>30){std::printf("P3B_SAMPLE INVALID_INTERVAL\n");success=false;}}
        if(success){
            thread::sleep_until(thread::clock()+u64(seconds)*1000000000ull);
            const auto sample=collect_pair(bc,nc,b,n,hidden_browser,hidden_notes);
            const auto &next=sample.aggregate;
            const auto payload=QJsonDocument(next).toJson(QJsonDocument::Compact);
            if(payload.size()>4*1024*1024){std::printf("P3B_SAMPLE RESOURCE_LIMIT\n");success=false;}
            else {if(app.arguments().contains("--emit-aggregate"))emit_frame("aggregate","BASELINE",1,payload);log_aggregate_diff(aggregate,next);success=sample.browser_ok&&sample.notes_ok;}
        }
    }
#endif
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
    const int old_index=app.arguments().indexOf("--old-instance");
    if(old_index>=0){
        const auto old=old_index+1<app.arguments().size()?app.arguments().at(old_index+1):QString{};
        bool transport=false;
        const auto reference=bc.request({{"op","detail"},{"role","content"},{"sourceInstance",old},{"sourceEpoch","1"},{"sceneVersion","1"},{"nodeId","1"}},&transport);
        const bool replaced=old.size()==32 && old!=QString::fromLatin1(b.instance) && transport && reference.value("status")=="SOURCE_REPLACED" && !reference.contains("node");
        std::printf("P3B_OLD_INSTANCE status=%s\n",replaced?"SOURCE_REPLACED":"UNEXPECTED");
        success=success && replaced;
    }
    if(!browser_text && !bok && nok && bc.status()=="DENIED"){
        bool transport=false;const auto denied=bc.request({{"op","snapshot_begin"},{"maxNodes",8}},&transport);
        const bool refused=transport && denied.value("status")=="DENIED" && !denied.contains("nodes");
        std::printf("P3B_BROWSER_DENIAL_RECHECK refused=%d notes_alive=%d\n",int(refused),int(alive(n)));
        success=refused && alive(n);
    }
    if(dynamic && success && cross_exit_test){
        const auto sample=collect_pair(bc,nc,b,n,hidden_browser,hidden_notes,true);
        const bool captured=capture_next(sample.aggregate);if(captured)log_aggregate_diff(aggregate,sample.aggregate);
        const auto diff=ssg_multi::aggregate_diff(aggregate,sample.aggregate);
        const bool correct=!sample.browser_ok && sample.notes_ok && b.reaped && b.status.outcome==process_outcome::exited && b.status.code==0 &&
            diff.value("browser")=="INVALIDATED" && diff.value("notes")=="UNCHANGED";
        std::printf("P3B_CROSS_EXIT browser=%s notes=%s\n",!sample.browser_ok?"UNAVAILABLE":"UNEXPECTED",sample.notes_ok?"OBSERVED_COMPLETE":"UNAVAILABLE");
        success=captured && correct;
    } else if(dynamic && success && pipe_isolation_test){
        bool b_ok=false,n_ok=false;
        std::printf("P3B_TEST_TOKENS browser_read=%u browser_write=%u notes_read=%u notes_write=%u\n",b.input,b.output,n.input,n.output);
        const auto browser_probe=bc.request({{"op","test_pipe_isolation"},{"foreignRead",QString::number(n.input)},{"foreignWrite",QString::number(n.output)}},&b_ok);
        const auto notes_probe=nc.request({{"op","test_pipe_isolation"},{"foreignRead",QString::number(b.input)},{"foreignWrite",QString::number(b.output)}},&n_ok);
        const bool denied=b_ok && n_ok && browser_probe.value("status")=="OK" && notes_probe.value("status")=="OK" &&
            browser_probe.value("readDenied")==true && browser_probe.value("writeDenied")==true && notes_probe.value("readDenied")==true && notes_probe.value("writeDenied")==true;
        BaselineCollector fresh;const u64 bs=thread::clock();
        bool browser_ok=collect_baseline(bc,fresh) && fresh.commit() && alive(b);const u64 be=thread::clock();
        NotesBaseline updated;QString next_failure;const u64 ns=thread::clock();
        bool notes_ok=collect_notes(nc,updated,next_failure) && alive(n);const u64 ne=thread::clock();
        browser_ok=browser_ok && alive(b);notes_ok=notes_ok && alive(n);
        const bool notes_same=notes_ok && updated.instance==note.instance && updated.epoch==note.epoch && updated.node==note.node && updated.revision==note.revision && updated.text==note.text;
        const auto delta=browser_ok?ssg_pipe::compare_baselines(*collector.committed(),*fresh.committed()):ssg_pipe::Diff{};
        const bool browser_same=browser_ok && delta.status==ssg_pipe::DiffStatus::ok && delta.changes.empty();
        const QJsonObject next{{"status",browser_ok&&notes_ok?"AGGREGATE_COMPLETE_OBSERVED":"AGGREGATE_PARTIAL"},
            {"semantics","sequential-per-source-non-atomic"},{"globalAtomicSnapshot","NOT_IMPLEMENTED"},
            {"sources",QJsonArray{browser_ok?browser_result(*fresh.committed(),bs,be,hidden_browser):unavailable_result(b,bs,be,"UNAVAILABLE",client_failure(bc),hidden_browser),
                                  notes_ok?notes_result(updated,ns,ne,hidden_notes):unavailable_result(n,ns,ne,"UNAVAILABLE",source_failure(next_failure),hidden_notes)}}};
        const bool captured=capture_next(next);if(captured)log_aggregate_diff(aggregate,next);
        std::printf("P3B_PIPE_CROSS_DENIAL browser=%d notes=%d browser_after=%d notes_after=%d\n",int(b_ok && browser_probe.value("readDenied")==true && browser_probe.value("writeDenied")==true),int(n_ok && notes_probe.value("readDenied")==true && notes_probe.value("writeDenied")==true),int(browser_same),int(notes_same));
        success=captured && denied && browser_same && notes_same;
    } else if(dynamic && success && browser_scroll_test){
        std::printf("P3B_BROWSER_SCROLL_READY\n");
        thread::sleep_until(thread::clock()+12000000000ull);
        BaselineCollector fresh;const u64 bs=thread::clock();
        bool browser_ok=collect_baseline(bc,fresh) && fresh.commit() && alive(b);const u64 be=thread::clock();
        NotesBaseline updated;QString next_failure;const u64 ns=thread::clock();
        bool notes_ok=collect_notes(nc,updated,next_failure) && alive(n);const u64 ne=thread::clock();
        browser_ok=browser_ok && alive(b);notes_ok=notes_ok && alive(n);
        const bool unchanged=notes_ok && updated.instance==note.instance && updated.epoch==note.epoch && updated.node==note.node && updated.revision==note.revision && updated.text==note.text;
        ssg_pipe::Diff changes;if(browser_ok)changes=ssg_pipe::compare_baselines(*collector.committed(),*fresh.committed());
        unsigned scroll=0,geometry=0,visibility=0,other=0;
        for(const auto &change:changes.changes){if(change.kind=="ScrollChanged")++scroll;else if(change.kind=="WindowGeometryChanged")++geometry;else if(change.kind=="VisibilityChanged")++visibility;else ++other;}
        const bool changed=browser_ok && changes.status==ssg_pipe::DiffStatus::ok && scroll==1 && collector.committed()->scroll!=fresh.committed()->scroll;
        const QJsonObject next{{"status",browser_ok&&notes_ok?"AGGREGATE_COMPLETE_OBSERVED":"AGGREGATE_PARTIAL"},
            {"semantics","sequential-per-source-non-atomic"},{"globalAtomicSnapshot","NOT_IMPLEMENTED"},
            {"sources",QJsonArray{browser_ok?browser_result(*fresh.committed(),bs,be,hidden_browser):unavailable_result(b,bs,be,"UNAVAILABLE",client_failure(bc),hidden_browser),
                                  notes_ok?notes_result(updated,ns,ne,hidden_notes):unavailable_result(n,ns,ne,"UNAVAILABLE",source_failure(next_failure),hidden_notes)}}};
        const bool captured=capture_next(next);if(captured)log_aggregate_diff(aggregate,next);
        std::printf("P3B_SCROLL before=%d after=%d scroll=%u geometry=%u visibility=%u other=%u notes=%s\n",collector.committed()->scroll,browser_ok?fresh.committed()->scroll:-1,scroll,geometry,visibility,other,unchanged?"UNCHANGED":"UNKNOWN_OR_CHANGED");
        success=changed && unchanged && captured;
    } else if(dynamic && success && browser_reload_test){
        std::printf("P3B_BROWSER_RELOAD_READY\n");
        thread::sleep_until(thread::clock()+12000000000ull);
        const auto &old=*collector.committed();bool transport=false;
        const auto old_ref=bc.request({{"op","detail"},{"role","content"},{"sourceInstance",QString::fromStdString(old.instance)},
            {"sourceEpoch",QString::fromStdString(old.epoch)},{"sceneVersion","1"},{"nodeId",QString::fromStdString(old.nodes.front().id)}},&transport);
        BaselineCollector fresh;const u64 bs=thread::clock();
        bool browser_ok=collect_baseline(bc,fresh) && fresh.commit() && alive(b);const u64 be=thread::clock();
        NotesBaseline updated;QString next_failure;const u64 ns=thread::clock();
        bool notes_ok=collect_notes(nc,updated,next_failure) && alive(n);const u64 ne=thread::clock();
        browser_ok=browser_ok && alive(b);notes_ok=notes_ok && alive(n);
        const bool replaced=browser_ok && old.instance==fresh.committed()->instance && old.epoch!=fresh.committed()->epoch &&
            ssg_pipe::compare_baselines(old,*fresh.committed()).status==ssg_pipe::DiffStatus::reset_required && transport && old_ref.value("status")=="SOURCE_REPLACED";
        const bool unchanged=notes_ok && updated.instance==note.instance && updated.epoch==note.epoch && updated.node==note.node && updated.revision==note.revision && updated.text==note.text;
        const QJsonObject next{{"status",browser_ok&&notes_ok?"AGGREGATE_COMPLETE_OBSERVED":"AGGREGATE_PARTIAL"},
            {"semantics","sequential-per-source-non-atomic"},{"globalAtomicSnapshot","NOT_IMPLEMENTED"},
            {"sources",QJsonArray{browser_ok?browser_result(*fresh.committed(),bs,be,hidden_browser):unavailable_result(b,bs,be,"UNAVAILABLE",client_failure(bc),hidden_browser),
                                  notes_ok?notes_result(updated,ns,ne,hidden_notes):unavailable_result(n,ns,ne,"UNAVAILABLE",source_failure(next_failure),hidden_notes)}}};
        const bool captured=capture_next(next);if(captured)log_aggregate_diff(aggregate,next);
        std::printf("P3B_DIFF browser=%s notes=%s old_reference=%s\n",replaced?"REPLACED":"UNKNOWN",unchanged?"UNCHANGED":"UNKNOWN_OR_CHANGED",old_ref.value("status").toString().toUtf8().constData());
        success=replaced && unchanged && captured;
    } else if(dynamic && success && (browser_exit_test || browser_revoke_test)){
        std::printf("%s\n",browser_exit_test?"P3B_BROWSER_EXIT_READY":"P3B_BROWSER_REVOKE_READY");
        thread::sleep_until(thread::clock()+12000000000ull);
        const bool browser_still_alive=alive(b);
        BaselineCollector after_exit;const u64 bs=thread::clock();const bool browser_observed=collect_baseline(bc,after_exit);const u64 be=thread::clock();
        bool refused=false;
        if(browser_revoke_test && !browser_observed && bc.status()=="DENIED"){
            bool transport=false;const auto again=bc.request({{"op","snapshot_begin"},{"maxNodes",8}},&transport);
            refused=transport && again.value("status")=="DENIED" && !again.contains("nodes");
            const auto &old=*collector.committed();
            const auto old_ref=bc.request({{"op","detail"},{"role","content"},{"sourceInstance",QString::fromStdString(old.instance)},
                {"sourceEpoch",QString::fromStdString(old.epoch)},{"sceneVersion","1"},{"nodeId",QString::fromStdString(old.nodes.front().id)}},&transport);
            refused=refused && transport && old_ref.value("status")=="DENIED" && !old_ref.contains("node") && !old_ref.contains("nodes");
            std::printf("P3B_BROWSER_OLD_REF_AFTER_REVOKE status=%s\n",old_ref.value("status").toString().toUtf8().constData());
        }
        NotesBaseline updated;QString next_failure;const u64 ns=thread::clock();
        bool notes_observed=collect_notes(nc,updated,next_failure) && alive(n);const u64 ne=thread::clock();
        const bool browser_alive_final=alive(b);notes_observed=notes_observed && alive(n);
        const bool notes_unchanged=notes_observed && updated.instance==note.instance && updated.epoch==note.epoch && updated.node==note.node && updated.revision==note.revision && updated.text==note.text;
        const bool revoked=browser_revoke_test && browser_still_alive && browser_alive_final && refused;
        const QJsonObject unavailable=unavailable_result(b,bs,be,revoked?"DENIED":"UNAVAILABLE",revoked?QStringLiteral("DENIED"):bc.error().isEmpty()?QStringLiteral("SOURCE_EXITED"):bc.error(),hidden_browser);
        const QJsonObject next{{"status","AGGREGATE_PARTIAL"},{"semantics","sequential-per-source-non-atomic"},{"globalAtomicSnapshot","NOT_IMPLEMENTED"},
            {"sources",QJsonArray{unavailable,notes_observed?notes_result(updated,ns,ne,hidden_notes):unavailable_result(n,ns,ne,"UNAVAILABLE",source_failure(next_failure),hidden_notes)}}};
        const bool captured=capture_next(next);if(captured)log_aggregate_diff(aggregate,next);
        std::printf("P3B_DIFF browser=%s notes=%s retry_refused=%d browser_alive=%d notes_alive=%d\n",browser_revoke_test?(revoked?"DENIED":"UNKNOWN"):!browser_still_alive&&!browser_observed?"EXITED":"UNKNOWN",notes_unchanged?"UNCHANGED":"UNKNOWN_OR_CHANGED",int(refused),int(browser_alive_final),int(notes_observed));
        success=captured && notes_unchanged && (browser_revoke_test?revoked:!browser_still_alive && !browser_observed && b.reaped && b.status.outcome==process_outcome::exited && b.status.code==0);
    } else if(dynamic && success){
        std::printf("P3B_BASELINE_A_COMPLETE\n");
        NotesBaseline updated;QString second_failure;const u64 second_nstart=thread::clock();
        const bool second_notes=collect_notes(nc,updated,second_failure,!timeout_test && !truncated_test && !cancel_test,cancel_test);const u64 second_nend=thread::clock();
        bool retry_refused=false,alternate_refused=false;
        if(!second_notes && (second_failure=="DENIED" || second_failure=="PROTECTED")){
            NotesBaseline retry;QString retry_failure;
            retry_refused=!collect_notes(nc,retry,retry_failure) && retry_failure==second_failure;
            bool ok=false;
            const auto document=nc.request({{"op","snapshot"},{"role","document"},{"visibleOnly",false},{"maxNodes",96}},&ok);
            const auto nodes=document.value("nodes").toArray();
            const auto protected_node=nodes.size()==1?nodes.first().toObject():QJsonObject{};
            const bool no_text=ok && document.value("status")=="OK" && nodes.size()==1 && !protected_node.contains("text") &&
                protected_node.value("textStatus")== (second_failure=="DENIED"?"NOT_AUTHORIZED":"PROTECTED");
            const auto other=nc.request({{"op","snapshot"},{"role","label"},{"visibleOnly",false},{"maxNodes",96}},&ok);
            const auto marker=note.text.left(32).toUtf8();
            const bool label_safe=ok && other.value("status")=="OK" && !marker.isEmpty() && !QJsonDocument(other).toJson(QJsonDocument::Compact).contains(marker);
            const auto direct=nc.request({{"op","text_range"},{"sourceInstance",document.value("sourceInstance")},
                {"sourceEpoch",document.value("sourceEpoch")},{"nodeId",protected_node.value("id")},{"start",0},{"maxLength",512}},&ok);
            const bool range_refused=ok && direct.value("status").toString()==second_failure && !direct.contains("text");
            alternate_refused=no_text && label_safe && range_refused;
            std::printf("P3B_ALTERNATE_REFUSAL status=%s no_text=%d label_safe=%d range_refused=%d\n",second_failure.toUtf8().constData(),int(no_text),int(label_safe),int(range_refused));
        }
        BaselineCollector second_browser;const u64 second_bstart=thread::clock();
        bool second_bok=collect_baseline(bc,second_browser) && second_browser.commit() && alive(b);const u64 second_bend=thread::clock();
        const bool second_nalive=alive(n);
        second_bok=second_bok && alive(b);
        ssg_pipe::Diff delta;
        if(second_bok)delta=ssg_pipe::compare_baselines(*collector.committed(),*second_browser.committed());
        const bool browser_unchanged=second_bok && delta.status==ssg_pipe::DiffStatus::ok && delta.changes.empty();
        const bool notes_changed=second_notes && second_nalive && note.instance==updated.instance && note.epoch==updated.epoch && note.node==updated.node && note.revision!=updated.revision && note.text!=updated.text;
        const bool expected_edit=std::strcmp(argv[3],"--test-edit")==0;
        const bool expected_exit=std::strcmp(argv[3],"--test-notes-exit")==0;
        const QString expected_refusal=std::strcmp(argv[3],"--test-revoke")==0?QStringLiteral("DENIED"):QStringLiteral("PROTECTED");
        const bool expected_denial=!expected_edit && !second_notes && second_failure==expected_refusal && retry_refused && alternate_refused && second_nalive;
        QJsonObject bs=second_bok?browser_result(*second_browser.committed(),second_bstart,second_bend,hidden_browser):unavailable_result(b,second_bstart,second_bend,"UNAVAILABLE",client_failure(bc),hidden_browser);
        QJsonObject ns=second_notes && second_nalive?notes_result(updated,second_nstart,second_nend,hidden_notes):unavailable_result(n,second_nstart,second_nend,(timeout_test || truncated_test || cancel_test || !second_nalive)?QStringLiteral("UNAVAILABLE"):second_failure,source_failure(second_failure),hidden_notes);
        const QJsonObject next{{"status",second_bok&&second_notes&&second_nalive?"AGGREGATE_COMPLETE_OBSERVED":"AGGREGATE_PARTIAL"},
            {"semantics","sequential-per-source-non-atomic"},{"globalAtomicSnapshot","NOT_IMPLEMENTED"},{"sources",QJsonArray{bs,ns}}};
        const bool captured=capture_next(next);if(captured)log_aggregate_diff(aggregate,next);
        std::printf("P3B_DIFF browser=%s notes=%s retry_refused=%d browser_alive=%d notes_alive=%d\n",browser_unchanged?"UNCHANGED":"UNKNOWN_OR_CHANGED",notes_changed?"CHANGED":(timeout_test || truncated_test || cancel_test)?second_failure.toUtf8().constData():!second_nalive?"EXITED":second_failure.toUtf8().constData(),int(retry_refused),int(second_bok),int(second_nalive));
        const bool notes_exited=!second_notes && !second_nalive && n.reaped && n.status.outcome==process_outcome::exited && n.status.code==0;
        const bool fault_observed=!second_notes && ((timeout_test && second_failure=="TIMEOUT") || (truncated_test && second_failure=="TRUNCATED") || (cancel_test && second_failure=="CANCELLED"));
        success=captured && browser_unchanged && ((timeout_test || truncated_test || cancel_test)?fault_observed:expected_edit?notes_changed:expected_exit?notes_exited:expected_denial);
    }
#else
    (void)dynamic;
#endif
    std::printf("P3B_CAPTURE_COMPLETE\n");
    bool clean=shutdown(b,n);
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
    // A bounded capacity probe is not an exact global pipe counter.
    pipe_handles probes[4]{};unsigned acquired=0;
    for(;acquired<4;++acquired)if(sdk::syscall(sys_pipe_create,reinterpret_cast<u64>(&probes[acquired]))!=0)break;
    unsigned denied=0,reused=0;char byte=0;
    for(unsigned i=0;i<4;++i){
        for(unsigned j=0;j<acquired;++j)if(old_tokens[i]==probes[j].read_token || old_tokens[i]==probes[j].write_token)++reused;
        const auto result=sdk::syscall(i%2?sys_pipe_write:sys_pipe_read,old_tokens[i],reinterpret_cast<u64>(&byte),1);
        if(result==process_error_denied)++denied;
    }
    for(unsigned i=0;i<acquired;++i){close_token(probes[i].read_token);close_token(probes[i].write_token);}
    std::printf("P3B_PIPE_REUSE acquired=%u requested=4\n",acquired);
    std::printf("P3B_STALE_TOKEN_REFUSED checked=4 denied=%u reused=%u\n",denied,reused);
    clean=clean && acquired==4 && denied==4 && reused==0;
#endif
    return success && clean?0:1;
}
