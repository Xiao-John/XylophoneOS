# SPDX-License-Identifier: Apache-2.0
include /tests/C3Config.mk
all: /tests/C3Config.mk
	@printf '%s:%s:%s:%s\n' '$(MESSAGE)' '$@' '$<' "$$0" > /out/c3_macros.txt
