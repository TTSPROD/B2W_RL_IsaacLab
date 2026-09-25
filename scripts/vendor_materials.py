#!/usr/bin/env python3
"""Fetch pinned, selected upstream materials; verify Git blobs and SHA-256 offline."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/github-dns-bypass/scripts'))
import github_dns as net

net.resolve = lru_cache(maxsize=32)(net.resolve)
MANIFEST = ROOT / 'vendor/manifest.json'
SOURCES = [
    ('unitree_sdk2', 'unitreerobotics/unitree_sdk2', '07493e4b5b46ced303ffa6acb426b4c365c291f0', 'BSD-3-Clause', 'archive'),
    ('robot_lab', 'fan-ziqi/robot_lab', '09f6a9dfdf48f32f38bb851dfa3a7d44db32b270', 'Apache-2.0', 'raw'),
    ('rl_sar', 'fan-ziqi/rl_sar', '376d42c9b128f963ab08579762d5a216a976ce39', 'Apache-2.0', 'raw'),
    ('unitree_ros', 'unitreerobotics/unitree_ros', 'ccfc6fd8430a17ba3dacef9a1e2faf64ff3b0aee', 'BSD-3-Clause', 'raw'),
    ('unitree_mujoco', 'unitreerobotics/unitree_mujoco', '1eb6642e3f3fdfb7fb13a9794fd6a2dd93ea0e7d', 'BSD-3-Clause', 'raw'),
    ('unitree_ros2', 'unitreerobotics/unitree_ros2', '668d1ec5a05d1c38d3306bdca7d59f2ba3581a88', 'BSD-3-Clause', 'raw'),
]


def selected(name, path):
    if path in ('LICENSE', 'NOTICE', 'README.md', '.gitmodules'):
        return True
    if name == 'unitree_sdk2':
        return not path.startswith(('.github/', '.devcontainer/'))
    if name == 'robot_lab':
        return (path in ('VERSION', 'pyproject.toml') or path.startswith(('scripts/', 'source/robot_lab/robot_lab/', 'source/robot_lab/config/'))
                or path.startswith('source/robot_lab/data/Robots/unitree/b2w_description/')
                or path in ('source/robot_lab/setup.py', 'source/robot_lab/pyproject.toml'))
    if name == 'rl_sar':
        return path.startswith(('src/', 'policy/b2w/')) or path in ('build.sh', 'CMakeLists.txt')
    if name == 'unitree_ros':
        # The complete B2W mesh set already exists in robot_lab; do not duplicate 72MB meshes.
        return path in ('robots/b2w_description/urdf/b2w_description.urdf', 'robots/b2w_description/README.md', 'robots/b2w_description/package.xml')
    if name == 'unitree_mujoco':
        return (path.startswith(('unitree_robots/b2w/', 'simulate/', 'simulate_python/', 'example/', 'doc/'))
                or path in ('readme.md', 'readme_zh.md'))
    if name == 'unitree_ros2':
        # Preserve complete message/example packages so upstream CMake targets resolve.
        return (path.startswith(('cyclonedds_ws/', 'example/'))
                or path in ('setup.sh', 'setup_local.sh', 'setup_default.sh', 'CHANGELOG.md', 'version.txt'))
    return False


def safe_target(name, path):
    if not re.fullmatch(r'[a-z][a-z0-9_]*', name):
        raise ValueError('Unsafe source name: ' + name)
    relative = PurePosixPath(path)
    if relative.is_absolute() or '..' in relative.parts or '\\' in path or ':' in path:
        raise ValueError('Unsafe upstream path: ' + path)
    base = (ROOT / 'vendor' / name).resolve()
    if (ROOT / 'vendor').resolve() not in base.parents:
        raise ValueError('Source escapes vendor root')
    target = base.joinpath(*relative.parts).resolve()
    if base not in target.parents:
        raise ValueError('Path escapes vendor root')
    return target


def hashes(path):
    size = path.stat().st_size
    blob = hashlib.sha1(('blob %d\0' % size).encode())
    sha256 = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            blob.update(data)
            sha256.update(data)
    return size, blob.hexdigest(), sha256.hexdigest()


def json_url(url):
    conn, response, _ = net.open_download(url)
    try:
        return json.load(response)
    finally:
        conn.close()


def fetch_one(source, entry):
    name, repo, commit, _, _ = source
    target = safe_target(name, entry['path'])
    if not target.exists() or hashes(target)[:2] != (entry['size'], entry['sha']):
        net.download('https://raw.githubusercontent.com/%s/%s/%s' % (repo, commit, entry['path']), target, timeout=90)
    size, blob, sha256 = hashes(target)
    if size != entry['size'] or blob != entry['sha']:
        raise ValueError('Git blob mismatch: ' + str(target))
    return {'path': entry['path'], 'bytes': size, 'git_blob_sha1': blob, 'sha256': sha256}


def fetch():
    if MANIFEST.exists():
        raise SystemExit('Manifest already exists; use restore or verify. Deliberate upstream updates require a new lock review.')
    manifest = {'schema_version': 1, 'snapshot_date': '2026-09-25', 'sources': [],
                'reference_only': [{'repository': 'LauraMQuiros/b2w-rl', 'commit': 'ad82b971bf69a84170f027035c1e2e3bf97e4ef9', 'reason': 'No license found at this revision; source not redistributed.'}]}
    for source in SOURCES:
        name, repo, commit, license_name, transport = source
        metadata = json_url('https://api.github.com/repos/%s/commits/%s' % (repo, commit))
        if metadata['sha'] != commit:
            raise ValueError('Commit did not resolve exactly')
        # Always bind selection to the pinned commit's actual root tree. A local
        # stale cache must not silently change snapshot provenance.
        root_tree = metadata['commit']['tree']['sha']
        tree = json_url('https://api.github.com/repos/%s/git/trees/%s?recursive=1' % (repo, root_tree))
        if tree.get('sha') != root_tree:
            raise ValueError('Upstream root tree mismatch')
        if tree.get('truncated'):
            raise ValueError('Truncated upstream tree')
        entries = [e for e in tree['tree'] if e['type'] == 'blob' and selected(name, e['path'])]
        if not entries or not any(e['path'] == 'LICENSE' for e in entries):
            raise ValueError('No selected files or license')
        print('%s: %d files, %.1f MB' % (name, len(entries), sum(e['size'] for e in entries) / 1e6), flush=True)
        if transport == 'archive':
            archive = ROOT / '.cache' / (name + '-' + commit + '.tar.gz')
            if not archive.exists():
                net.download('https://codeload.github.com/%s/tar.gz/%s' % (repo, commit), archive, timeout=120)
            chosen = {e['path'] for e in entries}
            with tarfile.open(archive, 'r:gz') as tar:
                for member in tar:
                    parts = member.name.split('/', 1)
                    if len(parts) != 2 or parts[1] not in chosen:
                        continue
                    if member.issym():
                        # Git stores a symlink as its UTF-8 target text. Preserve
                        # those bytes portably; restore executable links at build time.
                        target = safe_target(name, parts[1])
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(member.linkname.encode('utf-8'))
                        continue
                    if not member.isfile():
                        raise ValueError('Selected archive member is not a regular file')
                    target = safe_target(name, parts[1])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as stream, target.open('wb') as output:
                        import shutil
                        shutil.copyfileobj(stream, output)
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(fetch_one, source, entry) for entry in entries]
            files = [f.result() for f in as_completed(futures)]
        modes = {e['path']: e['mode'] for e in entries}
        for item in files:
            item['upstream_mode'] = modes[item['path']]
        manifest['sources'].append({'name': name, 'repository': repo, 'commit': commit,
                                    'root_tree_sha': root_tree,
                                    'commit_date': metadata['commit']['committer']['date'],
                                    'license': license_name, 'selection': 'B2W-focused reference snapshot; see vendor/README.md',
                                    'files': sorted(files, key=lambda x: x['path'])})
        (ROOT / '.cache/vendor-progress.json').write_text(json.dumps(manifest, indent=2) + '\n')
    MANIFEST.parent.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    verify()


def verify(restore=False):
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    count = 0
    for source in manifest['sources']:
        for entry in source['files']:
            target = safe_target(source['name'], entry['path'])
            expected = (entry['bytes'], entry['git_blob_sha1'], entry['sha256'])
            if restore and (not target.exists() or hashes(target) != expected):
                url = 'https://raw.githubusercontent.com/%s/%s/%s' % (source['repository'], source['commit'], entry['path'])
                net.download(url, target, timeout=90, expected_sha256=entry['sha256'])
            if not target.is_file() or hashes(target) != expected:
                raise ValueError('Missing or modified vendor file: ' + str(target))
            count += 1
    print('Verified %d files from %d pinned sources.' % (count, len(manifest['sources'])))


def audit_provenance():
    """Independently bind every locked file to the real pinned Git tree."""
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    for source in manifest['sources']:
        metadata = json_url('https://api.github.com/repos/%s/commits/%s' % (source['repository'], source['commit']))
        if metadata['sha'] != source['commit']:
            raise ValueError('Commit mismatch')
        root_tree = metadata['commit']['tree']['sha']
        tree = json_url('https://api.github.com/repos/%s/git/trees/%s?recursive=1' % (source['repository'], root_tree))
        if tree.get('sha') != root_tree or tree.get('truncated'):
            raise ValueError('Invalid upstream tree')
        expected = {e['path']: (e['sha'], e['size'], e['mode']) for e in tree['tree']
                    if e['type'] == 'blob' and selected(source['name'], e['path'])}
        actual = {e['path']: (e['git_blob_sha1'], e['bytes'], e['upstream_mode']) for e in source['files']}
        if expected != actual:
            raise ValueError('Manifest differs from selected upstream tree: ' + source['name'])
        source['root_tree_sha'] = root_tree
        print('Provenance verified: ' + source['name'], flush=True)
    temporary = MANIFEST.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    temporary.replace(MANIFEST)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['fetch', 'verify', 'restore', 'audit-provenance'])
    args = parser.parse_args()
    if args.command == 'fetch':
        fetch()
    elif args.command == 'audit-provenance':
        audit_provenance()
    else:
        verify(restore=args.command == 'restore')
