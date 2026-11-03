# SPDX-License-Identifier: Apache-2.0
"""Check registered notice materials and exact SDK copies; not a legal/member audit."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def load_open_items():
    """Single register of open license items; the audit output derives from it."""
    data=json.loads((ROOT/'licenses/open_items.json').read_text())
    if data.get('version')!=1 or not isinstance(data.get('items'),list):
        raise SystemExit('licenses/open_items.json: expected version 1 with items[]')
    statuses=set(data.get('statuses',{}))
    listing=[]
    for item in data['items']:
        ident=item.get('id','<no id>')
        for field in ('id','status','scope','summary','evidence'):
            if not item.get(field):raise SystemExit(f'open_items: {ident} missing {field}')
        if item['status'] not in statuses:
            raise SystemExit(f'open_items: {ident} has unknown status {item["status"]!r}')
        if item['status']=='open' and not item.get('exit_condition'):
            raise SystemExit(f'open_items: {ident} is open but has no exit_condition')
        if item['status']=='deferred' and not (item.get('trigger') or item.get('exit_condition')):
            raise SystemExit(f'open_items: {ident} is deferred but names no trigger')
        if item['status']=='not_applicable' and not item.get('reason'):
            raise SystemExit(f'open_items: {ident} is not_applicable but has no reason')
        evidence=ROOT/item['evidence']
        if not evidence.exists():raise SystemExit(f'open_items: {ident} evidence missing: {item["evidence"]}')
        if evidence.is_dir() and item['evidence'].startswith('docs/reports/') and not (evidence/'manifest.json').is_file():
            raise SystemExit(f'open_items: {ident} evidence lacks flat manifest.json: {item["evidence"]}')
        listing.append({k:item[k] for k in ('id','status','scope','evidence')})
    return listing

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,default=ROOT/'build')
    args=parser.parse_args()
    build=args.build.resolve(strict=True); sdk=build/'sdk'
    manifest=json.loads((sdk/'manifest.json').read_text())
    components=json.loads((ROOT/'licenses/components.json').read_text())
    component_sources={}
    checked={}
    for relative,digest in manifest['licenses'].items():
        artifact=sdk/relative
        if sha(artifact)!=digest:raise SystemExit(f'SDK license hash mismatch: {relative}')
        source=ROOT/relative if relative not in ('licenses/newlib.txt',) else ROOT/'src/third_party/newlib/COPYING.NEWLIB'
        if sha(source)!=digest:raise SystemExit(f'SDK source notice mismatch: {relative}')
        checked[relative]=digest
    required={'LICENSE','NOTICE','licenses/mit_legacy.txt','licenses/legacy_mit_files.json',
              'licenses/fatfs.txt','licenses/newlib.txt','licenses/components.json'}
    if not required<=checked.keys():raise SystemExit('Missing required SDK notices')
    for component in components['components']:
        for relative in component.get('notices',[]):
            if not (ROOT/relative).is_file():raise SystemExit(f'Missing registered notice: {relative}')
        for relative,digest in component.get('artifact_sha256',{}).items():
            if sha(ROOT/relative)!=digest:raise SystemExit(f'Registered component changed: {relative}')
        for relative,identifier in component.get('source_files',{}).items():
            if relative in component_sources:raise SystemExit(f'Duplicate registered component source: {relative}')
            source=ROOT/relative
            if not source.is_file():raise SystemExit(f'Missing registered component source: {relative}')
            if f'SPDX-License-Identifier: {identifier}' not in source.read_text():
                raise SystemExit(f'Component source SPDX mismatch: {relative}')
            component_sources[relative]=identifier
        for relative, provenance in component.get('vendored_source_files', {}).items():
            if relative in component_sources: raise SystemExit(f'Duplicate registered component source: {relative}')
            source=ROOT/relative
            upstream=Path(component['path'])/'upstream'
            if not Path(relative).is_relative_to(upstream) or not source.is_file():
                raise SystemExit(f'Vendored source is not an existing upstream file: {relative}')
            if hashlib.sha256(source.read_bytes()).hexdigest()!=provenance['sha256']:
                raise SystemExit(f'Vendored source SHA mismatch: {relative}')
            if provenance['notice'] not in component['notices'] or not (ROOT/provenance['notice']).is_file():
                raise SystemExit(f'Vendored source lacks its registered notice: {relative}')
            if provenance['license'] not in ('MIT',):
                raise SystemExit(f'Unreviewed vendored source declaration: {relative}')
            component_sources[relative]=provenance['license']
    legacy=set(json.loads((ROOT/'licenses/legacy_mit_files.json').read_text())['files'])
    built=json.loads((build/'manifest.json').read_text())
    new_sources=[]
    for relative in built['sources']:
        if relative.startswith(('src/third_party/','licenses/')) or relative in legacy:continue
        if Path(relative).suffix not in ('.cpp','.hpp','.py','.asm','.c','.h','.s','.sh','.ld'):continue
        if relative in component_sources:
            new_sources.append(relative)
            continue
        if 'SPDX-License-Identifier: Apache-2.0' not in (ROOT/relative).read_text():
            raise SystemExit(f'New source missing Apache-2.0 identifier: {relative}')
        new_sources.append(relative)
    listing=load_open_items()
    active=[item['id'] for item in listing if item['status']=='open']
    report={'build_id' :manifest['build_id'],'status':'passed','scope':'registered_materials_and_sdk_copies',
            'files':checked,'new_sources':new_sources,'not_completed':active,
            'open_items':listing,
            'open_items_register':'licenses/open_items.json',
            'review_reports':{
                'newlib_member_mapping':'docs/reports/newlib_member_license_20261103/',
                'gnu_seed_distribution_review':'docs/reports/gnu_seed_distribution_20261103/',
                'qt_static_distribution_review':'docs/reports/qt_static_distribution_20261103/'},
            'review_limits':['member mapping is declaration extraction, not a legal opinion',
                             'qt static redistribution remains NOT_GRANTED (see review report)',
                             'archive member provenance is derived until docs/contracts/archive_member_provenance.md takes effect']}
    (build/'license_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"PASS: {len(checked)} license materials | build {manifest['build_id']} | "
          f"open license items: {len(active)} -> {', '.join(active) if active else 'none'} "
          f"(register: licenses/open_items.json)")
if __name__=='__main__':main()
