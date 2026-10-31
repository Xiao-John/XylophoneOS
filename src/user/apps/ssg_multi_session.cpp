// SPDX-License-Identifier: Apache-2.0
// Trusted user-space supervisor and read-only dual-source consumer.
#include "../ssg/multi_source.hpp"
#include "../ssg/baseline_diff.hpp"
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
static QJsonObject browser_result(const ssg_pipe::Baseline &b,u64 start,u64 end,bool hidden){
    QJsonArray nodes;
    for(const auto &n:b.nodes){
        QJsonObject node{{"id",identity("browser",QString::fromStdString(b.instance),QString::fromStdString(b.epoch),QString::fromStdString(n.id))},
                         {"parent",QString::fromStdString(n.parent)},{"role",QString::fromStdString(n.role)},{"tag",QString::fromStdString(n.tag)}};
        if(n.has_text)node["text"]=QString::fromStdString(n.text);
        if(n.has_href)node["href"]=QString::fromStdString(n.href);
        nodes.append(node);
    }
    return {{"slot","browser"},{"status","OBSERVED_COMPLETE"},{"instance",QString::fromStdString(b.instance)},{"epoch",QString::fromStdString(b.epoch)},
            {"revision",QString::fromStdString(b.revision)},{"session",QString::fromStdString(b.session)},{"scope","unfiltered-litehtml"},
            {"presentation",hidden?"hidden-test-no-surface-no-input":"visible-surface"},
            {"startedMonotonicNs",QString::number(start)},{"endedMonotonicNs",QString::number(end)},{"nodes",nodes}};
}
static QJsonObject notes_result(const NotesBaseline &n,u64 start,u64 end,bool hidden){
    return {{"slot","notes"},{"status","OBSERVED_COMPLETE"},{"instance",n.instance},{"epoch",n.epoch},{"revision",n.revision},
            {"scope","document-range-UTF-16"},{"presentation",hidden?"hidden-session-no-surface-no-input":"visible-surface"},
            {"startedMonotonicNs",QString::number(start)},{"endedMonotonicNs",QString::number(end)},
            {"document",QJsonObject{{"id",identity("notes",n.instance,n.epoch,n.node)},{"utf16Units",n.units},{"text",n.text}}}};
}
static void finish(Source &s){
    close_token(s.output);close_token(s.input);
}
static bool shutdown(Source &a,Source &b){
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
    return clean;
}
int main(int argc,char **argv){
    QCoreApplication app(argc,argv);
    const char *browser=argc>1?argv[1]:"/web/ssg.html",*notes=argc>2?argv[2]:"/synthetic.txt";
    const bool notes_text=!app.arguments().contains("--notes-denied");
    const bool browser_text=!app.arguments().contains("--browser-denied");
    Source b{"browser"},n{"notes"};
    bool hidden_notes=app.arguments().contains("--notes-hidden"),hidden_browser=false,dynamic=false;
    const char *notes_fault=nullptr;
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
    dynamic=argc>3 && std::strncmp(argv[3],"--test-",7)==0;
    const bool browser_exit_test=dynamic && std::strcmp(argv[3],"--test-browser-exit")==0;
    const bool browser_revoke_test=dynamic && std::strcmp(argv[3],"--test-browser-revoke")==0;
    const bool browser_reload_test=dynamic && std::strcmp(argv[3],"--test-browser-reload")==0;
    const bool timeout_test=dynamic && std::strcmp(argv[3],"--test-notes-timeout")==0;
    const bool truncated_test=dynamic && std::strcmp(argv[3],"--test-notes-truncated")==0;
    if(timeout_test)notes_fault="--ssg-test-timeout";
    if(truncated_test)notes_fault="--ssg-test-truncated";
    hidden_notes=!dynamic || browser_exit_test || browser_revoke_test || browser_reload_test || timeout_test || truncated_test;
    hidden_browser=dynamic && !hidden_notes;
#endif
    if(!launch(b,"/bin/browser.elf",browser,browser_text,hidden_browser) || !launch(n,"/bin/notes.elf",notes,notes_text,hidden_notes,notes_fault)){
        std::printf("P3B_LAUNCH FAILED\n");shutdown(b,n);return 2;
    }
    if(std::strcmp(b.instance,n.instance)==0){std::printf("P3B_LAUNCH INSTANCE_COLLISION\n");shutdown(b,n);return 2;}
    std::printf("P3B_BOTH_STARTED supervisor=%llu browser=%lld notes=%lld\n",(unsigned long long)sdk::pid(),(long long)b.pid,(long long)n.pid);
    Client bc(b.slot,b.input,b.output,b.instance,b.pid),nc(n.slot,n.input,n.output,n.instance,n.pid);
    BaselineCollector collector;const u64 bstart=thread::clock();
    bool bok=collect_baseline(bc,collector) && collector.commit();const u64 bend=thread::clock();
    const bool browser_alive=alive(b),notes_alive_before=alive(n);
    NotesBaseline note;QString failure;const u64 nstart=thread::clock();
    bool nok=collect_notes(nc,note,failure);const u64 nend=thread::clock();
    const bool browser_alive_after=alive(b),notes_alive_after=alive(n);
    bok=bok && browser_alive && browser_alive_after;nok=nok && notes_alive_before && notes_alive_after;
    QJsonObject browser_source=bok?browser_result(*collector.committed(),bstart,bend,hidden_browser):QJsonObject{{"slot","browser"},{"status",bc.status()=="DENIED"?"DENIED":"UNAVAILABLE"},{"failure",!bc.error().isEmpty()?bc.error():!bc.status().isEmpty()?bc.status():QStringLiteral("COLLECTION_OR_LIVENESS")}};
    QJsonObject notes_source=nok?notes_result(note,nstart,nend,hidden_notes):QJsonObject{{"slot","notes"},{"status",failure=="DENIED"?"DENIED":failure=="PROTECTED"?"PROTECTED":"UNAVAILABLE"},{"failure",failure.isEmpty()?QStringLiteral("COLLECTION_OR_LIVENESS"):failure}};
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
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
    if(!browser_text && !bok && nok && bc.status()=="DENIED"){
        bool transport=false;const auto denied=bc.request({{"op","snapshot_begin"},{"maxNodes",8}},&transport);
        const bool refused=transport && denied.value("status")=="DENIED" && !denied.contains("nodes");
        std::printf("P3B_BROWSER_DENIAL_RECHECK refused=%d notes_alive=%d\n",int(refused),int(alive(n)));
        success=refused && alive(n);
    }
    if(dynamic && success && browser_reload_test){
        std::printf("P3B_BROWSER_RELOAD_READY\n");
        thread::sleep_until(thread::clock()+12000000000ull);
        const auto &old=*collector.committed();bool transport=false;
        const auto old_ref=bc.request({{"op","detail"},{"role","content"},{"sourceInstance",QString::fromStdString(old.instance)},
            {"sourceEpoch",QString::fromStdString(old.epoch)},{"sceneVersion","1"},{"nodeId",QString::fromStdString(old.nodes.front().id)}},&transport);
        BaselineCollector fresh;const u64 bs=thread::clock();
        const bool browser_ok=collect_baseline(bc,fresh) && fresh.commit() && alive(b);const u64 be=thread::clock();
        NotesBaseline updated;QString next_failure;const u64 ns=thread::clock();
        const bool notes_ok=collect_notes(nc,updated,next_failure) && alive(n);const u64 ne=thread::clock();
        const bool replaced=browser_ok && old.instance==fresh.committed()->instance && old.epoch!=fresh.committed()->epoch &&
            ssg_pipe::compare_baselines(old,*fresh.committed()).status==ssg_pipe::DiffStatus::reset_required && transport && old_ref.value("status")=="SOURCE_REPLACED";
        const bool unchanged=notes_ok && updated.instance==note.instance && updated.epoch==note.epoch && updated.node==note.node && updated.revision==note.revision && updated.text==note.text;
        const QJsonObject next{{"status",browser_ok&&notes_ok?"AGGREGATE_COMPLETE_OBSERVED":"AGGREGATE_PARTIAL"},
            {"semantics","sequential-per-source-non-atomic"},{"globalAtomicSnapshot","NOT_IMPLEMENTED"},
            {"sources",QJsonArray{browser_ok?browser_result(*fresh.committed(),bs,be,hidden_browser):QJsonObject{{"slot","browser"},{"status","UNAVAILABLE"}},
                                  notes_ok?notes_result(updated,ns,ne,hidden_notes):QJsonObject{{"slot","notes"},{"status","UNAVAILABLE"}}}}};
        capture("aggregate","BASELINE",1,QJsonDocument(next).toJson(QJsonDocument::Compact));
        std::printf("P3B_DIFF browser=%s notes=%s old_reference=%s\n",replaced?"REPLACED":"UNKNOWN",unchanged?"UNCHANGED":"UNKNOWN_OR_CHANGED",old_ref.value("status").toString().toUtf8().constData());
        success=replaced && unchanged;
    } else if(dynamic && success && (browser_exit_test || browser_revoke_test)){
        std::printf("%s\n",browser_exit_test?"P3B_BROWSER_EXIT_READY":"P3B_BROWSER_REVOKE_READY");
        thread::sleep_until(thread::clock()+12000000000ull);
        const bool browser_still_alive=alive(b);
        BaselineCollector after_exit;const bool browser_observed=collect_baseline(bc,after_exit);
        bool refused=false;
        if(browser_revoke_test && !browser_observed && bc.status()=="DENIED"){
            bool transport=false;const auto again=bc.request({{"op","snapshot_begin"},{"maxNodes",8}},&transport);
            refused=transport && again.value("status")=="DENIED" && !again.contains("nodes");
        }
        NotesBaseline updated;QString next_failure;const u64 ns=thread::clock();
        const bool notes_observed=collect_notes(nc,updated,next_failure) && alive(n);const u64 ne=thread::clock();
        const bool notes_unchanged=notes_observed && updated.instance==note.instance && updated.epoch==note.epoch && updated.node==note.node && updated.revision==note.revision && updated.text==note.text;
        const QJsonObject unavailable{{"slot","browser"},{"status",browser_revoke_test?"DENIED":"UNAVAILABLE"},{"failure",browser_revoke_test?QStringLiteral("DENIED"):bc.error().isEmpty()?QStringLiteral("SOURCE_EXITED"):bc.error()}};
        const QJsonObject next{{"status","AGGREGATE_PARTIAL"},{"semantics","sequential-per-source-non-atomic"},{"globalAtomicSnapshot","NOT_IMPLEMENTED"},
            {"sources",QJsonArray{unavailable,notes_observed?notes_result(updated,ns,ne,hidden_notes):QJsonObject{{"slot","notes"},{"status","UNAVAILABLE"}}}}};
        capture("aggregate","BASELINE",1,QJsonDocument(next).toJson(QJsonDocument::Compact));
        std::printf("P3B_DIFF browser=%s notes=%s retry_refused=%d browser_alive=%d notes_alive=%d\n",browser_revoke_test?(refused?"DENIED":"UNKNOWN"):!browser_still_alive&&!browser_observed?"EXITED":"UNKNOWN",notes_unchanged?"UNCHANGED":"UNKNOWN_OR_CHANGED",int(refused),int(browser_still_alive),int(notes_observed));
        success=notes_unchanged && (browser_revoke_test?browser_still_alive && refused:!browser_still_alive && !browser_observed && b.reaped && b.status.outcome==process_outcome::exited && b.status.code==0);
    } else if(dynamic && success){
        std::printf("P3B_BASELINE_A_COMPLETE\n");
        NotesBaseline updated;QString second_failure;const u64 second_nstart=thread::clock();
        const bool second_notes=collect_notes(nc,updated,second_failure,!timeout_test && !truncated_test);const u64 second_nend=thread::clock();
        bool retry_refused=false;
        if(!second_notes && (second_failure=="DENIED" || second_failure=="PROTECTED")){
            NotesBaseline retry;QString retry_failure;
            retry_refused=!collect_notes(nc,retry,retry_failure) && retry_failure==second_failure;
        }
        BaselineCollector second_browser;const u64 second_bstart=thread::clock();
        const bool second_bok=collect_baseline(bc,second_browser) && second_browser.commit() && alive(b);const u64 second_bend=thread::clock();
        const bool second_nalive=alive(n);
        ssg_pipe::Diff delta;
        if(second_bok)delta=ssg_pipe::compare_baselines(*collector.committed(),*second_browser.committed());
        const bool browser_unchanged=second_bok && delta.status==ssg_pipe::DiffStatus::ok && delta.changes.empty();
        const bool notes_changed=second_notes && second_nalive && note.instance==updated.instance && note.epoch==updated.epoch && note.node==updated.node && note.revision!=updated.revision && note.text!=updated.text;
        const bool expected_edit=std::strcmp(argv[3],"--test-edit")==0;
        const bool expected_exit=std::strcmp(argv[3],"--test-notes-exit")==0;
        const QString expected_refusal=std::strcmp(argv[3],"--test-revoke")==0?QStringLiteral("DENIED"):QStringLiteral("PROTECTED");
        const bool expected_denial=!expected_edit && !second_notes && second_failure==expected_refusal && retry_refused && second_nalive;
        QJsonObject bs=second_bok?browser_result(*second_browser.committed(),second_bstart,second_bend,hidden_browser):QJsonObject{{"slot","browser"},{"status","UNAVAILABLE"}};
        QJsonObject ns=second_notes?notes_result(updated,second_nstart,second_nend,hidden_notes):QJsonObject{{"slot","notes"},{"status",(timeout_test || truncated_test || !second_nalive)?QStringLiteral("UNAVAILABLE"):second_failure},{"failure",second_failure}};
        const QJsonObject next{{"status",second_bok&&second_notes&&second_nalive?"AGGREGATE_COMPLETE_OBSERVED":"AGGREGATE_PARTIAL"},
            {"semantics","sequential-per-source-non-atomic"},{"globalAtomicSnapshot","NOT_IMPLEMENTED"},{"sources",QJsonArray{bs,ns}}};
        capture("aggregate","BASELINE",1,QJsonDocument(next).toJson(QJsonDocument::Compact));
        std::printf("P3B_DIFF browser=%s notes=%s retry_refused=%d browser_alive=%d notes_alive=%d\n",browser_unchanged?"UNCHANGED":"UNKNOWN_OR_CHANGED",notes_changed?"CHANGED":(timeout_test || truncated_test)?second_failure.toUtf8().constData():!second_nalive?"EXITED":second_failure.toUtf8().constData(),int(retry_refused),int(second_bok),int(second_nalive));
        const bool notes_exited=!second_notes && !second_nalive && n.reaped && n.status.outcome==process_outcome::exited && n.status.code==0;
        const bool fault_observed=!second_notes && ((timeout_test && second_failure=="TIMEOUT") || (truncated_test && second_failure=="TRUNCATED"));
        success=browser_unchanged && ((timeout_test || truncated_test)?fault_observed:expected_edit?notes_changed:expected_exit?notes_exited:expected_denial);
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
    for(unsigned i=0;i<acquired;++i){close_token(probes[i].read_token);close_token(probes[i].write_token);}
    std::printf("P3B_PIPE_REUSE acquired=%u requested=4\n",acquired);
    clean=clean && acquired==4;
#endif
    return success && clean?0:1;
}
