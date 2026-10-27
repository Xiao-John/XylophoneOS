# SPDX-License-Identifier: Apache-2.0
set -e
mkdir -p /tmp/du/a
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
if rm /tmp/du/a 2>/dev/null; then echo RM_DIR_WRONG; exit 1; fi
if mkdir -p /tmp/du/moved 2>/dev/null; then echo MKDIR_FILE_WRONG; exit 1; fi
if ls -R /tmp/du/a 2>/dev/null; then echo LS_OPTION_WRONG; exit 1; fi
if cp /tmp/du/moved /tmp/du/moved 2>/dev/null; then echo CP_SAME_WRONG; exit 1; fi
if tail -n -1 /tmp/du/moved 2>/dev/null; then echo TAIL_COUNT_WRONG; exit 1; fi
if wc -m /tmp/du/moved 2>/dev/null; then echo WC_OPTION_WRONG; exit 1; fi
rm /tmp/du/a/data /tmp/du/a/.secret
rmdir /tmp/du/a
printf 'DU12_OK\n'
