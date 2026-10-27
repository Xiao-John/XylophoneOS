// SPDX-License-Identifier: Apache-2.0
#include "ff.h"

// FatFs uses UTF-8 for API long names and UTF-16 on disk. The OEM converter
// only supports ASCII short aliases; non-ASCII OEM code pages are unsupported.
// Name comparisons fold ASCII only; no general Unicode case folding is claimed.
extern "C" WCHAR ff_oem2uni(WCHAR oem, WORD) {
    return oem >= 0x20 && oem <= 0x7e ? oem : 0;
}

extern "C" WCHAR ff_uni2oem(DWORD unicode, WORD) {
    return unicode >= 0x20 && unicode <= 0x7e ? static_cast<WCHAR>(unicode) : 0;
}

extern "C" DWORD ff_wtoupper(DWORD unicode) {
    if (unicode >= 'a' && unicode <= 'z') { return unicode - 'a' + 'A'; }
    return unicode;
}
