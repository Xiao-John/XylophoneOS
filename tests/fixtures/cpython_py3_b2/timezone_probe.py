# SPDX-License-Identifier: Apache-2.0
"""Exercise real wall time, libc TZ parsing, and the IANA fallback database."""

from datetime import datetime, timezone
import os
import time

wall_ns = time.time_ns()
assert wall_ns > 1_790_000_000_000_000_000, wall_ns
assert abs(datetime.now(timezone.utc).timestamp() * 1_000_000_000 - wall_ns) < 2_000_000_000
before = time.monotonic_ns()
time.sleep(0.04)
assert time.monotonic_ns() > before

os.environ["TZ"] = "UTC0"
time.tzset()
assert time.localtime(0) == time.gmtime(0)
os.environ["TZ"] = "EST5EDT,M3.2.0/2,M11.1.0/2"
time.tzset()
assert (time.localtime(1_772_951_400).tm_hour,
        time.localtime(1_772_951_400).tm_isdst) == (1, 0)
assert (time.localtime(1_772_955_000).tm_hour,
        time.localtime(1_772_955_000).tm_isdst) == (3, 1)

from zoneinfo import ZoneInfo

new_york = ZoneInfo("America/New_York")
spring_before = datetime.fromtimestamp(1_772_951_400, timezone.utc).astimezone(new_york)
spring_after = datetime.fromtimestamp(1_772_955_000, timezone.utc).astimezone(new_york)
assert spring_before.utcoffset().total_seconds() == -5 * 3600, spring_before
assert spring_after.utcoffset().total_seconds() == -4 * 3600, spring_after
fold0 = datetime.fromtimestamp(1_793_511_000, timezone.utc).astimezone(new_york)
fold1 = datetime.fromtimestamp(1_793_514_600, timezone.utc).astimezone(new_york)
assert fold0.hour == fold1.hour == 1 and (fold0.fold, fold1.fold) == (0, 1)
assert fold0.utcoffset().total_seconds() == -4 * 3600
assert fold1.utcoffset().total_seconds() == -5 * 3600
print(f"PY3_B2_REALTIME_TZDATA_OK wall_ns={wall_ns}")
