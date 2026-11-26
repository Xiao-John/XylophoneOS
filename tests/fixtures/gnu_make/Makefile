include /work/vars.mk

.PHONY: all left right common wildcard concurrent first second pipe capture broken survivor
.DELETE_ON_ERROR:

all: left right
	@printf 'GNU_MAKE_DEPS_OK %s\n' '$(WORD)';

left right: common
	@printf 'GNU_MAKE_TARGET %s\n' '$@';

common:
	@/usr/bin/mkprobe append /out/common

wildcard:
	@printf 'GNU_MAKE_WILDCARD <%s>\n' '$(wildcard /work/*.mk)';

concurrent: first second
	@echo GNU_MAKE_PARALLEL_OK;

first:
	@/usr/bin/mkprobe peer /out/first /out/second

second:
	@/usr/bin/mkprobe peer /out/second /out/first

pipe:
	@/usr/bin/mkprobe emit | /usr/bin/mkprobe verify

capture:
	@printf 'GNU_MAKE_CAPTURE <%s>\n' '$(shell /usr/bin/mkprobe emit)';

broken: /out/incomplete

/out/incomplete:
	@/usr/bin/mkprobe fail $@

survivor:
	@echo GNU_MAKE_SURVIVOR_OK;
