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
    // Duplicate cursor, wrong cursor, mixed revision and resource exhaustion must
    // all discard staging and leave the committed baseline intact.
    for(int fault=0;fault<4;++fault){
        c.begin();assert(c.accept(page(1,false,"5","","c")));
        auto p=page(2,false,"5","c","d");
        if(fault==0)p.cursor="c";
        if(fault==1)p.request_cursor="wrong";
        if(fault==2)p.revision="other";
        if(fault==3)p.sequence=BaselineCollector::max_pages+1;
        assert(!c.accept(p));assert(!c.commit());
        assert(c.committed()->session=="1" && c.committed()->nodes.size()==2);
    }
    c.begin();assert(c.accept(page(1,true,"6","","")));assert(c.commit());
    assert(c.committed()->session=="6" && c.committed()->nodes.size()==1);
}
