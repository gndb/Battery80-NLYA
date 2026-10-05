"""Read-only source-release audit. No imports from tools, devices, WMI or drivers."""
import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ('evidence/panel/', 'evidence/packaging/', 'evidence/ec/stage13/', '.build/', 'build/', 'dist/', '__pycache__/')
BAD_SUFFIX = {'.rom', '.bin', '.sys', '.dll', '.exe', '.zip', '.pem', '.key', '.log'}
ALLOWED_PNG = {'assets/preview-holding.png', 'assets/preview-error.png'}


def scan():
    problems, files, links = [], {}, 0
    if ROOT.lstat().st_file_attributes & 0x400:
        raise RuntimeError('Release root is a reparse point')
    def visit(directory):
        nonlocal links
        for p in sorted(directory.iterdir()):
            rel = p.relative_to(ROOT).as_posix()
            if p.name == '.git' or p.name == '__pycache__' or any(rel == d.rstrip('/') or rel.startswith(d) for d in RUNTIME):
                continue
            info = p.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_file_attributes & 0x400:
                problems.append('Reparse path: ' + rel)
                continue
            if p.is_dir():
                visit(p)
                continue
            if (p.suffix.lower() in BAD_SUFFIX and rel != 'drivers/inpoutx64.sys') or p.name.startswith('.env'):
                problems.append('Excluded private/binary material: ' + rel)
            if rel.startswith('reference/') or '.git' in p.parts or rel.startswith('archives/'):
                problems.append('Private or third-party tree: ' + rel)
            data = p.read_bytes()
            files[rel] = hashlib.sha256(data).hexdigest()
            if rel == 'drivers/inpoutx64.sys':
                if files[rel] != 'f8965fdce668692c3785afa3559159f9a18287bc0d53abb21902895a8ecf221b':
                    problems.append('Original signed driver hash mismatch')
                continue
            if rel in ALLOWED_PNG:
                if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                    problems.append('Invalid preview PNG: ' + rel)
                # Reject PNG ancillary text/EXIF metadata without modifying pixels.
                off = 8
                while off + 12 <= len(data):
                    n = int.from_bytes(data[off:off+4], 'big')
                    chunk = data[off+4:off+8]
                    if chunk in (b'tEXt', b'zTXt', b'iTXt', b'eXIf'):
                        problems.append('PNG metadata requires review: ' + rel)
                    off += n + 12
                continue
            try:
                text = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                problems.append('Unexpected non-text file: ' + rel)
                continue
            rules = {
                'private profile path': r'(?i)[a-z]:[\\/]Users[\\/][^\s"\']+',
                'email address': r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',
                'GitHub token': r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b',
                'OpenAI-like token': r'\bsk-[A-Za-z0-9_-]{20,}\b',
                'private key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                'MAC address': r'(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b',
            }
            for label, pattern in rules.items():
                if re.search(pattern, text) and not (label == 'email address' and rel.startswith('licenses/')):
                    problems.append(label + ': ' + rel)
            if p.suffix == '.py':
                try:
                    ast.parse(text, filename=rel)
                except SyntaxError as exc:
                    problems.append('Python syntax: ' + rel + ': ' + str(exc))
            if p.suffix == '.md':
                for match in re.finditer(r'!?\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))\)', text):
                    target = (match[1] or match[2]).split('#', 1)[0]
                    if not target or re.match(r'^[a-z]+:', target, re.I):
                        continue
                    links += 1
                    resolved = (p.parent / target).resolve()
                    if ROOT != resolved and ROOT not in resolved.parents:
                        problems.append('Link outside release: ' + rel + ' -> ' + target)
                    elif not resolved.exists():
                        problems.append('Missing local link: ' + rel + ' -> ' + target)
    visit(ROOT)
    return files, problems, links


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--audit-only', action='store_true', help='Preparation: scan without frozen SHA256 manifest')
    args = a.parse_args()
    files, problems, links = scan()
    if not args.audit_only:
        manifest = ROOT / 'SHA256SUMS.txt'
        if not manifest.exists():
            problems.append('Missing frozen SHA256SUMS.txt')
        else:
            expected = {}
            for line in manifest.read_text(encoding='utf-8').splitlines():
                sha, rel = line.split('  ', 1)
                path = PurePosixPath(rel)
                if path.is_absolute() or '..' in path.parts or ':' in rel or '\\' in rel or rel in expected:
                    problems.append('Unsafe or duplicate manifest path: ' + rel)
                expected[rel] = sha
            actual = {p: h for p, h in files.items() if p != 'SHA256SUMS.txt'}
            if set(expected) != set(actual):
                problems.append('Manifest file-set differs: ' + json.dumps(sorted(set(expected) ^ set(actual))))
            for rel in set(expected) & set(actual):
                if expected[rel] != actual[rel]:
                    problems.append('Changed release file: ' + rel)
    result = {'passed': not problems, 'scanned_files': len(files), 'local_links_checked': links,
              'problems': problems, 'audit_only': args.audit_only, 'hardware_calls': 0,
              'scope': 'Pattern-based public-content audit and integrity; not a guarantee against every secret'}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not problems else 2


if __name__ == '__main__':
    raise SystemExit(main())
