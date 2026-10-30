// SPDX-License-Identifier: Apache-2.0
#include "../../../src/user/ssg/baseline.hpp"
#include <cassert>
using namespace ssg_pipe;
static BaselinePage page(unsigned seq,bool complete,const char *session,const char *request,const char *cursor) {
    BaselinePage p;p.instance="instance";p.epoch="epoch";p.revision="rev";p.session=session;p.sequence=seq;
    p.request_cursor=request;p.cursor=cursor;p.complete=complete;p.source_valid=true;p.has_next=!complete;
    p.has_data=true;p.traversal_complete=complete;p.visited=1;
    BaselineNode n;n.id=seq==1?"1":"2";n.parent=seq==1?"0":"1";n.role="element";n.tag="div";p.nodes.push_back(n);return p;
}
int main(){
    BaselineCollector c;c.begin();assert(c.accept(page(1,false,"1","","a")));assert(!c.commit());
    assert(c.accept(page(2,true,"1","a","")));assert(c.commit());assert(c.committed()->nodes.size()==2);
    c.begin();assert(c.accept(page(1,false,"2","","b")));assert(!c.accept(page(2,true,"3","b","")));
    assert(!c.commit());assert(c.committed()->session=="1" && c.committed()->nodes.size()==2);
    c.begin();assert(c.accept(page(1,false,"4","","c")));c.cancel();assert(!c.commit());assert(c.committed()->session=="1");
}
