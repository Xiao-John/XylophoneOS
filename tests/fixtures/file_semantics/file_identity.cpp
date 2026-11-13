// SPDX-License-Identifier: Apache-2.0
// Reuse the real service/FatFs memory disk and existing 25 regression cases.
#define main file_semantics_baseline_main
#include "file_semantics.cpp"
#undef main

namespace {
client_session& owner = sessions[0];

void fresh() {
    reset_media();
    owner = client_session{};
    owner.pid = 10;
    owner.parent_pid = 5;
    for (auto& entry : kernel_sessions) { entry = file_session_info{}; }
    write_fault_after = write_short_by = write_fail_nth = read_fault_after = -1;
    rename_fault_nth = rename_fault_nth2 = -1;
    unlink_fault = disk_write_fault = false;
}

void ok(const response& result, const char* why) {
    if (result.status_code != 0) {
        std::fprintf(stderr, "status=%d at %s\n", result.status_code, why);
        require(false, why);
    }
}

u32 opened(const char* path, u32 flags = read_write) {
    const response result = open_path(owner, path, flags);
    ok(result, path);
    return result.handle;
}

response named(op operation, const char* path, u32 flags = 0) {
    request in = make_request(operation);
    set_name(in, path);
    in.flags = flags;
    return call(owner, in);
}

std::string handle_text(u32 handle) {
    ok(seek_handle(owner, handle, 0, seek_set), "read rewind");
    const response result = read_handle(owner, handle, 128);
    ok(result, "read content");
    return std::string(reinterpret_cast<const char*>(result.data), result.length);
}

std::string cwd(client_session& session) {
    const response result = call(session, make_request(op::cwd_get));
    ok(result, "get cwd");
    return std::string(result.name, result.name_length);
}

void no_objects() {
    for (const auto& object : file_objects) { require(!object.used, "all object references reclaimed"); }
}

DWORD free_clusters() {
    DWORD free = 0;
    FATFS* volume = nullptr;
    require(f_getfree("", &free, &volume) == FR_OK && volume == &fs, "free clusters");
    return free;
}

void fill_disk(DWORD leave) {
    FIL filler{};
    require(f_open(&filler, "filler.bin", FA_CREATE_NEW | FA_WRITE) == FR_OK, "filler open");
    std::vector<unsigned char> cluster(fs.csize * 512u, 0x5a);
    const DWORD available = free_clusters();
    require(available >= leave, "filler budget");
    for (DWORD i = leave; i < available; ++i) {
        UINT written = 0;
        require(f_write(&filler, cluster.data(), cluster.size(), &written) == FR_OK &&
                written == cluster.size(), "real filler allocation");
    }
    require(f_close(&filler) == FR_OK && free_clusters() == leave, "filler leaves requested free space");
}

void new_check(const char* label) {
    ++checks;
    std::printf("[identity] %s ok\n", label);
}
}

