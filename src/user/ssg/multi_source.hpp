// SPDX-License-Identifier: Apache-2.0
// Two explicitly wired sources, sampled sequentially. Private prototype only.
#pragma once
#include "browser_adapter.hpp"
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonParseError>
#include <xos/sdk.hpp>
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
#include <pthread.h>
#endif

namespace ssg_multi {
using namespace xos;
constexpr u64 operation_ns=30000000000ull, source_ns=300000000000ull;
constexpr unsigned max_request=4096, max_response=81920;
inline void put32(char *p,unsigned n){for(unsigned i=0;i<4;++i)p[i]=char((n>>(i*8))&255);}
inline unsigned get32(const char *p){unsigned n=0;for(unsigned i=0;i<4;++i)n|=unsigned(static_cast<unsigned char>(p[i]))<<(i*8);return n;}

inline void emit_frame(const char *slot,const char *direction,unsigned sequence,const QByteArray &data){
    const auto encoded=data.toBase64();
    std::printf("P3B_FRAME_BEGIN %s %s %u %d %d\n",slot,direction,sequence,int(data.size()),int(encoded.size()));
    for(int i=0;i<encoded.size();i+=96)std::printf("P3B_FRAME_PART %s %s %u %d %s\n",slot,direction,sequence,i,encoded.mid(i,96).constData());
    std::printf("P3B_FRAME_END %s %s %u\n",slot,direction,sequence);
}
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
inline void capture(const char *slot,const char *direction,unsigned sequence,const QByteArray &data){emit_frame(slot,direction,sequence,data);}
#else
inline void capture(const char *,const char *,unsigned,const QByteArray &){}
#endif

// Parent retains only its own two tokens. A nonblocking syscall and the
// system monotonic clock bound each transfer without closing another route.
class Client {
    const char *slot_;u32 in_,out_;QString instance_;i64 pid_;unsigned sequence_=0;u64 remaining_=source_ns;
    alignas(4) u32 cancelled_=0;
    QString error_,status_;
    struct Charge {
        Client &client;u64 started;
        ~Charge(){const auto end=thread::clock();const auto elapsed=end>=started?end-started:client.remaining_;
            client.remaining_=elapsed>=client.remaining_?0:client.remaining_-elapsed;}
    };
    bool transfer(bool write,char *data,unsigned length,u64 until){
        unsigned done=0;
        while(done<length){
            if(__atomic_load_n(&cancelled_,__ATOMIC_ACQUIRE)){error_="CANCELLED";return false;}
            if(thread::clock()>=until){error_="TIMEOUT";return false;}
            const auto n=sdk::syscall(write?sys_pipe_write:sys_pipe_read,write?out_:in_,reinterpret_cast<u64>(data+done),length-done);
            if(n>0){done+=unsigned(n);continue;}
            if(n==0 && !write){error_=done?"TRUNCATED":"EOF";return false;}
            if(n!=process_error_would_block){error_="IO_ERROR";return false;}
            thread::sleep_until(thread::clock()+10000000ull);
        }
        return true;
    }
public:
    Client(const char *slot,u32 input,u32 output,const char *instance,i64 pid)
        :slot_(slot),in_(input),out_(output),instance_(QString::fromLatin1(instance)),pid_(pid){}
    const QString &error()const{return error_;}
    const QString &status()const{return status_;}
    u64 remaining_budget_ns()const{return remaining_;}
    void cancel(){__atomic_store_n(&cancelled_,1u,__ATOMIC_RELEASE);}
    bool cancelled()const{return __atomic_load_n(&cancelled_,__ATOMIC_ACQUIRE)!=0;}
    QJsonObject request(const QJsonObject &object,bool *ok=nullptr,unsigned =0){
        if(ok)*ok=false;
        if(!error_.isEmpty())return {};
        if(__atomic_load_n(&cancelled_,__ATOMIC_ACQUIRE)){error_="CANCELLED";return {};}
        const auto payload=QJsonDocument(object).toJson(QJsonDocument::Compact);
        if(payload.isEmpty() || unsigned(payload.size())>max_request){error_="REQUEST_LIMIT";return {};}
        const auto now=thread::clock();
        if(!remaining_){error_="SOURCE_BUDGET";return {};}
        if(now>~u64{0}-operation_ns){error_="CLOCK_ERROR";return {};}
        Charge charge{*this,now};const auto until=now+qMin(remaining_,operation_ns);const unsigned seq=++sequence_;
        char header[12]={'S','S','G','1'};put32(header+4,unsigned(payload.size()));put32(header+8,seq);
        capture(slot_,"REQ",seq,payload);
        if(!transfer(true,header,12,until) || !transfer(true,const_cast<char *>(payload.constData()),unsigned(payload.size()),until))return {};
        if(!transfer(false,header,12,until))return {};
        const unsigned size=get32(header+4);
        if(QByteArray(header,4)!="SSG1" || get32(header+8)!=seq || size==0 || size>max_response){error_="BAD_FRAME";return {};}
        QByteArray reply(int(size),'\0');
        if(!transfer(false,reply.data(),size,until)){if(error_=="EOF")error_="TRUNCATED";return {};}
        if(cancelled()){error_="CANCELLED";return {};}
        capture(slot_,"RESP",seq,reply);
        QJsonParseError parse{};const auto document=QJsonDocument::fromJson(reply,&parse);
        if(parse.error!=QJsonParseError::NoError || !document.isObject()){error_="BAD_JSON";return {};}
        auto result=document.object();
        // The actual authority is the parent's prewiring. These fields are
        // consistency checks, never a grant or a source of identity.
        if(result.contains("sourceInstance") && result.value("sourceInstance").toString()!=instance_){error_="INSTANCE_MISMATCH";return {};}
        if(result.contains("providerPid") && result.value("providerPid").toString()!=QString::number(pid_)){error_="PID_MISMATCH";return {};}
        if(result.value("status")=="OK" && (result.value("sourceInstance").toString()!=instance_ || result.value("providerPid").toString()!=QString::number(pid_))){error_="IDENTITY_MISSING";return {};}
        if(cancelled()){error_="CANCELLED";return {};}
        status_=result.value("status").toString();
        if(ok)*ok=true;return result;
    }
};

struct NotesBaseline {
    QString instance,epoch,node,revision,text;
    int units=0;
};
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
struct CancelWorker {
    pthread_t thread{};bool started=false;
    ~CancelWorker(){if(started && pthread_join(thread,nullptr)!=0)xos::sdk::exit(126);}
};
inline void *cancel_after_delay(void *argument){
    xos::thread::sleep_until(xos::thread::clock()+1000000000ull);
    std::printf("P3B_CANCEL_WORKER requested_ns=%llu\n",(unsigned long long)xos::thread::clock());
    static_cast<Client *>(argument)->cancel();return nullptr;
}
#endif
// A transaction never publishes staged text on reset, refusal or failure.
inline bool collect_notes(Client &client,NotesBaseline &output,QString &failure,bool inject=false,bool cancel_test=false){
    constexpr int max_units=131072,max_ranges=512,max_attempts=3,max_text_bytes=524288;
    bool injected=false;
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
    CancelWorker cancel_worker;
#else
    (void)cancel_test;
#endif
    output=NotesBaseline{};
    for(int attempt=0;attempt<max_attempts;++attempt){
        bool ok=false;const auto base=client.request({{"op","snapshot"},{"role","document"},{"visibleOnly",false},{"maxNodes",96}},&ok);
        if(!ok){failure=client.error();return false;}
        if(base.value("status")!="OK"){failure=base.value("status").toString();return false;}
        const auto nodes=base.value("nodes").toArray();
        if(base.value("capped").toBool() || nodes.size()!=1 || base.value("sourceInstance").toString().isEmpty() || base.value("sourceEpoch").toString().isEmpty()) {failure="INVALID_SNAPSHOT";return false;}
        const auto node=nodes.first().toObject();const auto access=node.value("textStatus").toString();
        if(access=="PROTECTED" || access=="NOT_AUTHORIZED"){failure=access=="PROTECTED"?"PROTECTED":"DENIED";return false;}
        if(node.value("id").toString().isEmpty()){failure="INVALID_NODE";return false;}
        QJsonObject req{{"op","text_range"},{"sourceInstance",base.value("sourceInstance")},{"sourceEpoch",base.value("sourceEpoch")},{"nodeId",node.value("id")},{"maxLength",512}};
        QString staged,revision;int offset=0,total=-1;bool reset=false;
        for(int page=0;page<max_ranges;++page){
            req["start"]=offset;if(!revision.isEmpty())req["documentRevision"]=revision;
            const auto part=client.request(req,&ok);const auto status=part.value("status").toString();
            if(!ok){failure=client.error();if(failure=="CANCELLED")std::printf("P3B_NOTES_DISCARD reason=CANCELLED units=%d observed_ns=%llu\n",staged.size(),(unsigned long long)xos::thread::clock());return false;}
            if(status=="RESET_REQUIRED" && !revision.isEmpty() && part.value("sourceInstance")==base.value("sourceInstance") && !part.value("documentRevision").toString().isEmpty() && part.value("documentRevision").toString()!=revision){
                std::printf("P3B_NOTES_DISCARD reason=RESET_REQUIRED units=%d\n",staged.size());staged.clear();reset=true;break;
            }
            if(status!="OK"){failure=status.isEmpty()?"INVALID_STATUS":status;return false;}
            if(part.value("sourceInstance")!=base.value("sourceInstance") || part.value("sourceEpoch")!=base.value("sourceEpoch") || part.value("nodeId")!=node.value("id") ||
               part.value("indexUnit")!="UTF-16-code-unit" || !part.value("text").isString() || part.value("start").toInt(-1)!=offset ||
               (!revision.isEmpty() && part.value("documentRevision").toString()!=revision)){failure="MIXED_RANGE";return false;}
            revision=part.value("documentRevision").toString();if(total<0)total=part.value("documentLength").toInt(-1);
            const int end=part.value("end").toInt(-1);const auto value=part.value("text").toString();
            if(revision.isEmpty() || total<0 || total>max_units || total!=part.value("documentLength").toInt(-1) || end<offset || end>total ||
               (end==offset && end!=total) || value.size()!=end-offset || part.value("remaining").toInt(-1)!=total-end){failure="INVALID_RANGE";return false;}
            staged+=value;offset=end;
            if(staged.toUtf8().size()>max_text_bytes){failure="TEXT_LIMIT";return false;}
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
            if(cancel_test && !cancel_worker.started && page==1 && offset<total){
                if(pthread_create(&cancel_worker.thread,nullptr,cancel_after_delay,&client)!=0){failure="CANCEL_SETUP_FAILED";return false;}
                cancel_worker.started=true;std::printf("P3B_CANCEL_ARMED staged_units=%d\n",offset);
            }
            if(inject && !injected && page==1 && offset<total){
                injected=true;std::printf("P3B_EDIT_INJECTION_READY staged_units=%d\n",offset);
                thread::sleep_until(thread::clock()+12000000000ull);
            }
#else
            (void)inject;(void)injected;
#endif
            if(offset==total){
                if(client.cancelled()){failure="CANCELLED";std::printf("P3B_NOTES_DISCARD reason=CANCELLED units=%d observed_ns=%llu\n",staged.size(),(unsigned long long)xos::thread::clock());return false;}
                output={base.value("sourceInstance").toString(),base.value("sourceEpoch").toString(),node.value("id").toString(),revision,staged,total};failure.clear();return true;}
        }
        if(!reset){failure="RANGE_BUDGET";return false;}
    }
    failure="RETRY_BUDGET";return false;
}
}
