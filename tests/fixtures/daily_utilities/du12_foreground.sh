# SPDX-License-Identifier: Apache-2.0
set -e
PATH=/usr/bin
export PATH
mkdir -p /tmp/du_direct/staging
printf 'one\ntwo\nthree\n' > /tmp/du_direct/staging/input
ls /tmp/du_direct/staging
cat /tmp/du_direct/staging/input
cp /tmp/du_direct/staging/input /tmp/du_direct/copy
mv /tmp/du_direct/copy /tmp/du_direct/moved
head -n 2 /tmp/du_direct/moved
tail -n 2 /tmp/du_direct/moved
wc -lwc /tmp/du_direct/moved
basename /tmp/du_direct/moved
dirname /tmp/du_direct/moved
rm /tmp/du_direct/staging/input
rmdir /tmp/du_direct/staging
test ! -e /tmp/du_direct/staging
test ! -e /tmp/du_direct/copy
printf 'DU12_FOREGROUND_OK\n'
