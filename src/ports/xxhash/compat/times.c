/* newlib's clock() path resolves _times_r -> times(), while the frozen SDK
   exports only _times(); forward so clock()-using tools link unchanged. */
#include <sys/times.h>

clock_t _times(struct tms*);

clock_t times(struct tms* buffer) { return _times(buffer); }
