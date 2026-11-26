# Fontconfig on XOS

This target builds upstream Fontconfig with the XOS native glibc SDK, the WebCore
FreeType archive and target LibXml2. The build host supplies GNU gperf. The source
and COPYING hashes are pinned to the [upstream release and checksum](https://www.freedesktop.org/software/fontconfig/release/).

```sh
python3 src/ports/webkit/fontconfig/build_target.py \
  --archive "$FONTCONFIG_ARCHIVE" --sdk-build "$GLIBC_SDK" \
  --font-target "$WEBKIT_FONT_TARGET" --xml-target "$WEBKIT_XML_TARGET" \
  --output "$FONTCONFIG_TARGET"
python3 tests/webkit_fontconfig_guest.py --system "$SYSTEM" \
  --target "$FONTCONFIG_TARGET" --font-target "$WEBKIT_FONT_TARGET" \
  --output "$FONTCONFIG_GUEST"
```

The target installs the static archive, public headers and upstream COPYING in
its output prefix. The guest gate parses explicit XML aliases, reads fonts from a
FAT directory using the real file service, selects a font for a Unicode character,
and checks the empty-directory case and resource counts. It uses an application
configuration and supplies no global font configuration or persistent cache.

The WebCore font backend still needs to link and run against the archive. Page
layout, software painting and Qt viewport delivery each have their own guest gate.
