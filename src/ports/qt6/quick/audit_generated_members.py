# SPDX-License-Identifier: Apache-2.0
"""Inspect original Qt-generated translation units without running the generators."""

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import posixpath
import re
import shlex
import xml.etree.ElementTree as et

from audit_static_members import path_digest, source_declarations
from qt_rcc_object import embedded_resources


@lru_cache(maxsize=None)
def command_edges(build):
    edges = {}
    row = None
    for line in (build / "build.ninja").read_text().replace("$\n", "").splitlines():
        if line.startswith("build "):
            outputs, separator, body = line[6:].partition(": ")
            row = None
            if separator and body.startswith("CUSTOM_COMMAND "):
                tokens = body.split()[1:]
                marker = next((i for i, token in enumerate(tokens) if token in {"|", "||", "|@"}), len(tokens))
                row = {"inputs": tokens[:marker]}
                for output in outputs.split():
                    if output != "|" and not output.startswith("$"):
                        edges[output] = row
        elif row is not None and line.startswith("  COMMAND = "):
            row["command"] = line.removeprefix("  COMMAND = ")
        elif line and not line.startswith(" "):
            row = None
    return edges


def cmake_setting(build, key):
    return next(line.split("=", 1)[1] for line in (build / "CMakeCache.txt").read_text().splitlines()
                if line.startswith(key + ":"))


def declared_license(record):
    return any(record.get(key) for key in
               ("spdx_declarations", "component_notices", "reuse_annotations", "license_sidecar"))


def inputs_declare_license(inputs):
    return any(declared_license(item.get("declarations", {})) for item in inputs)


