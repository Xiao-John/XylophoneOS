#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify and resume one existing SDK draft without rebuilding or changing its assets."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from build_glibc_host_sdk import load, qualify_archive, sha


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def gh_json(endpoint, *arguments):
    return json.loads(subprocess.check_output(['gh', 'api', endpoint, *arguments], text=True))


def asset_names(tag):
    require(re.fullmatch(r'xos-sdk-glibc-preview-[0-9]+', tag), 'invalid SDK preview tag')
    return {tag + '-linux-x86_64.tar.zst', tag + '-sources.tar.zst',
            'package.json', 'qualification.json', 'SHA256SUMS'}


def release_snapshot(release, tag, *, draft=True):
    require(type(release['id']) is int and release['id'] > 0, 'invalid release ID')
    require(release['tag_name'] == tag and release['draft'] is draft and
            release['prerelease'] is True, 'unexpected prerelease identity or publication state')
    assets = release['assets']
    require(len(assets) == 5 and {a['name'] for a in assets} == asset_names(tag),
            'release must contain exactly the five SDK assets')
    for asset in assets:
        require(type(asset['id']) is int and asset['id'] > 0 and
                type(asset['size']) is int and asset['size'] > 0 and
                asset['state'] == 'uploaded' and
                re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest') or ''),
                'asset must have an uploaded state, size and API SHA-256')
    require(len({a['id'] for a in assets}) == 5, 'duplicate asset IDs')
    return {'id': release['id'], 'tag_name': tag, 'draft': draft, 'prerelease': True,
            'assets': sorted([{k: a[k] for k in ('id', 'name', 'size', 'state', 'digest')}
                              for a in assets], key=lambda a: a['name'])}


def tag_commit(repository, tag):
    ref = gh_json('repos/' + repository + '/git/ref/tags/' + tag)
    require(ref['ref'] == 'refs/tags/' + tag and ref['object']['type'] == 'commit' and
            re.fullmatch(r'[0-9a-f]{40}', ref['object']['sha']), 'expected an exact commit tag')
    return ref['object']['sha']


def workflow_commit():
    value = os.environ.get('GITHUB_SHA', '')
    require(re.fullmatch(r'[0-9a-f]{40}', value), 'GITHUB_SHA must identify the recovery workflow')
    return value


def verify_qualification(report, package):
    require(report['status'] == 'passed' and report['fresh_extraction_verified'] is True,
            'qualification did not pass a fresh extraction')
    for field in ('source_commit', 'profile_sha256', 'binding', 'system', 'archive', 'source_archive'):
        require(report[field] == package[field], 'qualification binding differs: ' + field)
    require(report['user_data_preserved'] is True and set(report['applications']) == {'c', 'cpp'},
            'qualification is missing the consumer applications or preserved user data')
    for name, marker in (('c', 'GLIBC_KIT_C_OK 2.44'),
                         ('cpp', 'GLIBC_KIT_CPP_OK vector thread exception')):
        app = report['applications'][name]
        require(type(app['guest_exit_code']) is int and app['guest_exit_code'] == 0 and app['marker'] == marker and
                len(app['resources_before']) == 3 and
                all(type(value) is int and value >= 0 for value in app['resources_before']) and
                app['resources_before'] == app['resources_after'], 'guest result differs: ' + name)


def verify_downloaded(directory, state):
    assets = directory / 'assets'
    require({p.name for p in assets.iterdir()} == asset_names(state['tag']), 'downloaded asset set differs')
    digests = {}
    for asset in state['release']['assets']:
        path = assets / asset['name']
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == asset['size'],
                'downloaded asset type or size differs: ' + asset['name'])
        digests[asset['name']] = sha(path)
        require('sha256:' + digests[asset['name']] == asset['digest'],
                'downloaded asset API digest differs: ' + asset['name'])
    sums = {}
    for line in (assets / 'SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([^/\\]+)', line)
        require(match is not None and match[2] not in sums, 'invalid or duplicate checksum entry')
        sums[match[2]] = match[1]
    require(sums == {name: digest for name, digest in digests.items() if name != 'SHA256SUMS'},
            'SHA256SUMS does not bind all four other assets')
    package, original = load(assets / 'package.json'), load(assets / 'qualification.json')
    require(package['tag'] == state['tag'] and package['source_commit'] == state['source_commit'],
            'package source differs from the existing tag')
    for field, name in (('archive', state['tag'] + '-linux-x86_64.tar.zst'),
                        ('source_archive', state['tag'] + '-sources.tar.zst')):
        require(package[field] == {'name': name, 'sha256': digests[name]},
                'package archive binding differs: ' + field)
    verify_qualification(original, package)
    return package


