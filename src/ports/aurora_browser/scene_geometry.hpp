// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QtCore/QJsonArray>
#include <QtCore/QRect>
#include <QtCore/QString>
#include <QtCore/QVector>

namespace browser {
struct SceneGeometry {
    QRect bounds, visible_bounds;
    QJsonArray fragments, visible_fragments;
    QString visibility;
};

// The input is the engine's bounded fragment set in window coordinates. A
// union rectangle alone can span the viewport even when no fragment enters it.
inline SceneGeometry scene_geometry(const QVector<QRect> &boxes, const QRect &viewport, bool complete) {
    SceneGeometry result;
    bool all_inside = true;
    for(const auto &box:boxes){
        if(box.isEmpty())continue;
        result.bounds=result.bounds.isNull()?box:result.bounds.united(box);
        result.fragments.append(QJsonArray{box.x(),box.y(),box.width(),box.height()});
        const auto visible=box.intersected(viewport);
        if(visible!=box)all_inside=false;
        if(!visible.isEmpty()){
            result.visible_bounds=result.visible_bounds.isNull()?visible:result.visible_bounds.united(visible);
            result.visible_fragments.append(QJsonArray{visible.x(),visible.y(),visible.width(),visible.height()});
        }
    }
    if(!complete)result.visibility=result.visible_fragments.isEmpty()?"UNKNOWN_FRAGMENT_TRUNCATED":"viewport-visible-fragments-incomplete";
    else if(result.bounds.isEmpty())result.visibility="not-rendered";
    else if(result.visible_fragments.isEmpty())result.visibility="scroll-required";
    else if(complete && all_inside)result.visibility="viewport-visible";
    else result.visibility="viewport-partial";
    return result;
}
}
