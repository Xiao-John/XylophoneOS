// SPDX-License-Identifier: Apache-2.0
// Exercise the real QtScene against live Qt Widgets in an XOS guest.
#include "../../../src/ports/qt6/aurora/ssg.hpp"
#include <QtWidgets/QApplication>
#include <QtWidgets/QPlainTextEdit>
#include <QtGui/QTextDocument>
#include <QtCore/QtPlugin>
#include <cstdio>
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    QWidget root; auto *edit = new QPlainTextEdit(&root);
    edit->setPlainText(QString::fromUtf8("A😀B\nC")); root.show();
    aurora::QtScene scene(&root); scene.host_allow_observation(true);
    int failures=0, checks=0;
    auto check=[&](bool value,const char *name){++checks;if(!value)++failures;std::printf("SSG_RANGE_CHECK %s=%s\n",name,value?"PASS":"FAIL");};
    auto snapshot=scene.snapshot(false,"document");
    auto epoch=snapshot["sourceEpoch"].toString();
    auto id=snapshot["nodes"].toArray().first().toObject()["id"].toString();
    auto first=scene.text_range(epoch,id,0,2,{}); auto revision=first["documentRevision"].toString();
    check(first["status"]=="OK" && first["text"]=="A" && first["end"]==1,"surrogate_end_not_split");
    check(scene.text_range(epoch,id,2,2,revision)["status"]=="INVALID_BOUNDARY","surrogate_start_rejected");
    auto middle=scene.text_range(epoch,id,1,2,revision);
    check(middle["status"]=="OK" && middle["text"].toString()==QString::fromUtf8("😀") && middle["end"]==3,"surrogate_pair_whole");
    auto last=scene.text_range(epoch,id,3,1024,revision);
    check(last["status"]=="OK" && last["text"]=="B\nC" && last["remaining"]==0,"last_page");
    check(scene.text_range(epoch,id,7,2,revision)["status"]=="OUT_OF_RANGE","out_of_range");
    check(scene.text_range(epoch,id,-1,2,revision)["status"]=="BAD_QUERY" && scene.text_range(epoch,id,0,1,{})["status"]=="BAD_QUERY" && scene.text_range(epoch,id,0,1025,{})["status"]=="BAD_QUERY","invalid_lengths_and_offset");
    check(scene.text_range(epoch,id,1,2,{})["status"]=="BAD_QUERY","missing_revision_rejected");
    edit->insertPlainText("X");
    check(scene.text_range(epoch,id,1,2,revision)["status"]=="RESET_REQUIRED","edit_invalidates_revision");
    edit->setProperty("xosSsgProtected",true);
    check(scene.text_range(epoch,id,0,2,{})["status"]=="PROTECTED","protection_rechecked");
    edit->setProperty("xosSsgProtected",false);
    auto *replacement=new QTextDocument(edit); edit->setDocument(replacement);
    check(scene.text_range(epoch,id,0,2,{})["status"]=="STALE_REFERENCE","replacement_invalidates_reference");
    scene.revoke();
    check(scene.text_range(epoch,id,0,2,{})["status"]=="DENIED","revocation_rechecked");
    scene.host_allow_observation(true); snapshot=scene.snapshot(false,"document");
    epoch=snapshot["sourceEpoch"].toString();id=snapshot["nodes"].toArray().first().toObject()["id"].toString();
    auto empty=scene.text_range(epoch,id,0,2,{});
    check(empty["status"]=="OK" && empty["end"]==0 && empty["remaining"]==0 && empty["text"]=="","empty_document");
    delete edit;
    check(scene.text_range(epoch,id,0,2,{})["status"]=="STALE_REFERENCE","deleted_widget_invalidates_reference");
    std::printf("SSG_RANGE_TEST_DONE checks=%d failures=%d\n",checks,failures);
    return failures?1:0;
}