class GenerationAudit:
    def __init__(self, roots, host_files):
        self.roots = roots
        self.host = host_files
        self.tools = {}

    def input(self, path):
        path = path.resolve()
        for role, root in self.roots.items():
            if path.is_relative_to(root):
                record = {"root": role, "path": path.relative_to(root).as_posix(), "present": path.is_file()}
                if record["present"]:
                    record["sha256"] = path_digest(path)
                    record["bytes"] = path.stat().st_size
                    if role.endswith("_source"):
                        record["declarations"] = source_declarations(root, path)
                return record
        raise ValueError(f"Generation input is outside the supplied capture roots: {path.name}")

    def tool(self, name, path):
        if name == "cmake":
            record = {"name": name, "origin": "original_cmake_cache",
                      "sha256": path_digest(path), "bytes": path.stat().st_size}
        else:
            record = self.input(path)
            kit_root = {"qtbase_host": "host_qt", "qtdeclarative_host": "host_qml"}[record["root"]]
            kit_path = kit_root + "/" + record["path"]
            if record["sha256"] != self.host[kit_path]["sha256"]:
                raise ValueError(f"Original {name} differs from the kit host inventory")
            record["kit_path"] = kit_path
        if name in self.tools and self.tools[name] != record:
            raise ValueError(f"The capture uses more than one {name} binary")
        self.tools[name] = record
        return name

    def command(self, build, path, name):
        entry = command_edges(build)[path.relative_to(build).as_posix()]
        command = entry["command"]
        invocation = shlex.split(command)
        tool_path = next((Path(token) for token in invocation
                          if token.startswith("/") and Path(token).name == name), None)
        if tool_path is None:
            raise ValueError(f"No {name} invocation in the captured Ninja rule")
        inputs = [(build / token).resolve() for token in entry["inputs"]]
        return {"name": self.tool(name, tool_path),
                "command_sha256": sha_text(command)}, [value for value in inputs if value != tool_path.resolve()]

    def cmake_tool(self, build):
        return self.tool("cmake", Path(cmake_setting(build, "CMAKE_COMMAND")))

    def moc_includes(self, generated, headers):
        return [{"generated": self.input(generated.parent / include), "source": self.input(headers[include])}
                for include in re.findall(r'^\s*#\s*include\s+"([^"]+)"', generated.read_text(), re.M)]

    def automoc(self, build, generated):
        invocation, inputs = self.command(build, generated, "cmake")
        invocation["inputs"] = [self.input(path) for path in inputs]
        metadata_file = generated.parent.parent / "CMakeFiles" / (generated.parent.name + ".dir") / "AutogenInfo.json"
        metadata = json.loads(metadata_file.read_text())
        if Path(metadata["MOC_COMPILATION_FILE"]).resolve() != generated:
            raise ValueError("AUTOMOC output differs from the recorded build")
        inputs = {row[2]: Path(row[0]) for row in metadata["HEADERS"]}
        selected = self.moc_includes(generated, inputs) if generated.is_file() else []
        payload = {"driver": invocation, "moc": self.tool("moc", Path(metadata["QT_MOC_EXECUTABLE"])),
                   "autogen_info": self.input(metadata_file), "selected_includes": selected,
                   "parse_cache": self.input(Path(metadata["PARSE_CACHE_FILE"])),
                   "compiler_predefs": self.input(Path(metadata["MOC_PREDEFS_FILE"])),
                   "header_scan_candidates": len(inputs)}
        if not generated.is_file():
            payload["candidate_headers"] = [{**self.input(path), "planned_output": output}
                                            for output, path in sorted(inputs.items())]
            payload["candidate_sources"] = [self.input(Path(row[0])) for row in metadata["SOURCES"]]
        return payload

    def shader(self, build, path):
        rule = command_edges(build).get(path.relative_to(build).as_posix()) if path.is_relative_to(build) else None
        if rule is None:
            source = path.with_suffix("")
            if path.is_relative_to(build):
                return {"status": "producer_not_captured", "inputs": []}
            return {"status": "precompiled_upstream_resource", "inputs": [self.input(source)]}
        generator, declared = self.command(build, path, "qsb")
        depfile = path.with_name(path.name + ".d")
        if depfile.is_file():
            text = depfile.read_text().replace("\\\n", " ")
            _, separator, tail = text.partition(":")
            if not separator:
                raise ValueError("Invalid qsb dependency record")
            declared.extend((build / name).resolve() for name in shlex.split(tail))
        return {"status": "recorded_qsb_command", "producer": generator, "dependency_file": self.input(depfile),
                "inputs": [self.input(value) for value in dict.fromkeys(declared)]}

    def qmldir(self, build, root, generated, resource):
        module = root / generated.relative_to(build).parent.parent.parent
        macro = root / "src/qml/Qt6QmlMacros.cmake"
        template = root / "src/qml/Qt6qmldirTemplate.cmake.in"
        if "Qt6qmldirTemplate.cmake.in" not in macro.read_text() or not resource.read_text().startswith("module "):
            raise ValueError("The embedded qmldir does not match the Qt configure-time shape")
        return {"generator": self.cmake_tool(build), "inputs": [self.input(template), self.input(macro),
                                                                  self.input(module / "CMakeLists.txt")]}

    def rcc(self, build, root, generated, obj):
        invocation, inputs = self.command(build, generated, "rcc")
        qrcs = [path for path in inputs if path.suffix == ".qrc"]
        if len(qrcs) != 1:
            raise ValueError("Expected one qrc manifest for an archived rcc member")
        qrc = qrcs[0]
        embedded = embedded_resources(obj)
        resources = {}
        for group in et.parse(qrc).getroot().findall("qresource"):
            prefix = group.get("prefix", "/")
            if group.get("lang"):
                raise ValueError("A localized qrc requires a locale-aware resource map")
            for item in group.findall("file"):
                value = item.text.strip()
                alias = item.get("alias", value)
                name = posixpath.normpath("/" + prefix.lstrip("/") + "/" + alias.lstrip("/"))
                path = (qrc.parent / value).resolve()
                record = self.input(path)
                if (name in resources or name not in embedded or not record["present"]
                        or embedded[name]["sha256"] != record["sha256"] or embedded[name]["bytes"] != record["bytes"]):
                    raise ValueError(f"Original ELF resource bytes differ from qrc input: {name}")
                resource = {"input": record, "embedded": embedded[name]}
                if path.name.endswith((".qsb", ".qsb.mv2qsb")):
                    resource["shader"] = self.shader(build, path)
                elif path.name == "qmldir":
                    resource["qml_directory"] = self.qmldir(build, root, generated, path)
                derivation = resource.get("shader", resource.get("qml_directory", {}))
                if declared_license(record.get("declarations", {})):
                    resource["declaration_evidence"] = "direct_input"
                elif inputs_declare_license(derivation.get("inputs", [])):
                    resource["declaration_evidence"] = "generation_inputs"
                else:
                    resource["declaration_evidence"] = "unresolved"
                resources[name] = resource
        if resources.keys() != embedded.keys():
            raise ValueError("The qrc and archived ELF resource names differ")
        return {"generator": invocation, "qrc": self.input(qrc), "entries": resources}

    def plugin(self, build, root, generated, obj_path):
        module = root / generated.relative_to(build).parent
        template = root / "src/qml/Qt6QmlPluginTemplate.cpp.in"
        macro = root / "src/qml/Qt6QmlMacros.cmake"
        if "Qt6QmlPluginTemplate.cpp.in" not in macro.read_text():
            raise ValueError("The Qt QML CMake macro does not refer to the plugin template")
        text = generated.read_text()
        if not text.startswith("// This file is autogenerated by CMake."):
            raise ValueError("Expected an original configured Qt QML plugin source")
        intermediate = generated.with_name(generated.stem + "_in.cpp")
        configured = self.input(intermediate)
        if not configured["present"]:
            raise ValueError("The intermediate configured QML plugin source is missing")
        target = obj_path.split("CMakeFiles/", 1)[1].split(".dir/", 1)[0]
        moc_include, = re.findall(r'#include "([^"]+\.moc)"', text)
        moc_dir = generated.parent / (target + "_autogen")
        moc_config = generated.parent / "CMakeFiles" / (moc_dir.name + ".dir") / "AutogenInfo.json"
        meta = json.loads(moc_config.read_text())
        return {"cmake": self.cmake_tool(build), "template": self.input(template),
                "cmake_macro": self.input(macro), "module_configuration": self.input(module / "CMakeLists.txt"),
                "intermediate_source": configured, "moc": self.tool("moc", Path(meta["QT_MOC_EXECUTABLE"])),
                "moc_configuration": self.input(moc_config), "moc_include": self.input(moc_dir / "include" / moc_include)}

    def jpeg_copy(self, build, root, generated, obj_path):
        module = root / "src/3rdparty/libjpeg"
        variant = generated.stem[-3:] if generated.stem.endswith(("_12", "_16")) else ""
        original = module / "src" / (generated.stem.removesuffix(variant) + ".c")
        record = self.input(original)
        if path_digest(generated) != record["sha256"]:
            raise ValueError("CMake's archived JPEG source copy differs from the corresponding original")
        rows = (build / "build.ninja").read_text().splitlines()
        start = next(index for index, line in enumerate(rows) if line.startswith(f"build {obj_path}:"))
        definitions = next((line.strip().removeprefix("DEFINES = ") for line in rows[start + 1:start + 9]
                            if line.startswith("  DEFINES = ")), "")
        if variant and f"-DBITS_IN_JSAMPLE={variant[1:]}" not in definitions.split():
            raise ValueError("JPEG copy variant differs from the compiler definitions")
        return {"cmake": self.cmake_tool(build), "copyonly": self.input(module / "CMakeLists.txt"),
                "original": record, "jpeg_sample_bits": int(variant[1:]) if variant else 8}

    def generated(self, row, build, root, member):
        path = build / row["generated_source"]
        limit = []
        binding = self.input(path)
        result = {"source": binding, "unresolved": limit}
        if not binding["present"]:
            limit.append("generated_translation_unit_not_retained")
        if binding["present"] and row.get("generated_source_sha256", binding["sha256"]) != binding["sha256"]:
            raise ValueError("Retained generated source differs from its audited bytes")
        match path.name:
            case "mocs_compilation.cpp":
                result["kind"] = "automoc"
                result["details"] = self.automoc(build, path)
                if not binding["present"]:
                    limit.append("exact_automoc_header_selection_unavailable")
            case name if name.startswith("qrc_"):
                result["kind"] = "rcc"
                result["details"] = self.rcc(build, root, path, member)
            case name if name.endswith("_qmltyperegistrations.cpp"):
                result["kind"] = "qml_registration"
                invocation, listed = self.command(build, path, "qmltyperegistrar")
                result["details"] = {"generator": invocation, "inputs": [self.input(item) for item in listed]}
            case "qqmljsgrammar.cpp" | "qqmljsparser.cpp":
                result["kind"] = "qlalr_parser"
                invocation, listed = self.command(build, path, "qlalr")
                result["details"] = {"generator": invocation, "inputs": [self.input(item) for item in listed]}
            case name if name.endswith("Plugin.cpp") and binding["present"]:
                result["kind"] = "qml_plugin_template"
                result["details"] = self.plugin(build, root, path, row["build_object"])
            case _ if path.is_relative_to(build / "src/3rdparty/libjpeg"):
                result["kind"] = "jpeg_source_copy"
                result["details"] = self.jpeg_copy(build, root, path, row["build_object"])
            case _:
                result["kind"] = "unrecognized"
                limit.append("generation_recipe_not_traced")
        return result


def sha_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
