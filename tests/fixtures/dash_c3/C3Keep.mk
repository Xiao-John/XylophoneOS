# SPDX-License-Identifier: Apache-2.0
all: bad good
bad:
	false
good:
	printf 'keep_independent\n' > /out/c3_kept.txt
