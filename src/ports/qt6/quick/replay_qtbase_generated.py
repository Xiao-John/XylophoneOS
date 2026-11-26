# SPDX-License-Identifier: Apache-2.0
"""Restore missing generated QtBase objects under an independent build directory."""

import json
import os
from pathlib import Path
import shlex
import subprocess

from audit_generated_members import cmake_setting, command_edges, sha_text
from relink import sha


class GeneratedReplay:
    def __init__(self, capture, build, output, expected_compiler):
        self.capture = capture
        self.build = build
        self.output = output
        self.expected_compiler = expected_compiler
        self.cmake = Path(cmake_setting(build, "CMAKE_COMMAND"))
        self.ninja = Path(cmake_setting(build, "CMAKE_MAKE_PROGRAM"))
        self.env = dict(os.environ, LC_ALL="C")
        self.number = 0
        output.mkdir(parents=True, exist_ok=False)

    def run_logged(self, args, cwd, log):
        result = subprocess.run(list(map(str, args)), cwd=cwd, env=self.env, timeout=90,
                                capture_output=True, check=False)
        with log.open("ab") as stream:
            stream.write(result.stdout)
            stream.write(result.stderr)
        result.check_returncode()

    def custom_command(self, original, copied, output_argument, log):
        entry = command_edges(self.build)[original.relative_to(self.build).as_posix()]
        tokens = shlex.split(entry["command"])
        if tokens[:1] != ["cd"] or tokens[2:3] != ["&&"] or "&&" in tokens[3:]:
            raise ValueError("Unsupported shape for a single archived generation command")
        working_directory = Path(tokens[1]).resolve(strict=True)
        if not working_directory.is_relative_to(self.build):
            raise ValueError("The original generation command has a different working directory")
        command = tokens[3:]
        if output_argument.endswith("="):
            index = command.index(output_argument + str(original))
            command[index] = output_argument + str(copied)
        else:
            index = command.index(output_argument) + 1
            if command[index] != str(original):
                raise ValueError("Archived generation command has a different output")
            command[index] = str(copied)
        self.run_logged(command, working_directory, log)
        return {"command_sha256": sha_text(entry["command"]), "generated": self.capture.input(copied),
                "inputs": [self.capture.input(self.build / name) for name in entry["inputs"]]}

    def automoc(self, generation, destination, new_source, log):
        metadata_location = generation["details"]["autogen_info"]["path"]
        metadata = self.build / metadata_location
        config = json.loads(metadata.read_text())
        config["BUILD_DIR"] = str(destination)
        for name in ("INCLUDE_DIR", "DEP_FILE", "MOC_COMPILATION_FILE", "MOC_PREDEFS_FILE",
                     "PARSE_CACHE_FILE", "SETTINGS_FILE"):
            if config.get(name):
                config[name] = str(destination / Path(config[name]).name)

        reconstructed = []
        for row in config["SOURCES"]:
            source = Path(row[0])
            if source == self.build / "src/corelib/.rcc/qmimeprovider_database.cpp" and not source.is_file():
                generated = destination / source.name
                reconstructed.append(self.custom_command(source, generated, "-DOUTPUT_FILE=", log))
                row[0] = str(generated)

        replay_config = destination / metadata.name
        replay_config.write_text(json.dumps(config) + "\n")
        cwd = self.build / Path(generation["source"]["path"]).parent.parent
        self.run_logged([self.cmake, "-E", "cmake_autogen", replay_config, "Release"], cwd, log)
        headers = {row[2]: Path(row[0]) for row in config["HEADERS"]}
        return {"replay_config": self.capture.input(replay_config),
                "selected_includes": self.capture.moc_includes(new_source, headers),
                "reconstructed_scan_inputs": reconstructed}

    def replay(self, member, generation):
        original = self.build / generation["source"]["path"]
        destination = self.output / str(self.number)
        self.number += 1
        destination.mkdir()
        source = destination / original.name
        obj = destination / member["name"]
        log = destination / "commands.log"
        log.touch()
        result = {}
        try:
            if generation["kind"] == "automoc":
                result.update(self.automoc(generation, destination, source, log))
            elif generation["kind"] == "rcc":
                result.update(self.custom_command(original, source, "--output", log))
            else:
                raise ValueError("No isolated replay for the missing translation unit kind")
            if "generated" not in result:
                result["generated"] = self.capture.input(source)
            invocation = subprocess.check_output([self.ninja, "-C", self.build, "-t", "commands", "-s",
                                                  member["build_object"]],
                                                 text=True, env=self.env, timeout=15).strip()
            command = shlex.split(invocation)
            compiler = Path(command[0]).resolve(strict=True)
            if compiler.name != "x86_64-elf-g++" or sha(compiler) != self.expected_compiler:
                raise ValueError("Archived compile command uses a different target compiler")
            for flag, path in (("-o", obj), ("-MF", destination / "object.d"), ("-c", source)):
                command[command.index(flag) + 1] = str(path)
            self.run_logged(command, self.build, log)
            result.update(compiler_sha256=sha(compiler), original_compile_command_sha256=sha_text(invocation),
                          ninja_sha256=sha(self.ninja), generated_object=self.capture.input(obj))
            result["status"] = ("byte_identical" if sha(obj) == member["member_sha256"] else "object_differs")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            with log.open("a") as stream:
                stream.write(type(error).__name__ + "\n")
            result["status"] = "command_failed"
        result["log_sha256"] = sha(log)
        return result
