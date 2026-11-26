// SPDX-License-Identifier: Apache-2.0
#include <libxml/parser.h>
#include <libxml/xmlstring.h>

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

struct page_events {
    unsigned starts;
    unsigned ends;
    bool wrong_element;
    char text[16];
    size_t text_size;
};

static bool is_page_namespace(const xmlChar *uri) {
    return xmlStrEqual(uri, BAD_CAST "urn:clarke:page");
}

static void start_element(void *context, const xmlChar *name, const xmlChar *prefix,
                          const xmlChar *uri, int namespace_count, const xmlChar **namespaces,
                          int attribute_count, int defaulted_count, const xmlChar **attributes) {
    struct page_events *events = context;
    if (events->starts == 0) {
        events->wrong_element |= !xmlStrEqual(name, BAD_CAST "page") || namespace_count != 1 ||
            namespaces[0] != NULL || !is_page_namespace(namespaces[1]) || attribute_count != 0;
    } else if (events->starts == 1) {
        events->wrong_element |= !xmlStrEqual(name, BAD_CAST "label") || namespace_count != 0 ||
            attribute_count != 1 || !xmlStrEqual(attributes[0], BAD_CAST "id") ||
            attributes[4] - attributes[3] != 6 || memcmp(attributes[3], "sample", 6) != 0;
    } else {
        events->wrong_element = true;
    }
    events->wrong_element |= prefix != NULL || defaulted_count != 0 || !is_page_namespace(uri);
    ++events->starts;
}

static void end_element(void *context, const xmlChar *name, const xmlChar *prefix, const xmlChar *uri) {
    struct page_events *events = context;
    const xmlChar *expected = events->ends == 0 ? BAD_CAST "label" : BAD_CAST "page";
    events->wrong_element |= prefix != NULL || !xmlStrEqual(name, expected) || !is_page_namespace(uri);
    ++events->ends;
}

static void record_text(void *context, const xmlChar *bytes, int count) {
    struct page_events *events = context;
    if (count < 0 || (size_t)count > sizeof(events->text) - events->text_size) {
        events->wrong_element = true;
        return;
    }
    memcpy(events->text + events->text_size, bytes, (size_t)count);
    events->text_size += (size_t)count;
}

int main(int argc, char **argv) {
    bool malformed = argc == 2 && strcmp(argv[1], "malformed") == 0;
    if ((!malformed && argc != 1) || argc > 2)
        return 64;
    const char first[] = "<page xmlns='urn:clarke:page'><label id='sample'>h\xc3";
    const char second[] = "\xa9llo&amp;XOS</label>";
    const char *end = malformed ? "</wrong>" : "</page>";
    const char expected[] = "h\xc3\xa9llo&XOS";

    struct page_events events = {0};
    xmlSAXHandler handler = {.initialized = XML_SAX2_MAGIC, .startElementNs = start_element,
                             .endElementNs = end_element, .characters = record_text};
    xmlParserCtxtPtr parser = xmlCreatePushParserCtxt(&handler, &events, NULL, 0, NULL);
    if (!parser)
        return 70;
    int status = xmlCtxtUseOptions(parser, XML_PARSE_NONET | XML_PARSE_NO_XXE);
    if (status == 0)
        status = xmlParseChunk(parser, first, (int)sizeof(first) - 1, 0);
    if (status == 0)
        status = xmlParseChunk(parser, second, (int)sizeof(second) - 1, 0);
    if (status == 0)
        status = xmlParseChunk(parser, end, (int)strlen(end), 1);
    xmlFreeParserCtxt(parser);
    xmlCleanupParser();
    if (malformed && status == XML_ERR_TAG_NAME_MISMATCH) {
        puts("WEBKIT_XML_PUSH_REJECTED mismatched_close");
        return 2;
    }
    if (malformed || status != 0 || events.wrong_element || events.starts != 2 || events.ends != 2 ||
        events.text_size != sizeof(expected) - 1 || memcmp(events.text, expected, events.text_size) != 0)
        return 1;
    puts("WEBKIT_XML_PUSH_PASS starts=2 ends=2 utf8_bytes=10");
    return 0;
}
