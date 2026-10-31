// SPDX-License-Identifier: Apache-2.0
#include "../../../src/user/ssg/aggregate_diff.hpp"
#include <QtCore/QCoreApplication>
#include <cstdio>
int main(int argc,char **argv){
    QCoreApplication app(argc,argv);int failures=0,checks=0;
    auto check=[&](const char *name,bool ok){++checks;if(!ok)++failures;std::printf("P3B_DIFF_CHECK %s=%s\n",name,ok?"PASS":"FAIL");};
    QJsonObject a{{"slot","browser"},{"status","OBSERVED_COMPLETE"},{"instance","i1"},{"epoch","e1"},{"revision","r1"},{"startedMonotonicNs","1"},{"endedMonotonicNs","2"},{"session","1"},{"scrollY",0}};
    auto b=a;b["startedMonotonicNs"]="3";b["endedMonotonicNs"]="4";b["session"]="2";
    check("observation_time_not_content",ssg_multi::source_change(a,b)=="UNCHANGED");
    b["scrollY"]=5;check("changed",ssg_multi::source_change(a,b)=="CHANGED");
    b=a;b["instance"]="i2";check("instance_replaced",ssg_multi::source_change(a,b)=="REPLACED");
    b=a;b["epoch"]="e2";check("epoch_replaced",ssg_multi::source_change(a,b)=="REPLACED");
    b={{"slot","browser"},{"status","UNAVAILABLE"}};check("invalidated",ssg_multi::source_change(a,b)=="INVALIDATED");
    b={{"slot","browser"},{"status","DENIED"}};check("denied",ssg_multi::source_change(a,b)=="PERMISSION_CHANGED");
    b={{"slot","browser"},{"status","PROTECTED"}};check("protected",ssg_multi::source_change(a,b)=="PERMISSION_CHANGED");
    check("unobserved_is_unknown",ssg_multi::source_change(b,b)=="UNKNOWN");
    b=a;b["slot"]="notes";check("wrong_slot_is_unknown",ssg_multi::source_change(a,b)=="UNKNOWN");
    auto note=a;note["slot"]="notes";auto changed=note;changed["revision"]="r2";
    const QJsonObject old{{"sources",QJsonArray{a,note}}},now{{"sources",QJsonArray{a,changed}}};
    auto d=ssg_multi::aggregate_diff(old,now);
    check("source_specific",d.value("browser")=="UNCHANGED" && d.value("notes")=="CHANGED");
    std::printf("P3B_DIFF_TEST_DONE checks=%d failures=%d\n",checks,failures);return failures?1:0;
}
