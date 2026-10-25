# SPDX-License-Identifier: Apache-2.0
all: left right
left: shared
	@printf 'left\n' >> /out/c3_diamond.txt
right: shared
	@printf 'right\n' >> /out/c3_diamond.txt
shared:
	@printf 'shared\n' >> /out/c3_diamond.txt
