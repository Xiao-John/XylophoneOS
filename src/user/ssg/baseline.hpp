// SPDX-License-Identifier: Apache-2.0
// Bounded, transactional storage for an unfiltered preorder traversal.
#pragma once
#include "page_continuity.hpp"
#include <algorithm>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace ssg_pipe {
struct BaselineNode {
    std::string id, parent, role, tag, text, href;
    // Serialized protocol fields. Geometry is window-relative; scroll is separate.
    std::string fragments, visible_fragments, bounds, visible_bounds, visibility;
    bool has_text=false, has_href=false, geometry_known=false, fragments_complete=false;
};
struct Baseline {
    std::string instance, epoch, revision, session, scope, authority;
    bool visible_only=false, traversal_complete=false, locally_consistent=false;
    // Only a separate verifier can set oracle_verified and qualify a baseline.
    bool oracle_verified=false, formally_qualified=false;
    int scroll=0;
    std::vector<BaselineNode> nodes;
};
struct BaselinePage {
    std::string instance, epoch, revision, session, scope, authority, request_cursor, cursor;
    unsigned sequence=0, visited=0;
    int scroll=0;
    bool visible_only=false, complete=false, source_valid=false, has_next=false, has_data=false, traversal_complete=false;
    std::vector<BaselineNode> nodes;
};
class BaselineCollector {
public:
    enum class State { idle, staging, validated, committed, invalid };
    static constexpr size_t max_nodes=4096, max_bytes=4*1024*1024, max_text_bytes=1024*1024, max_pages=1024;
private:
    State state_=State::idle;
    Baseline staging_, committed_;
    bool has_committed_=false;
    PageContinuity continuity_;
    std::set<std::string> ids_;
    std::vector<std::string> stack_;
    size_t bytes_=0, text_bytes_=0;
    std::string expected_cursor_;
    static bool id_ok(const std::string &s, bool zero=false) {
        if (s.empty() || (s.size()>1 && s[0]=='0') || (!zero && s=="0") || s.size()>20) return false;
        uint64_t n=0;
        for(char c:s) { if(c<'0'||c>'9'||n>(UINT64_MAX-unsigned(c-'0'))/10) return false; n=n*10+unsigned(c-'0'); }
        return true;
    }
    bool fail(){ state_=State::invalid; staging_=Baseline{}; ids_.clear(); stack_.clear(); continuity_=PageContinuity{}; expected_cursor_.clear(); bytes_=text_bytes_=0; return false; }
public:
    void begin(){state_=State::staging; staging_=Baseline{}; continuity_=PageContinuity{}; ids_.clear(); stack_.clear(); bytes_=text_bytes_=0; expected_cursor_.clear();}
    void cancel(){fail();}
    State state()const{return state_;}
    const Baseline *committed()const{return has_committed_?&committed_:nullptr;}
    bool accept(const BaselinePage &p) {
        if(state_!=State::staging || p.sequence>max_pages || p.scope!="" || p.visible_only || p.session.empty() ||
           p.instance.size()>256 || p.epoch.size()>128 || p.revision.size()>128 || p.session.size()>256 || p.authority.size()>256 || p.cursor.size()>256 || p.request_cursor.size()>256 ||
           !p.source_valid || p.request_cursor!=expected_cursor_ || p.has_next==p.complete || p.has_data!=!p.nodes.empty() ||
           p.traversal_complete!=p.complete || p.nodes.size()>16 || p.visited<p.nodes.size() || p.visited>16 || (!p.complete && !p.visited)) return fail();
        if(!continuity_.accept(p.instance,p.epoch,p.revision,p.sequence,p.scroll,p.complete,p.cursor))return fail();
        if(p.sequence==1){staging_.instance=p.instance;staging_.epoch=p.epoch;staging_.revision=p.revision;staging_.session=p.session;staging_.scope=p.scope;staging_.visible_only=p.visible_only;staging_.authority=p.authority;staging_.scroll=p.scroll;}
        else if(p.session!=staging_.session || p.scope!=staging_.scope || p.visible_only!=staging_.visible_only || p.authority!=staging_.authority)return fail();
        for(const auto &n:p.nodes){
            if(!id_ok(n.id) || !id_ok(n.parent,true) || ids_.count(n.id) || ids_.size()>=max_nodes ||
               (n.role!="text" && n.role!="link" && n.role!="element") || (n.role=="text" && !n.has_text) || (n.role=="link" && (!n.has_href || n.tag!="a")))return fail();
            if(ids_.empty()){if(n.parent!="0")return fail();}
            else {auto it=std::find(stack_.begin(),stack_.end(),n.parent);if(it==stack_.end())return fail();stack_.erase(it+1,stack_.end());}
            const size_t cost=n.id.size()+n.parent.size()+n.role.size()+n.tag.size()+n.text.size()+n.href.size()+n.fragments.size()+n.visible_fragments.size()+n.bounds.size()+n.visible_bounds.size()+n.visibility.size()+sizeof(BaselineNode);
            if(cost>max_bytes-bytes_ || n.text.size()>max_text_bytes-text_bytes_)return fail();
            bytes_+=cost;text_bytes_+=n.text.size();stack_.push_back(n.id);ids_.insert(n.id);staging_.nodes.push_back(n);
        }
        expected_cursor_=p.cursor;
        if(p.complete){if(staging_.nodes.empty())return fail();staging_.traversal_complete=true;staging_.locally_consistent=true;state_=State::validated;}
        return true;
    }
    bool commit(){if(state_!=State::validated)return false;committed_=std::move(staging_);has_committed_=true;state_=State::committed;return true;}
};
}
