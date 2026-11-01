// SPDX-License-Identifier: Apache-2.0
#include "../../../src/ports/aurora_browser/scene_geometry.hpp"
#include <QtCore/QCoreApplication>
#include <cstdio>

int main(int argc,char **argv){
    QCoreApplication app(argc,argv);
    int failures=0;
    auto check=[&](bool ok,const char *name){
        std::printf("SSG_DIFF_CHECK %s=%s\n",name,ok?"PASS":"FAIL");if(!ok)++failures;
    };
    const QRect viewport(0,0,100,100);
    auto off=browser::scene_geometry({QRect(10,-30,10,10),QRect(10,120,10,10)},viewport,true);
    check(off.visibility=="scroll-required" && off.visible_fragments.isEmpty() && off.visible_bounds.isEmpty(),"separate_offscreen_fragments");
    auto partial=browser::scene_geometry({QRect(90,20,20,10)},viewport,true);
    check(partial.visibility=="viewport-partial" && partial.visible_bounds==QRect(90,20,10,10),"fragment_clips_to_viewport");
    auto full=browser::scene_geometry({QRect(5,5,10,10),QRect(25,25,10,10)},viewport,true);
    check(full.visibility=="viewport-visible" && full.visible_fragments.size()==2,"multiple_visible_fragments");
    auto unknown=browser::scene_geometry({QRect(10,120,10,10)},viewport,false);
    check(unknown.visibility=="UNKNOWN_FRAGMENT_TRUNCATED" && unknown.visible_fragments.isEmpty(),"truncated_offscreen_is_unknown");
    auto incomplete=browser::scene_geometry({QRect(5,5,10,10)},viewport,false);
    check(incomplete.visibility=="viewport-visible-fragments-incomplete" && incomplete.visible_fragments.size()==1,"truncated_visible_is_not_fully_visible");
    auto none=browser::scene_geometry({},viewport,true);
    check(none.visibility=="not-rendered", "no_render_fragments");
    std::printf("SSG_DIFF_TEST_DONE failures=%d\n",failures);
    return failures?1:0;
}
