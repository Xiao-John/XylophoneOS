// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include "HTMLInputStream.h"
#include "HTMLTokenizer.h"
#include <wtf/MainThread.h>
#include <array>
#include <cstdio>
#include <string_view>

static bool matches(const auto& item, std::u16string_view expected)
{
    return std::u16string_view(item.span().data(), item.size()) == expected;
}

int main(int argc, char** argv)
{
    if (argc != 2)
        return 64;
    FILE* input = std::fopen(argv[1], "rb");
    if (!input) {
        std::puts("WEBKIT_HTML_INPUT_MISSING");
        return 2;
    }
    std::array<char, 128> bytes{};
    const auto length = std::fread(bytes.data(), 1, bytes.size(), input);
    const bool complete = std::feof(input) && !std::ferror(input);
    std::fclose(input);
    const auto delimiter = std::string_view(bytes.data(), length).find("&nbsp;");
    if (!complete || delimiter == std::string_view::npos)
        return 65;
    const auto split = delimiter + 3;
    WTF::initializeMainThread();
    WebCore::HTMLInputStream stream;
    stream.appendToEnd(WebCore::SegmentedString(WTF::String::fromUTF8({bytes.data(), split})));
    stream.appendToEnd(WebCore::SegmentedString(WTF::String::fromUTF8({bytes.data() + split, length - split})));
    stream.markEndOfFile();
    WebCore::HTMLTokenizer tokenizer(WebCore::HTMLParserOptions{});
    using Type = WebCore::HTMLToken::Type;
    {
        auto token = tokenizer.nextToken(stream.current());
        if (!token || token->type() != Type::DOCTYPE || !matches(token->name(), u"html"))
            return 1;
    }
    {
        auto token = tokenizer.nextToken(stream.current());
        if (!token || token->type() != Type::StartTag || !matches(token->name(), u"p") || token->attributes().size() != 1)
            return 2;
        const auto& attr = token->attributes()[0];
        if (!matches(attr.name, u"data-k") || !matches(attr.value, u"A&B"))
            return 3;
    }
    {
        auto token = tokenizer.nextToken(stream.current());
        if (!token || token->type() != Type::Character || !matches(token->characters(), u"Hi\u00a0X"))
            return 4;
    }
    {
        auto token = tokenizer.nextToken(stream.current());
        if (!token || token->type() != Type::EndTag || !matches(token->name(), u"p"))
            return 5;
    }
    auto eof = tokenizer.nextToken(stream.current());
    if (!eof || eof->type() != Type::EndOfFile)
        return 6;
    puts("WEBKIT_HTML_TOKENIZER_PASS doctype=html tag=p attribute=data-k text_chars=4 eof=1");
    return 0;
}
