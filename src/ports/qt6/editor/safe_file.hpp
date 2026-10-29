// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QtCore/QFile>
#include <QtCore/QByteArray>
#include <QtCore/QString>
#include <xos/file_client.hpp>
#include <cstdio>
namespace xos_editor {
constexpr qsizetype limit=1024*1024;
struct SaveResult { bool saved=false; bool unknown=false; QString message; };
inline bool read(const QString &path,QByteArray &bytes,QString &error) {
    QFile f(path);
    if(!f.open(QIODevice::ReadOnly)){error=f.errorString();return false;}
    if(f.size()>limit){error=QStringLiteral("File exceeds 1 MiB editor limit");return false;}
    bytes=f.readAll();
    if(f.error()!=QFileDevice::NoError){error=f.errorString();return false;}
    f.close();
    if(f.error()!=QFileDevice::NoError){error=f.errorString();return false;}
    return true;
}
// No QFile WriteOnly/truncate or QSaveFile fallback. Existing v2 staging only.
// A returned commit error is indeterminate: don't retry or mark the document clean.
inline SaveResult save(const QString &path,const QByteArray &bytes) {
    if(bytes.size()>limit) return {false,false,QStringLiteral("File exceeds 1 MiB editor limit")};
    const auto name=path.toUtf8();
    if(!path.startsWith('/') || name.size()>=xos::file::max_name || name.contains('\0'))
        return {false,false,QStringLiteral("Use an absolute path shorter than 256 UTF-8 bytes")};
    xos::file::Client client{};
    if(!client.init()) return {false,false,QStringLiteral("File service unavailable")};
    xos::u32 size=0,version=0,handle=0;
    auto rc=client.stat(name.constData(),size,version);
    if(rc==0) {
        // FatFs read-only attribute is enforced by a non-truncating writable open;
        // stat's public flags expose directory status, not the FAT read-only bit.
        rc=client.open(name.constData(),xos::file::read_write,handle,size,version);
        if(rc==0) rc=client.close(handle);
        if(rc) return {false,false,QStringLiteral("Target is not writable / close failed (%1)").arg(rc)};
    } else if(rc!=static_cast<xos::i64>(xos::file::status::not_found)) {
        return {false,false,QStringLiteral("Cannot inspect target (%1)").arg(rc)};
    }
    rc=client.begin_replace(name.constData(),xos::u32(bytes.size()));
    if(rc) return {false,false,QStringLiteral("Cannot stage save (%1); original retained").arg(rc)};
    std::printf("EDITOR_SAVE_STAGE bytes=%lld\n",(long long)bytes.size());
    for(xos::u32 offset=0;offset<bytes.size();) {
        const auto n=qMin<xos::u32>(xos::file::request_data_size,xos::u32(bytes.size())-offset);
        rc=client.chunk_replace(offset,bytes.constData()+offset,n);
        if(rc){client.abort_replace();return {false,false,QStringLiteral("Short/failed staging write (%1); original retained").arg(rc)};}
        offset+=n;
    }
    rc=client.sync();
    if(rc){client.abort_replace();return {false,false,QStringLiteral("Staging sync failed (%1); original retained").arg(rc)};}
    std::printf("EDITOR_SAVE_COMMIT\n");
    rc=client.commit_replace();
    if(rc) return {false,true,QStringLiteral("Commit outcome unknown (%1). Keep buffer; reboot/recover before retry.").arg(rc)};
    rc=client.sync();
    if(rc) return {false,true,QStringLiteral("Final sync failed (%1). Keep buffer; saved state unknown.").arg(rc)};
    QByteArray verified;QString error;
    if(!read(path,verified,error) || verified!=bytes)
        return {false,true,QStringLiteral("Readback mismatch/error. Keep buffer; saved state unknown.")};
    std::printf("EDITOR_SAVE_OK bytes=%lld\n",(long long)bytes.size());
    return {true,false,QStringLiteral("Saved, synced and byte-verified")};
}
}
