// SPDX-License-Identifier: Apache-2.0
#include <fontconfig/fontconfig.h>
#include <stdio.h>
#include <string.h>

static int match_font(FcConfig *config, const char *expected_file)
{
    static const FcChar8 generic_family[] = "sans-serif";
    static const FcChar8 expected_family[] = "DejaVu Sans";
    FcPattern *query = FcPatternCreate();
    FcCharSet *coverage = FcCharSetCreate();
    FcPattern *match = NULL;
    int status = 6;

    if (query && coverage && FcCharSetAddChar(coverage, 0x03bb)
        && FcPatternAddString(query, FC_FAMILY, generic_family)
        && FcPatternAddCharSet(query, FC_CHARSET, coverage)
        && FcConfigSubstitute(config, query, FcMatchPattern)) {
        FcDefaultSubstitute(query);
        FcResult result;
        match = FcFontMatch(config, query, &result);
        if (match && result == FcResultMatch) {
            FcChar8 *family;
            FcChar8 *filename;
            FcCharSet *glyphs;
            if (FcPatternGetString(match, FC_FAMILY, 0, &family) == FcResultMatch
                && FcPatternGetString(match, FC_FILE, 0, &filename) == FcResultMatch
                && FcPatternGetCharSet(match, FC_CHARSET, 0, &glyphs) == FcResultMatch
                && !strcmp((const char *)family, (const char *)expected_family)
                && !strcmp((const char *)filename, expected_file)
                && FcCharSetHasChar(glyphs, 0x03bb)
                && !FcCharSetHasChar(glyphs, 0x10ffff)) {
                puts("XOS_FONTCONFIG_MATCH_PASS family=DejaVu_Sans alias=sans-serif glyph=03bb");
                status = 0;
            }
        }
    }
    if (match)
        FcPatternDestroy(match);
    if (query)
        FcPatternDestroy(query);
    if (coverage)
        FcCharSetDestroy(coverage);
    return status;
}

int main(int argc, char **argv)
{
    static const FcChar8 rules[] = "<?xml version=\"1.0\"?>"
        "<fontconfig><alias binding=\"strong\"><family>sans-serif</family>"
        "<prefer><family>DejaVu Sans</family></prefer></alias></fontconfig>";
    if (argc != 3)
        return 2;

    FcConfig *config = FcConfigCreate();
    if (!config)
        return 3;
    int status = 4;
    if (FcConfigParseAndLoadFromMemory(config, rules, FcTrue)
        && FcConfigAppFontAddDir(config, (const FcChar8 *)argv[1])) {
        const FcFontSet *fonts = FcConfigGetFonts(config, FcSetApplication);
        if (fonts && fonts->nfont == 0) {
            puts("XOS_FONTCONFIG_DIRECTORY_EMPTY");
            status = 5;
        } else if (fonts && fonts->nfont == 1) {
            status = match_font(config, argv[2]);
        }
    }
    FcConfigDestroy(config);
    return status;
}