def download(repository, tag, directory):
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository), 'invalid repository')
    asset_names(tag)
    try:
        # No matching objects produces empty output; multiple matching objects
        # produce multiple JSON documents. Both are rejected by json.loads.
        candidate = gh_json('repos/' + repository + '/releases', '--paginate',
                            '--jq', '.[] | select(.tag_name == ' + json.dumps(tag) + ')')
    except json.JSONDecodeError as error:
        raise ValueError('expected exactly one existing release for this tag') from error
    release = release_snapshot(candidate, tag)
    state = {'schema': 1, 'repository': repository, 'tag': tag, 'release': release,
             'source_commit': tag_commit(repository, tag), 'validation_commit': workflow_commit()}
    directory.mkdir(parents=True, exist_ok=False)
    assets = directory / 'assets'
    assets.mkdir()
    for asset in release['assets']:
        with (assets / asset['name']).open('xb') as stream:
            subprocess.run(['gh', 'api', 'repos/' + repository + '/releases/assets/' + str(asset['id']),
                            '-H', 'Accept: application/octet-stream'], stdout=stream, check=True)
    verify_downloaded(directory, state)
    write_json(directory / 'download-receipt.json', state)
    print(json.dumps({'status': 'downloaded_and_verified', 'release_id': release['id'],
                      'source_commit': state['source_commit'], 'assets': release['assets']}, sort_keys=True))


def qualify(directory):
    require(not os.environ.get('GH_TOKEN') and not os.environ.get('GITHUB_TOKEN'),
            'consumer qualification must run without a GitHub token')
    state = load(directory / 'download-receipt.json')
    require(state['validation_commit'] == workflow_commit(), 'recovery workflow changed')
    package = verify_downloaded(directory, state)
    fresh_package, fresh = qualify_archive(directory / 'assets')
    require(fresh_package == package, 'package changed during consumer qualification')
    verify_qualification(fresh, package)
    verify_downloaded(directory, state)
    proof = {'schema': 1, 'status': 'passed', 'release_id': state['release']['id'],
             'source_commit': state['source_commit'], 'validation_commit': state['validation_commit'],
             'download_receipt_sha256': sha(directory / 'download-receipt.json'),
             'original_qualification_sha256': sha(directory / 'assets/qualification.json'),
             'qualification': fresh}
    write_json(directory / 'recovery-qualification.json', proof)
    print(json.dumps(proof, sort_keys=True))


def publish(directory):
    state = load(directory / 'download-receipt.json')
    proof = load(directory / 'recovery-qualification.json')
    require(state['validation_commit'] == workflow_commit() and
            proof['validation_commit'] == state['validation_commit'] and
            proof['release_id'] == state['release']['id'] and proof['status'] == 'passed' and
            proof['source_commit'] == state['source_commit'] and
            proof['download_receipt_sha256'] == sha(directory / 'download-receipt.json') and
            proof['original_qualification_sha256'] == sha(directory / 'assets/qualification.json'),
            'recovery proof does not bind these original assets and workflow')
    package = verify_downloaded(directory, state)
    verify_qualification(proof['qualification'], package)
    endpoint = 'repos/' + state['repository'] + '/releases/' + str(state['release']['id'])
    # Re-read the remote draft and ref after the complete consumer run. Asset
    # IDs, names, sizes, states and digests must still match the captured set.
    require(release_snapshot(gh_json(endpoint), state['tag']) == state['release'],
            'remote draft or assets changed during qualification')
    require(tag_commit(state['repository'], state['tag']) == state['source_commit'],
            'tag changed during qualification')
    released = gh_json(endpoint, '--method', 'PATCH', '-F', 'draft=false',
                       '-F', 'prerelease=true', '-f', 'make_latest=false')
    # GitHub does not offer an atomic transaction across the release, its
    # assets and the Git ref. Detect observed changes after PATCH as well;
    # a failed post-check must never be reported as a verified publication.
    require(release_snapshot(released, state['tag'], draft=False) ==
            {**state['release'], 'draft': False}, 'published release or assets differ')
    require(tag_commit(state['repository'], state['tag']) == state['source_commit'],
            'tag changed during publication')
    print(json.dumps({'status': 'published_existing_draft', 'release_id': released['id'],
                      'url': released['html_url'], 'source_commit': state['source_commit'],
                      'validation_commit': state['validation_commit'],
                      'assets': state['release']['assets']}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='command', required=True)
    get = sub.add_parser('download')
    get.add_argument('--repository', required=True)
    get.add_argument('--tag', required=True)
    for command in (get, sub.add_parser('qualify'), sub.add_parser('publish')):
        command.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.command == 'download':
        download(args.repository, args.tag, directory)
    elif args.command == 'qualify':
        qualify(directory)
    else:
        publish(directory)


if __name__ == '__main__':
    main()
