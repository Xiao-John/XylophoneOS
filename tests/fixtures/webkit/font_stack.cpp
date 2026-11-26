// SPDX-License-Identifier: Apache-2.0
#include <ft2build.h>
#include FT_FREETYPE_H
#include <hb-ft.h>
#include <hb-icu.h>

#include <cstdio>

int main(int argc, char** argv)
{
    FT_Library library{};
    if (argc != 2 || FT_Init_FreeType(&library))
        return 1;
    FT_Face face{};
    if (FT_New_Face(library, argv[1], 0, &face) || FT_Set_Pixel_Sizes(face, 0, 24))
        return 2;

    auto* unicode = hb_icu_get_unicode_funcs();
    if (hb_unicode_script(unicode, 'A') != HB_SCRIPT_LATIN
        || hb_unicode_script(unicode, 0x0644) != HB_SCRIPT_ARABIC
        || hb_unicode_combining_class(unicode, 0x0301) != HB_UNICODE_COMBINING_CLASS_ABOVE)
        return 3;

    auto* font = hb_ft_font_create_referenced(face);
    auto* buffer = hb_buffer_create();
    hb_buffer_set_unicode_funcs(buffer, unicode);
    hb_buffer_add_utf8(buffer, "fi", -1, 0, -1);
    hb_buffer_guess_segment_properties(buffer);
    hb_shape(font, buffer, nullptr, 0);
    unsigned count{};
    const auto* glyphs = hb_buffer_get_glyph_infos(buffer, &count);
    const FT_UInt ligature = FT_Get_Char_Index(face, 0xfb01);
    if (count != 1 || !ligature || glyphs[0].codepoint != ligature
        || hb_buffer_get_glyph_positions(buffer, nullptr)[0].x_advance <= 0)
        return 4;
    if (FT_Load_Glyph(face, glyphs[0].codepoint, FT_LOAD_DEFAULT)
        || FT_Render_Glyph(face->glyph, FT_RENDER_MODE_NORMAL))
        return 5;
    const auto& bitmap = face->glyph->bitmap;
    unsigned ink = 0;
    if (bitmap.pixel_mode != FT_PIXEL_MODE_GRAY || bitmap.pitch <= 0
        || bitmap.width > static_cast<unsigned>(bitmap.pitch))
        return 6;
    for (unsigned row = 0; row < bitmap.rows; ++row) {
        for (unsigned column = 0; column < bitmap.width; ++column)
            ink += bitmap.buffer[row * static_cast<unsigned>(bitmap.pitch) + column] != 0;
    }
    if (!ink)
        return 7;
    std::printf("WEBKIT_FONT_STACK_PASS icu=3 ligature=%u bitmap=%ux%u ink=%u\n",
                ligature, bitmap.width, bitmap.rows, ink);
    hb_buffer_destroy(buffer);
    hb_font_destroy(font);
    FT_Done_Face(face);
    FT_Done_FreeType(library);
    return 0;
}