int main(int argc, char** argv) {
    if (file_semantics_baseline_main(argc, argv) != 0) { return 1; }
    checks = 0;

    fresh();
    seed_file("shared", "abcdef", 6);
    u32 writer = opened("shared"), reader = opened("shared", read_only);
    const u32 inode = fstat_handle(owner, writer).reserved;
    require(fstat_handle(owner, reader).reserved == inode, "independent open shares inode");
    require(read_handle(owner, reader, 2).length == 2, "reader advances independently");
    require(seek_handle(owner, writer, 0, seek_current).value == 0, "writer offset independent");
    require(write_handle(owner, writer, "XY", 2).value == 2, "shared writer progress");
    require(handle_text(reader) == "XYcdef", "reader sees shared FIL content");
    ok(close_handle(owner, writer), "writer close retains reader");
    require(handle_text(reader) == "XYcdef", "reader after writer close");
    ok(close_handle(owner, reader), "reader close");
    no_objects();
    new_check("independent_open_shared_inode");

    fresh();
    seed_file("append", "0", 1);
    const u32 append_a = opened("append", read_write | open_append);
    const u32 append_b = opened("append", read_write | open_append);
    require(write_handle(owner, append_a, "1", 1).value == 1 &&
            write_handle(owner, append_b, "2", 1).value == 1, "independent append writes");
    require(handle_text(append_a) == "012", "append uses shared current EOF");
    require(named(op::stat, "append").value == 3, "stat sees unsynced shared length");
    close_session(owner);
    new_check("independent_append_current_eof");

    fresh();
    seed_file("truncate", "abcdef", 6);
    writer = opened("truncate");
    ok(seek_handle(owner, writer, 5, seek_set), "saved offset");
    const u32 truncating = opened("truncate", write_only | open_truncate);
    require(fstat_handle(owner, writer).value == 0 &&
            seek_handle(owner, writer, 0, seek_current).value == 5, "truncate shares size not offset");
    require(write_handle(owner, writer, "X", 1).value == 1, "write after independent truncate");
    ok(close_handle(owner, truncating), "truncate close");
    ok(close_handle(owner, writer), "original close");
    require(read_file("truncate") == std::string("\0\0\0\0\0X", 6), "truncate shared cache and zero gap");
    new_check("truncate_shared_metadata_independent_offset");

    fresh();
    seed_file("A long file name.txt", "alias", 5);
    FILINFO alias{};
    require(f_stat("A long file name.txt", &alias) == FR_OK && alias.altname[0] != '\0', "SFN alias exists");
    writer = opened("A long file name.txt");
    reader = opened(alias.altname, read_only);
    require(fstat_handle(owner, writer).reserved == fstat_handle(owner, reader).reserved, "LFN SFN identity");
    require(open_path(owner, alias.altname, read_write | open_create | open_exclusive).status_code ==
            static_cast<i32>(status::exists), "exclusive checks existing shared inode");
    close_session(owner);
    new_check("lfn_sfn_aliases_share_object");

    fresh();
    seed_file("before", "old", 3);
    writer = opened("before");
    const u32 moved_inode = fstat_handle(owner, writer).reserved;
    ok(rename_path(owner, "before", "after"), "rename open file");
    require(named(op::stat, "before").status_code == static_cast<i32>(status::not_found), "old name absent");
    require(named(op::stat, "after").reserved == moved_inode, "rename preserves inode");
    require(write_handle(owner, writer, "new", 3).value == 3, "write renamed open file");
    ok(close_handle(owner, writer), "close renamed file");
    require(read_file("after") == "new", "sync uses moved directory entry");
    new_check("open_rename_updates_fatfs_entry");

    fresh();
    seed_file("deleted", "old", 3);
    writer = opened("deleted");
    const u32 deleted_inode = fstat_handle(owner, writer).reserved;
    const DWORD before_unlink = free_clusters();
    ok(named(op::remove, "deleted"), "unlink open file");
    require((fstat_handle(owner, writer).flags & stat_unlinked) != 0 &&
            fstat_handle(owner, writer).reserved == deleted_inode, "unlinked inode still open");
    require(free_clusters() == before_unlink, "unlink retains data allocation");
    const u32 replacement = opened("deleted", read_write | open_create);
    require(fstat_handle(owner, replacement).reserved != deleted_inode, "recreated path has fresh inode");
    require(write_handle(owner, replacement, "new", 3).value == 3 && handle_text(writer) == "old", "recreation cannot hijack old fd");
    ok(close_handle(owner, writer), "last close unlinked");
    require(free_clusters() == before_unlink, "last close reclaims old cluster despite new file allocation");
    ok(close_handle(owner, replacement), "replacement close");
    no_objects();
    new_check("unlink_delays_reclamation_and_prevents_reuse");

    fresh();
    seed_file("source", "new", 3);
    seed_file("target", "old", 3);
    writer = opened("source");
    reader = opened("target", read_only);
    const u32 source_inode = fstat_handle(owner, writer).reserved;
    const u32 target_inode = fstat_handle(owner, reader).reserved;
    ok(rename_path(owner, "source", "target"), "replace two open files");
    require(named(op::stat, "target").reserved == source_inode && source_inode != target_inode, "replace installs source identity");
    require(handle_text(writer) == "new" && handle_text(reader) == "old", "both old file descriptions stay on their objects");
    require((fstat_handle(owner, reader).flags & stat_unlinked) != 0, "replaced object becomes unlinked");
    close_session(owner);
    require(read_file("target") == "new" && read_file(backup_name) == "<absent>", "replace cleanup");
    no_objects();
    new_check("rename_over_open_target_preserves_both_objects");

    fresh();
    ok(mkdir_path(owner, "left"), "mkdir left");
    ok(mkdir_path(owner, "right"), "mkdir right");
    ok(mkdir_path(owner, "left/tree"), "mkdir source tree");
    ok(mkdir_path(owner, "right/empty"), "mkdir destination");
    seed_file("left/tree/data", "kept", 4);
    writer = opened("left/tree/data");
    const u32 old_directory = opened("right/empty", read_only | open_directory);
    ok(named(op::cwd_set, "right/empty"), "cwd old destination");
    ok(rename_path(owner, "/left/tree", "/right/empty"), "replace empty directory across parents");
    require(call(owner, make_request(op::cwd_get)).status_code == static_cast<i32>(status::not_found), "replaced cwd unlinked");
    require(open_path(owner, "intruder", read_write | open_create).status_code == static_cast<i32>(status::not_found), "deleted cwd cannot create in replacement");
    request listing = make_request(op::list);
    listing.handle = old_directory;
    const response empty = call(owner, listing);
    require(empty.status_code == 0 && empty.length == 0, "old opened directory remains empty");
    ok(named(op::cwd_set, ".."), "escape unlinked cwd");
    require(cwd(owner) == "/right" && handle_text(writer) == "kept", "original parent and descendant fd retained");
    close_session(owner);
    no_objects();
    new_check("directory_replace_and_unlinked_cwd_parent");

    fresh();
    ok(mkdir_path(owner, "Long parent folder"), "long parent");
    ok(mkdir_path(owner, "Long parent folder/child"), "child directory");
    require(f_stat("Long parent folder", &alias) == FR_OK && alias.altname[0] != '\0', "parent alias");
    std::string alias_child = std::string(alias.altname) + "/child";
    ok(named(op::cwd_set, alias_child.c_str()), "cwd through alias");
    require(cwd(owner) == "/Long parent folder/child", "canonical stored cwd spelling");
    ok(rename_path(owner, "/Long parent folder", "/moved"), "rename ancestor with cwd descendant");
    ok(mkdir_path(owner, "/Long parent folder"), "recreate old ancestor");
    ok(mkdir_path(owner, "/Long parent folder/child"), "recreate old cwd path");
    require(cwd(owner) == "/moved/child", "cwd follows renamed identity");
    writer = opened("relative", read_write | open_create);
    require(write_handle(owner, writer, "here", 4).value == 4, "relative write after rename");
    close_session(owner);
    require(read_file("moved/child/relative") == "here" &&
            read_file("Long parent folder/child/relative") == "<absent>", "old path cannot hijack cwd");
    no_objects();
    new_check("cwd_follows_ancestor_rename_and_sfn_alias");

    fresh();
    ok(mkdir_path(owner, "parent"), "cwd removal parent");
    ok(mkdir_path(owner, "parent/gone"), "cwd removal child");
    ok(named(op::cwd_set, "/parent/gone"), "cwd before rmdir");
    const u32 cwd_inode = named(op::stat, ".").reserved;
    ok(named(op::remove, "/parent/gone", allow_directory), "rmdir current directory");
    ok(named(op::remove, "/parent", allow_directory), "rmdir current directory parent");
    ok(mkdir_path(owner, "/parent"), "recreate removed parent");
    ok(mkdir_path(owner, "/parent/gone"), "recreate removed cwd");
    require(named(op::stat, ".").reserved == cwd_inode && named(op::stat, "/parent/gone").reserved != cwd_inode,
            "dot retains identity after path reuse");
    ok(named(op::cwd_set, ".."), "first deleted ancestor escape");
    require(call(owner, make_request(op::cwd_get)).status_code == static_cast<i32>(status::not_found), "deleted parent is still detached");
    ok(named(op::cwd_set, ".."), "second ancestor escape");
    require(cwd(owner) == "/", "escape reaches original root");
    no_objects();
    new_check("removed_cwd_and_parent_never_rebind");

    fresh();
    seed_file("pin", "image", 5);
    writer = opened("pin");
    require(open_path(owner, "pin", read_only | open_pin).status_code == static_cast<i32>(status::busy), "loader refuses existing writer");
    ok(close_handle(owner, writer), "writer before pin closes");
    reader = opened("pin", read_only | open_pin);
    require(open_path(owner, "pin", write_only).status_code == static_cast<i32>(status::busy), "pin prevents new writer");
    const u32 peer = opened("pin", read_only);
    ok(rename_path(owner, "pin", "renamed_pin"), "pin permits namespace move");
    require(handle_text(reader) == "image", "pin retains moved content");
    close_session(owner);
    no_objects();
    new_check("loader_pin_preserves_content_lease");

    fresh();
    ok(mkdir_path(owner, "forkdir"), "fork cwd directory");
    ok(named(op::cwd_set, "/forkdir"), "fork parent cwd");
    seed_file("forkdir/data", "abcdef", 6);
    reader = opened("data", read_only);
    kernel_sessions[1] = {20, 10, 101, 102};
    request clone = make_request(op::clone_session);
    clone.offset = 20;
    ok(call(owner, clone), "clone real descriptions and cwd");
    require(cwd(sessions[1]) == "/forkdir", "child cwd inherited");
    require(read_handle(sessions[1], reader, 2).length == 2 &&
            seek_handle(owner, reader, 0, seek_current).value == 2, "fork shares open description offset");
    ok(rename_path(owner, "/forkdir", "/fork_moved"), "rename shared cwd");
    require(cwd(owner) == "/fork_moved" && cwd(sessions[1]) == "/fork_moved", "both inherited cwd references follow rename");
    close_session(owner);
    require(read_handle(sessions[1], reader, 2).length == 2, "child survives parent session close");
    close_session(sessions[1]);
    no_objects();
    new_check("fork_shared_description_and_cwd_lifecycle");

    fresh();
    seed_file("saved", "old", 3);
    reader = opened("saved", read_only);
    const u32 old_saved_inode = fstat_handle(owner, reader).reserved;
    request begin = make_request(op::replace_begin);
    set_name(begin, "saved"); begin.length = 3;
    ok(call(owner, begin), "replace begin with open reader");
    request chunk = make_request(op::replace_chunk);
    chunk.length = 3; std::memcpy(chunk.data, "new", 3);
    ok(call(owner, chunk), "replace chunk");
    ok(call(owner, make_request(op::replace_commit)), "replace commit with open reader");
    require(handle_text(reader) == "old" && named(op::stat, "saved").reserved != old_saved_inode,
            "atomic save creates new inode while old reader stays old");
    ok(close_handle(owner, reader), "saved old reader close");
    require(read_file("saved") == "new", "saved new content");
    no_objects();
    new_check("atomic_save_with_open_old_inode");

    fresh();
    ok(mkdir_path(owner, "save_parent"), "staging parent");
    seed_file("save_parent/value", "old", 3);
    begin = make_request(op::replace_begin);
    set_name(begin, "save_parent/value"); begin.length = 3;
    ok(call(owner, begin), "begin before directory rename");
    ok(call(owner, chunk), "chunk before directory rename");
    ok(rename_path(owner, "save_parent", "save_moved"), "rename staging parent");
    ok(mkdir_path(owner, "save_parent"), "recreate old staging parent");
    seed_file("save_parent/value", "other", 5);
    ok(call(owner, make_request(op::replace_commit)), "commit follows parent object");
    require(read_file("save_moved/value") == "new" && read_file("save_parent/value") == "other",
            "staging path reuse cannot redirect commit");
    no_objects();
    new_check("atomic_save_retains_parent_identity");

    fresh();
    ok(mkdir_path(owner, "empty_save"), "empty staging parent");
    begin = make_request(op::replace_begin);
    set_name(begin, "empty_save/new"); begin.length = 0;
    ok(call(owner, begin), "empty begin");
    ok(named(op::remove, "empty_save", allow_directory), "remove referenced staging parent");
    ok(mkdir_path(owner, "empty_save"), "replace staging parent name");
    require(call(owner, make_request(op::replace_commit)).status_code == static_cast<i32>(status::not_found),
            "commit to removed parent fails");
    require(read_file("empty_save/new") == "<absent>" && !staging_active, "failed save cannot reach recreated parent");
    no_objects();
    new_check("atomic_save_removed_parent_fails_without_redirect");

    fresh();
    seed_file("nearfull", "keep", 4);
    writer = opened("nearfull");
    fill_disk(1);
    const u32 large_offset = fs.csize * 512u * 3u;
    ok(seek_handle(owner, writer, large_offset, seek_set), "near-full hole seek");
    require(write_handle(owner, writer, "x", 1).status_code == static_cast<i32>(status::no_space), "real near-full gap failure");
    require(fstat_handle(owner, writer).value == 4 && free_clusters() == 1 &&
            seek_handle(owner, writer, 0, seek_current).value == large_offset, "near-full write rolls allocation and length back");
    require(truncate_handle(owner, writer, large_offset).status_code == static_cast<i32>(status::no_space), "real near-full truncate failure");
    require(fstat_handle(owner, writer).value == 4 && free_clusters() == 1 && handle_text(writer) == "keep", "near-full truncate rollback content and allocation");
    close_session(owner);
    new_check("real_near_full_gap_and_truncate_rollback");

    fresh();
    seed_file("short", "keep", 4);
    writer = opened("short");
    const u32 cluster_bytes = fs.csize * 512u;
    ok(truncate_handle(owner, writer, cluster_bytes - 2), "prepare allocated cluster tail");
    fill_disk(0);
    ok(seek_handle(owner, writer, cluster_bytes - 2, seek_set), "seek full medium tail");
    const response partial = write_handle(owner, writer, "abcdefgh", 8);
    require(partial.status_code == 0 && partial.value == 2 && fstat_handle(owner, writer).value == cluster_bytes,
            "real full-medium write returns committed partial bytes");
    require(write_handle(owner, writer, "z", 1).status_code == static_cast<i32>(status::no_space), "real full-medium zero progress fails");
    begin = make_request(op::replace_begin);
    set_name(begin, "short"); begin.length = 1;
    require(call(owner, begin).status_code == static_cast<i32>(status::no_space) && !staging_active,
            "atomic save rejects lack of staging and journal space");
    close_session(owner);
    new_check("real_full_disk_short_write_and_save_space_gate");

    fresh();
    seed_file("held", "data", 4);
    writer = opened("held");
    seed_file("other", "other", 5);
    open_description* description = description_for(find_open(owner, writer));
    require(f_rename("held", "unlocked") == FR_LOCKED, "ordinary FatFs rename still enforces lock");
    require(f_rename_open(&file_for(*description), "other", "wrong") == FR_LOCKED, "extension rejects wrong FIL authority");
    ok(rename_path(owner, "held", "right"), "authorized sole FIL rename");
    close_session(owner);
    require(read_file("right") == "data" && read_file("other") == "other", "lock table relocation preserves objects");
    new_check("fatfs_lock_not_disabled_and_wrong_fil_rejected");

    fresh();
    seed_file("cleanup", "data", 4);
    writer = opened("cleanup");
    ok(named(op::remove, "cleanup"), "deferred cleanup unlink");
    unlink_fault = true;
    require(close_handle(owner, writer).status_code == static_cast<i32>(status::io), "last-close unlink failure is reported");
    retry_description_cleanup();
    no_objects();
    new_check("failed_deferred_delete_remains_owned_until_retry");

    fresh();
    ok(mkdir_path(owner, "restore_dir"), "directory recovery target");
    require(write_journal("restore_dir"), "directory recovery journal");
    require(f_rename("restore_dir", backup_name) == FR_OK, "directory recovery backup");
    recover();
    require(!recovery_failed && f_stat("restore_dir", &alias) == FR_OK && (alias.fattrib & AM_DIR) != 0,
            "recovery restores directory replacement backup");
    require(read_file(journal_name) == "<absent>", "directory recovery marker cleanup");
    new_check("directory_replacement_recovery");

    fresh();
    seed_file("XOS00001.TMP", "orphan", 6);
    require(f_mkdir("XOS00002.TMP") == FR_OK, "orphan empty directory");
    seed_file("ordinary", "keep", 4);
    recover_orphans();
    require(!recovery_failed && f_stat("XOS00001.TMP", &alias) == FR_NO_FILE &&
            f_stat("XOS00002.TMP", &alias) == FR_NO_FILE && read_file("ordinary") == "keep", "startup orphan cleanup is reserved-only");
    new_check("startup_reclaims_unlinked_backing_files_and_directories");

    fresh();
    ok(mkdir_path(owner, "Source long directory"), "long source directory");
    ok(mkdir_path(owner, "Source long directory/child"), "long source child");
    ok(mkdir_path(owner, "Target long directory"), "long target directory");
    require(f_stat("Source long directory", &alias) == FR_OK && alias.altname[0] != '\0', "source directory SFN");
    const std::string source_alias = alias.altname;
    require(f_stat("Target long directory", &alias) == FR_OK && alias.altname[0] != '\0', "target directory SFN");
    ok(named(op::cwd_set, alias.altname), "cwd target directory via SFN");
    require(rename_path(owner, ("/" + source_alias).c_str(), "/Source long directory/child/new").status_code ==
            static_cast<i32>(status::invalid), "SFN cannot hide source ancestor");
    ok(rename_path(owner, ("/" + source_alias).c_str(), "/Target long directory"), "directory replacement with SFN source");
    require(call(owner, make_request(op::cwd_get)).status_code == static_cast<i32>(status::not_found), "SFN cwd stays on replaced target");
    require(named(op::stat, "/Target long directory/child").status_code == 0, "directory alias source subtree moved");
    close_session(owner);
    no_objects();
    new_check("directory_replacement_and_ancestor_guard_with_sfn_aliases");

    fresh();
    seed_file("maintenance", "data", 4);
    disk_write_fault = true;
    require(open_path(owner, "maintenance", write_only | open_truncate).status_code ==
            static_cast<i32>(status::io), "failed truncate leaves owned FIL");
    require(cleanup_pending(), "failed close owns pending object");
    kernel_guard = {77, owner.pid};
    require(call(owner, make_request(op::maintenance_acquire)).status_code == static_cast<i32>(status::busy),
            "maintenance cannot pass pending object cleanup");
    disk_write_fault = false;
    retry_description_cleanup();
    ok(call(owner, make_request(op::maintenance_acquire)), "maintenance admitted after cleanup");
    sessions[1].pid = 77;
    ok(call(sessions[1], make_request(op::maintenance_release)), "maintenance released by owner");
    no_objects();
    new_check("maintenance_gate_keeps_failed_close_ownership");

    fresh();
    seed_file("XOS99999.TMP", "busy", 4);
    next_anonymous_serial = anonymous_serial_limit - 1;
    char hidden_name[13]{};
    require(anonymous_name(hidden_name) == status::ok &&
            std::strcmp(hidden_name, "XOS00000.TMP") == 0, "anonymous names wrap around collisions");
    new_check("anonymous_name_wrap_and_collision");

    std::printf("FILE_IDENTITY_CASES_PASSED=%d\n", checks);
    return 0;
}
