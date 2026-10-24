// SPDX-License-Identifier: Apache-2.0
#include "ff.h"

// XOS exposes visible ASCII paths. FAT long-name records are UTF-16 on disk;
// the minimal converter deliberately rejects non-ASCII API names rather than
// guessing an OEM encoding. Existing non-ASCII directory entries remain on disk.
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
