# SPDX-License-Identifier: Apache-2.0
set -e
mkdir -p /tmp/du/a
mkdir -p /tmp/du/中文
printf 'UTF8\n' > /tmp/du/中文/文件.txt
cat /tmp/du/中文/文件.txt > /tmp/du/unicode.txt
printf 'one\ntwo\nthree\n' > /tmp/du/a/data
printf 'hidden\n' > /tmp/du/a/.secret
ls /tmp/du/a > /tmp/du/ls.txt
ls -a /tmp/du/a > /tmp/du/all.txt
ls -A /tmp/du/a > /tmp/du/almost.txt
ls -d /tmp/du/a > /tmp/du/dir.txt
cat /tmp/du/a/data > /tmp/du/cat.txt
cp /tmp/du/a/data /tmp/du
mv /tmp/du/data /tmp/du/moved
head -n 2 /tmp/du/moved > /tmp/du/head.txt
tail -n 2 /tmp/du/moved > /tmp/du/tail.txt
printf 'a\nb\nc' | tail -n 2 > /tmp/du/tail_pipe.txt
printf 'a\nb\nc' | head -n 2 > /tmp/du/head_pipe.txt
wc -lwc /tmp/du/moved > /tmp/du/wc.txt
printf 'hello\n' | tee /tmp/du/tee.txt > /tmp/du/tee_out.txt
printf 'again\n' | tee -a /tmp/du/tee.txt > /tmp/du/tee_append_out.txt
basename /tmp/du/moved > /tmp/du/base.txt
dirname /tmp/du/moved > /tmp/du/parent.txt
cat /tests/binary.dat > /tmp/du/binary_copy.dat
head -n 2 /tests/binary.dat > /tmp/du/binary_head.dat
tail -n 1 /tests/binary.dat > /tmp/du/binary_tail.dat
wc -c /tests/binary.dat > /tmp/du/binary_wc.txt
head -n 0 /tmp/du/moved > /tmp/du/empty_head.txt
tail -n 0 /tmp/du/moved > /tmp/du/empty_tail.txt
tail -n 1 /tests/tail_limit.dat > /tmp/du/tail_limit.txt
if tail -n 1 /tests/tail_over_limit.dat > /tmp/du/tail_over_limit.txt 2>/dev/null; then echo TAIL_LIMIT_WRONG; exit 1; fi
printf 'alpha\nbeta\n' > /tmp/du/extra
head -n 1 /tmp/du/moved /tmp/du/extra > /tmp/du/multi_head.txt
tail -n 1 /tmp/du/moved /tmp/du/extra > /tmp/du/multi_tail.txt
wc -lc /tmp/du/moved /tmp/du/extra > /tmp/du/multi_wc.txt
basename '' > /tmp/du/empty_base.txt
basename /tmp/du/file.txt .txt > /tmp/du/suffix_base.txt
dirname //tmp/du/file.txt > /tmp/du/slashes_dir.txt
basename / > /tmp/du/root_base.txt
dirname / > /tmp/du/root_dir.txt
mkdir /tmp/du/keepdir
if rmdir /tmp/du/keepdir -z 2>/dev/null; then echo RMDIR_OPTION_WRONG; exit 1; fi
ls -d /tmp/du/keepdir > /tmp/du/keepdir.txt
rmdir /tmp/du/keepdir
rm -f /tmp/du/absent
if rm /tmp/du/a 2>/dev/null; then echo RM_DIR_WRONG; exit 1; fi
if mkdir -p /tmp/du/moved 2>/dev/null; then echo MKDIR_FILE_WRONG; exit 1; fi
if ls -R /tmp/du/a 2>/dev/null; then echo LS_OPTION_WRONG; exit 1; fi
if cp /tmp/du/moved /tmp/du/moved 2>/dev/null; then echo CP_SAME_WRONG; exit 1; fi
if tail -n -1 /tmp/du/moved 2>/dev/null; then echo TAIL_COUNT_WRONG; exit 1; fi
if wc -m /tmp/du/moved 2>/dev/null; then echo WC_OPTION_WRONG; exit 1; fi
if rmdir /tmp/du/a 2>/dev/null; then echo RMDIR_NONEMPTY_WRONG; exit 1; fi
if cat /tmp/du/absent 2>/dev/null; then echo CAT_MISSING_WRONG; exit 1; fi
if head -z 2>/dev/null; then echo HEAD_OPTION_WRONG; exit 1; fi
if tee -z 2>/dev/null; then echo TEE_OPTION_WRONG; exit 1; fi
if mkdir -z 2>/dev/null; then echo MKDIR_OPTION_WRONG; exit 1; fi
if mv -z 2>/dev/null; then echo MV_OPTION_WRONG; exit 1; fi
if cp -z 2>/dev/null; then echo CP_OPTION_WRONG; exit 1; fi
if rm -r /tmp/du/a 2>/dev/null; then echo RM_OPTION_WRONG; exit 1; fi
if rmdir -p /tmp/du/a 2>/dev/null; then echo RMDIR_OPTION_WRONG; exit 1; fi
rm /tmp/du/a/data /tmp/du/a/.secret
rmdir /tmp/du/a
rm /tmp/du/中文/文件.txt
rmdir /tmp/du/中文
printf 'DU12_OK\n'
