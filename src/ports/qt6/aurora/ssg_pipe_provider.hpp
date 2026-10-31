// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ssg.hpp"
#include "../../../user/ssg/pipe_wire.hpp"
#include <QtCore/QCoreApplication>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonParseError>
#include <QtCore/QMetaObject>
#include <QtCore/QThread>
#include <QtCore/QTimer>
#include <cstdio>
#include <functional>

namespace aurora {
// One GUI-owned timer supervises the worker's partial frame and blocked write.
// If the GUI event loop itself is wedged, this cannot enforce a hard deadline.
class GuiWatchdog {
    QObject *owner;QTimer timer;alignas(4) xos::u32 state=0;
    xos::u32 timer_generation=0; // accessed only on the GUI thread
    static constexpr xos::u32 timed_out=0xfffffffeu;
public:
    explicit GuiWatchdog(QObject *o):owner(o),timer(o){
        timer.setSingleShot(true);
        QObject::connect(&timer,&QTimer::timeout,owner,[this]{
            auto s=__atomic_load_n(&state,__ATOMIC_ACQUIRE);
            if((s&1u) && s==timer_generation && __atomic_compare_exchange_n(&state,&s,timed_out,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
                xos::sdk::close(0);xos::sdk::close(2);
            }
        });
    }
    bool arm(){
        auto s=__atomic_load_n(&state,__ATOMIC_ACQUIRE);
        if((s&1u) || s>=timed_out-2)return false;
        if(!__atomic_compare_exchange_n(&state,&s,s+1,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return false;
        const auto expected=s+1;
        return QMetaObject::invokeMethod(owner,[this,expected]{if(__atomic_load_n(&state,__ATOMIC_ACQUIRE)==expected){timer_generation=expected;timer.start(int(ssg_pipe::io_timeout_ns/1000000ull));}},Qt::QueuedConnection);
    }
    bool disarm(){
        auto s=__atomic_load_n(&state,__ATOMIC_ACQUIRE);
        if(!(s&1u))return false;
        if(!__atomic_compare_exchange_n(&state,&s,s+1,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return false;
        QMetaObject::invokeMethod(owner,[this]{if(!(__atomic_load_n(&state,__ATOMIC_ACQUIRE)&1u))timer.stop();},Qt::QueuedConnection);
        return true;
    }
    bool expired()const{return __atomic_load_n(&state,__ATOMIC_ACQUIRE)==timed_out;}
};
// Application-owned, opt-in and prewired. The only worker touches bytes;
// every QtScene call is posted to this object's GUI thread.
class PipeProvider final : public QObject {
    using Snapshot=std::function<QJsonObject(bool,const QString &,unsigned)>;
    using Diff=std::function<QJsonObject(quint64,const QString &)>;
    Snapshot snapshot_source;Diff diff_source;
    std::function<QJsonObject(const QJsonObject &)> page_source;
    std::function<QJsonObject(const QString &,const QString &,int,int,const QString &)> range_source;
    QString instance;
    QThread *worker=nullptr;
    GuiWatchdog watch;
    alignas(4) xos::u32 stopping=0, mailbox=0;
    QByteArray reply;

    QJsonObject execute(const QByteArray &bytes){
        QJsonParseError error{};const auto doc=QJsonDocument::fromJson(bytes,&error);
        if(error.error!=QJsonParseError::NoError || !doc.isObject())return {{"status","BAD_REQUEST"}};
        const auto request=doc.object();const auto op=request.value("op").toString();
#if defined(XOS_SSG_TEST_CONTROLS) || defined(XOS_SSG_TEST_ORACLE)
        // Synthetic-only isolation probe. A numeric token is not a grant; the
        // kernel must reject an endpoint not held by this provider process.
        if(op=="test_pipe_isolation"){
            bool read_ok=false,write_ok=false;
            const auto read_token=request.value("foreignRead").toString().toUInt(&read_ok);
            const auto write_token=request.value("foreignWrite").toString().toUInt(&write_ok);
            if(!read_ok || !write_ok)return {{"status","BAD_REQUEST"}};
            char byte=0;
            const auto read=xos::sdk::syscall(xos::sys_pipe_read,read_token,reinterpret_cast<xos::u64>(&byte),1);
            const auto write=xos::sdk::syscall(xos::sys_pipe_write,write_token,reinterpret_cast<xos::u64>(&byte),1);
            return {{"status","OK"},{"sourceInstance",instance},{"providerPid",QString::number(xos::sdk::pid())},
                    {"readDenied",read==xos::process_error_denied},{"writeDenied",write==xos::process_error_denied}};
        }
#endif
        if(op=="snapshot_begin" || op=="snapshot_next" || op=="snapshot_cancel"){
            if(!page_source)return {{"status","UNSUPPORTED"}};
            if(op!="snapshot_begin" && request.value("sourceInstance").toString()!=instance)
                return {{"status","SOURCE_REPLACED"},{"sourceInstance",instance}};
            auto result=page_source(request);result["sourceInstance"]=instance;
            result["providerPid"]=QString::number(xos::sdk::pid());return result;
        }
        const auto role=request.value("role").toString();const auto visible=request.value("visibleOnly").toBool(false);
        const auto limit=request.contains("maxNodes")?request.value("maxNodes").toInt(-1):96;
        if(role.size()>32 || limit<1 || limit>96 || (op!="snapshot" && op!="diff" && op!="detail" && op!="text_range"))
            return {{"status","BAD_REQUEST"}};
        if(op!="snapshot" && request.value("sourceInstance").toString()!=instance)
            return {{"status","SOURCE_REPLACED"},{"sourceInstance",instance}};
        if(op=="text_range"){
            if(!range_source)return {{"status","UNSUPPORTED"}};
            const auto start=request.value("start"),maximum=request.value("maxLength");
            if(!start.isDouble() || !maximum.isDouble() || start.toDouble()!=start.toInt(-1) || maximum.toDouble()!=maximum.toInt(-1) ||
               !request.value("nodeId").isString() || !request.value("sourceEpoch").isString() ||
               (request.contains("documentRevision") && !request.value("documentRevision").isString()))return {{"status","BAD_REQUEST"}};
            auto result=range_source(request.value("sourceEpoch").toString(),request.value("nodeId").toString(),start.toInt(),maximum.toInt(),request.value("documentRevision").toString());
            result["sourceInstance"]=instance;result["providerPid"]=QString::number(xos::sdk::pid());return result;
        }
        auto snapshot=snapshot_source(visible,role,unsigned(limit));
        snapshot["sourceInstance"]=instance;
        snapshot["providerPid"]=QString::number(xos::sdk::pid());
        if(snapshot.value("status").toString()!="OK" || op=="snapshot")return snapshot;
        const auto epoch=request.value("sourceEpoch").toString();
        if(epoch!=snapshot.value("sourceEpoch").toString())
            return {{"status","SOURCE_REPLACED"},{"sourceInstance",instance},{"sourceEpoch",snapshot.value("sourceEpoch")}};
        bool ok=false;const auto version=request.value("sceneVersion").toString().toULongLong(&ok);
        if(!ok)return {{"status","BAD_REQUEST"}};
        if(op=="diff"){
            auto result=diff_source(version,epoch);result["sourceInstance"]=instance;
            result["providerPid"]=QString::number(xos::sdk::pid());return result;
        }
        if(request.value("nodeId").toString().isEmpty())return {{"status","BAD_REQUEST"}};
        if(version!=snapshot.value("sceneVersion").toString().toULongLong())
            return {{"status","STALE_REFERENCE"},{"sourceInstance",instance},{"sourceEpoch",epoch},{"sceneVersion",snapshot.value("sceneVersion")}};
        for(const auto value:snapshot.value("nodes").toArray()){
            const auto node=value.toObject();
            if(node.value("id").toString()==request.value("nodeId").toString())
                return {{"status","OK"},{"sourceInstance",instance},{"sourceEpoch",epoch},{"sceneVersion",snapshot.value("sceneVersion")},{"node",node}};
        }
        return {{"status",snapshot.value("capped").toBool()?"NOT_FOUND_OR_INCOMPLETE":"NOT_FOUND"},
                {"sourceInstance",instance},{"sourceEpoch",epoch},{"sceneVersion",snapshot.value("sceneVersion")}};
    }
    void run(){
        unsigned last_sequence=0;
#ifdef XOS_SSG_TEST_CONTROLS
        // Synthetic fault injection is compiled only into the Notes fixture.
        const bool fault_timeout=QCoreApplication::arguments().contains("--ssg-test-timeout");
        const bool fault_truncated=QCoreApplication::arguments().contains("--ssg-test-truncated");
        const bool fault_cancel=QCoreApplication::arguments().contains("--ssg-test-cancel-stall");
        bool complete_once=false;unsigned after_complete=0;
#endif
        for(;;){
            QByteArray request;unsigned sequence=0;
            auto result=ssg_pipe::receive(request,sequence,ssg_pipe::max_request,watch,true);
            if(result!=ssg_pipe::Result::ok){std::printf("SSG_PROVIDER_END pid=%llu reason=%s\n",(unsigned long long)xos::sdk::pid(),ssg_pipe::name(result));break;}
            if(sequence==0 || sequence<=last_sequence){
                result=ssg_pipe::send(QByteArray("{\"status\":\"STALE_MESSAGE\"}"),sequence,ssg_pipe::max_response,watch);
                if(result!=ssg_pipe::Result::ok)break;
                continue;
            }
            last_sequence=sequence;
#ifdef XOS_SSG_TEST_CONTROLS
            if((fault_timeout || fault_truncated || fault_cancel) && complete_once && ++after_complete==4){
                std::printf("SSG_TEST_PROVIDER_FAULT kind=%s\n",fault_timeout?"TIMEOUT":fault_cancel?"CANCEL_STALL":"TRUNCATED");
                if(fault_timeout)xos::thread::sleep_until(xos::thread::clock()+35000000000ull);
                else if(fault_cancel)xos::thread::sleep_until(xos::thread::clock()+5000000000ull);
                else {char header[12]={'S','S','G','1'};ssg_pipe::put32(header+4,32);ssg_pipe::put32(header+8,sequence);
                    ssg_pipe::write_all(header,sizeof(header));ssg_pipe::write_all("{}",2);}
                break;
            }
#endif
            __atomic_store_n(&mailbox,0u,__ATOMIC_RELEASE);
            if(!QMetaObject::invokeMethod(this,[this,request]{
                if(__atomic_load_n(&stopping,__ATOMIC_ACQUIRE))return;
                auto response=QJsonDocument(execute(request)).toJson(QJsonDocument::Compact);
                if(unsigned(response.size())>ssg_pipe::max_response)
                    response=QJsonDocument(QJsonObject{{"status","RESOURCE_LIMIT"}}).toJson(QJsonDocument::Compact);
                reply=std::move(response);
                __atomic_store_n(&mailbox,1u,__ATOMIC_RELEASE);xos::thread::wake(&mailbox);
            },Qt::QueuedConnection))break;
            while(!__atomic_load_n(&mailbox,__ATOMIC_ACQUIRE) && !__atomic_load_n(&stopping,__ATOMIC_ACQUIRE))
                xos::thread::wait(&mailbox,0);
            if(__atomic_load_n(&stopping,__ATOMIC_ACQUIRE))break;
            result=ssg_pipe::send(reply,sequence,ssg_pipe::max_response,watch);
            if(result!=ssg_pipe::Result::ok){std::printf("SSG_PROVIDER_END pid=%llu reason=%s\n",(unsigned long long)xos::sdk::pid(),ssg_pipe::name(result));break;}
#ifdef XOS_SSG_TEST_CONTROLS
            if((fault_timeout || fault_truncated || fault_cancel) && !complete_once){
                const auto sent=QJsonDocument::fromJson(reply).object();
                const auto received=QJsonDocument::fromJson(request).object();
                complete_once=received.value("op")=="text_range" && sent.value("status")=="OK" && sent.value("remaining")==0;
            }
#endif
        }
        xos::sdk::close(0);xos::sdk::close(2);
        // A session-only hidden owner has no close button. Its own explicit
        // launch choice ties its lifetime to this prewired observation pipe.
        bool quit_hidden=QCoreApplication::arguments().contains("--ssg-session-hidden");
#if defined(XOS_SSG_TEST_CONTROLS) || defined(XOS_SSG_TEST_ORACLE)
        quit_hidden=quit_hidden || QCoreApplication::arguments().contains("--ssg-hidden-test");
#endif
        if(quit_hidden)
            QMetaObject::invokeMethod(QCoreApplication::instance(),[]{QCoreApplication::quit();},Qt::QueuedConnection);
    }
public:
    PipeProvider(QtScene &source,QString source_instance)
        :snapshot_source([&source](bool visible,const QString &role,unsigned limit){source.set_node_limit(limit);return source.snapshot(visible,role);}),
         diff_source([&source](quint64 version,const QString &epoch){return source.diff(version,epoch);}),
         range_source([&source](const QString &epoch,const QString &id,int start,int maximum,const QString &revision){return source.text_range(epoch,id,start,maximum,revision);}),
         instance(std::move(source_instance)),watch(this){}
    PipeProvider(QString source_instance,Snapshot snapshot,Diff diff,std::function<QJsonObject(const QJsonObject &)> page={})
        :snapshot_source(std::move(snapshot)),diff_source(std::move(diff)),page_source(std::move(page)),
         instance(std::move(source_instance)),watch(this){}
    void start(){worker=QThread::create([this]{run();});worker->start();}
    void stop(){
        if(!worker)return;
        __atomic_store_n(&stopping,1u,__ATOMIC_RELEASE);
        xos::sdk::close(0);xos::sdk::close(2);
        __atomic_store_n(&mailbox,1u,__ATOMIC_RELEASE);xos::thread::wake(&mailbox);
        worker->wait();delete worker;worker=nullptr;
    }
    ~PipeProvider() override {stop();}
};
}
