# SPDX-License-Identifier: Apache-2.0
"""Minimal PyYAML-compatible loader for Open Adventure's adventure.yaml.

This is not a general YAML implementation. It supports the constructs used by
the frozen Open Adventure 1.12 data file: indentation maps/sequences, !!omap,
!!null, flow sequences/maps, single/double quoted scalars, block scalars (|,
|-), and anchors/aliases. Unsupported syntax must raise, never guess.
"""


class YAMLError(Exception):
    pass


def safe_load(stream):
    if hasattr(stream, "read"):
        text = stream.read()
    else:
        text = str(stream)
    return _Parser(text).load()


class _Parser:
    def __init__(self, text):
        self.lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.index = 0
        self.anchors = {}

    def load(self):
        value = self._block(0)
        self._skip_empty()
        if self.index < len(self.lines):
            raise YAMLError("trailing content at line %d: %r" %
                            (self.index + 1, self.lines[self.index]))
        return value

    def _skip_empty(self):
        while self.index < len(self.lines):
            raw = self.lines[self.index]
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                self.index += 1
                continue
            return

    def _indent(self, raw):
        return len(raw) - len(raw.lstrip(" "))

    def _content(self, raw):
        text = self._strip_comment(raw.lstrip(" "))
        return text.rstrip()

    def _strip_comment(self, text):
        quote = None
        index = 0
        while index < len(text):
            ch = text[index]
            if quote == "'":
                if ch == "'":
                    if index + 1 < len(text) and text[index + 1] == "'":
                        index += 2
                        continue
                    quote = None
            elif quote == '"':
                if ch == "\\":
                    index += 2
                    continue
                if ch == '"':
                    quote = None
            elif ch in ("'", '"'):
                quote = ch
            elif ch == "#" and (index == 0 or text[index - 1].isspace()):
                return text[:index]
            index += 1
        return text

    def _block(self, indent):
        self._skip_empty()
        if self.index >= len(self.lines):
            return None
        raw = self.lines[self.index]
        if self._indent(raw) < indent:
            return None
        if self._indent(raw) != indent:
            raise YAMLError("bad indentation at line %d" % (self.index + 1))
        content = self._content(raw)
        if content == "-" or content.startswith("- "):
            return self._sequence(indent)
        return self._mapping(indent)

    def _mapping(self, indent):
        result = {}
        while True:
            self._skip_empty()
            if self.index >= len(self.lines):
                break
            raw = self.lines[self.index]
            if self._indent(raw) != indent:
                break
            content = self._content(raw)
            if content == "-" or content.startswith("- "):
                break
            key, rest = self._split_key(content)
            self.index += 1
            result[key] = self._value(rest, indent)
        return result

    def _sequence(self, indent):
        result = []
        while True:
            self._skip_empty()
            if self.index >= len(self.lines):
                break
            raw = self.lines[self.index]
            if self._indent(raw) != indent:
                break
            content = self._content(raw)
            if not (content == "-" or content.startswith("- ")):
                break
            rest = content[1:].strip()
            self.index += 1
            result.append(self._sequence_item(rest, indent))
        return result

    def _sequence_item(self, rest, indent):
        anchor = None
        if rest.startswith("&"):
            anchor, rest = self._take_anchor(rest)
            rest = rest.strip()
        if not rest:
            value = self._nested(indent)
        elif self._looks_like_key(rest):
            value = self._inline_map(rest, indent)
        else:
            value = self._value(rest, indent)
        if anchor:
            self.anchors[anchor] = value
        return value

    def _inline_map(self, rest, indent):
        key, tail = self._split_key(rest)
        result = {key: self._value(tail, indent)}
        self._skip_empty()
        if self.index < len(self.lines) and self._indent(self.lines[self.index]) > indent:
            extra_indent = self._indent(self.lines[self.index])
            extra = self._mapping(extra_indent)
            if not isinstance(extra, dict):
                raise YAMLError("sequence map continuation is not a mapping")
            result.update(extra)
        return result

    def _value(self, rest, parent_indent):
        anchor = None
        rest = rest.strip()
        if rest.startswith("&"):
            anchor, rest = self._take_anchor(rest)
            rest = rest.strip()
        if rest == "!!null" or rest == "null" or rest == "~":
            value = None
        elif rest == "!!omap":
            self._skip_empty()
            if self.index >= len(self.lines):
                value = []
            else:
                indent = self._indent(self.lines[self.index])
                if indent < parent_indent:
                    value = []
                else:
                    value = self._omap(self._block(indent))
        elif rest in ("|", "|-", ">", ">-"):
            value = self._block_scalar(parent_indent, rest)
        elif rest.startswith("!!"):
            raise YAMLError("unsupported tag %r" % rest)
        elif rest == "":
            value = self._nested_or_same_sequence(parent_indent)
        elif rest.startswith("[" ) or rest.startswith("{"):
            text = self._collect_flow(rest)
            value = _Flow(text, self.anchors).parse()
        else:
            value = self._scalar(rest)
        if anchor:
            self.anchors[anchor] = value
        return value

    def _nested_or_same_sequence(self, parent_indent):
        self._skip_empty()
        if self.index < len(self.lines):
            indent = self._indent(self.lines[self.index])
            content = self._content(self.lines[self.index])
            if indent == parent_indent and (content == "-" or content.startswith("- ")):
                return self._sequence(indent)
        return self._nested(parent_indent)

    def _nested(self, parent_indent):
        self._skip_empty()
        if self.index >= len(self.lines):
            return None
        indent = self._indent(self.lines[self.index])
        if indent <= parent_indent:
            return None
        content = self._content(self.lines[self.index])
        if content == "-" or content.startswith("- ") or self._looks_like_key(content):
            return self._block(indent)
        return self._plain_block(indent)

    def _plain_block(self, indent):
        collected = []
        min_indent = None
        while self.index < len(self.lines):
            raw = self.lines[self.index]
            if raw.strip() == "":
                collected.append("")
                self.index += 1
                continue
            current = self._indent(raw)
            if current < indent:
                break
            if min_indent is None or current < min_indent:
                min_indent = current
            collected.append(raw)
            self.index += 1
        if min_indent is None:
            return ""
        lines = ["" if raw == "" else raw[min_indent:].strip() for raw in collected]
        out = []
        for line in lines:
            if line == "":
                if out and out[-1] != "\n":
                    out.append("\n")
            else:
                if out and out[-1] not in ("", "\n"):
                    out.append(" ")
                out.append(line)
        return "".join(out).rstrip("\n")

    def _take_anchor(self, text):
        end = 1
        while end < len(text) and (text[end].isalnum() or text[end] == "_"):
            end += 1
        name = text[1:end]
        if not name:
            raise YAMLError("empty anchor")
        return name, text[end:]

    def _split_key(self, content):
        quote = None
        index = 0
        while index < len(content):
            ch = content[index]
            if quote == "'":
                if ch == "'":
                    if index + 1 < len(content) and content[index + 1] == "'":
                        index += 2
                        continue
                    quote = None
            elif quote == '"':
                if ch == "\\":
                    index += 2
                    continue
                if ch == '"':
                    quote = None
            elif ch in ("'", '"'):
                quote = ch
            elif ch == ":" and (index + 1 == len(content) or content[index + 1].isspace()):
                key = content[:index].strip()
                if key.startswith("'") or key.startswith('"'):
                    key = self._unquote(key)
                else:
                    key = self._key(self._unquote(key))
                return key, content[index + 1:].strip()
            index += 1
        raise YAMLError("expected 'key: value' in %r" % content)

    def _key(self, text):
        lowered = text.lower()
        if lowered in ("yes", "true", "on"):
            return True
        if lowered in ("no", "false", "off"):
            return False
        return text

    def _looks_like_key(self, content):
        try:
            self._split_key(content)
            return True
        except YAMLError:
            return False

    def _scalar(self, text):
        text = text.strip()
        if text == "":
            return None
        if text.startswith("*"):
            name = text[1:]
            if name not in self.anchors:
                raise YAMLError("unknown alias *%s" % name)
            return self.anchors[name]
        if text.startswith("'") or text.startswith('"'):
            return self._unquote(text)
        if text == "true":
            return True
        if text == "false":
            return False
        if text.lstrip("-").isdigit():
            return int(text)
        return text

    def _unquote(self, text):
        if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
            return text[1:-1].replace("''", "'")
        if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
            body = text[1:-1]
            out = []
            index = 0
            escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0"}
            while index < len(body):
                ch = body[index]
                if ch == "\\" and index + 1 < len(body):
                    nxt = body[index + 1]
                    out.append(escapes.get(nxt, nxt))
                    index += 2
                    continue
                out.append(ch)
                index += 1
            return "".join(out)
        return text

    def _collect_flow(self, first):
        text = first
        while not _balanced(text):
            if self.index >= len(self.lines):
                raise YAMLError("unterminated flow collection")
            text += " " + self._content(self.lines[self.index])
            self.index += 1
        return text

    def _block_scalar(self, parent_indent, marker):
        self._skip_empty()
        collected = []
        block_indent = None
        while self.index < len(self.lines):
            raw = self.lines[self.index]
            if raw.strip() == "":
                collected.append("")
                self.index += 1
                continue
            indent = self._indent(raw)
            if block_indent is None:
                block_indent = indent
            if indent < block_indent:
                break
            collected.append(raw)
            self.index += 1
        if block_indent is None:
            return ""
        lines = []
        for raw in collected:
            if raw == "":
                lines.append("")
            else:
                lines.append(raw[block_indent:])
        text = "\n".join(lines)
        if marker in ("|-", ">-"):
            text = text.rstrip("\n")
        elif not text.endswith("\n"):
            text += "\n"
        return text

    def _omap(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise YAMLError("!!omap must be a sequence")
        pairs = []
        for item in value:
            if not isinstance(item, dict) or len(item) != 1:
                raise YAMLError("!!omap entries must be single-key mappings")
            key = next(iter(item))
            pairs.append((key, item[key]))
        return pairs


def _balanced(text):
    depth = 0
    quote = None
    index = 0
    while index < len(text):
        ch = text[index]
        if quote == "'":
            if ch == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    index += 2
                    continue
                quote = None
        elif quote == '"':
            if ch == "\\":
                index += 2
                continue
            if ch == '"':
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        index += 1
    return depth == 0 and quote is None


class _Flow:
    def __init__(self, text, anchors):
        self.text = text
        self.index = 0
        self.anchors = anchors

    def parse(self):
        value = self._value()
        self._skip()
        if self.index != len(self.text):
            raise YAMLError("trailing flow content: %r" % self.text[self.index:])
        return value

    def _skip(self):
        while self.index < len(self.text) and self.text[self.index].isspace():
            self.index += 1

    def _value(self):
        self._skip()
        if self.index >= len(self.text):
            raise YAMLError("unexpected end of flow")
        ch = self.text[self.index]
        if ch == "[":
            return self._list()
        if ch == "{":
            return self._map()
        if ch in ("'", '"'):
            return self._quoted()
        start = self.index
        while self.index < len(self.text) and self.text[self.index] not in ",]}:":
            self.index += 1
        return self._scalar(self.text[start:self.index].strip())

    def _scalar(self, text):
        if text == "!!null" or text in ("null", "~"):
            return None
        if text == "true":
            return True
        if text == "false":
            return False
        if text.lstrip("-").isdigit():
            return int(text)
        if text.startswith("*"):
            name = text[1:]
            if name not in self.anchors:
                raise YAMLError("unknown alias *%s" % name)
            return self.anchors[name]
        return text

    def _quoted(self):
        quote = self.text[self.index]
        self.index += 1
        out = []
        while self.index < len(self.text):
            ch = self.text[self.index]
            if quote == "'":
                if ch == "'":
                    if self.index + 1 < len(self.text) and self.text[self.index + 1] == "'":
                        out.append("'")
                        self.index += 2
                        continue
                    self.index += 1
                    return "".join(out)
                out.append(ch)
                self.index += 1
            else:
                if ch == "\\" and self.index + 1 < len(self.text):
                    nxt = self.text[self.index + 1]
                    out.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(nxt, nxt))
                    self.index += 2
                    continue
                if ch == '"':
                    self.index += 1
                    return "".join(out)
                out.append(ch)
                self.index += 1
        raise YAMLError("unterminated quoted scalar")

    def _list(self):
        self.index += 1
        result = []
        while True:
            self._skip()
            if self.index < len(self.text) and self.text[self.index] == "]":
                self.index += 1
                return result
            result.append(self._value())
            self._skip()
            if self.index < len(self.text) and self.text[self.index] == ",":
                self.index += 1
                continue
            if self.index < len(self.text) and self.text[self.index] == "]":
                self.index += 1
                return result
            raise YAMLError("expected ',' or ']' in flow list")

    def _map(self):
        self.index += 1
        result = {}
        while True:
            self._skip()
            if self.index < len(self.text) and self.text[self.index] == "}":
                self.index += 1
                return result
            key = self._value()
            if not isinstance(key, str):
                raise YAMLError("flow map key must be a string")
            self._skip()
            if self.index >= len(self.text) or self.text[self.index] != ":":
                raise YAMLError("expected ':' in flow map")
            self.index += 1
            result[key] = self._value()
            self._skip()
            if self.index < len(self.text) and self.text[self.index] == ",":
                self.index += 1
                continue
            if self.index < len(self.text) and self.text[self.index] == "}":
                self.index += 1
                return result
            raise YAMLError("expected ',' or '}' in flow map")
