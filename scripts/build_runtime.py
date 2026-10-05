"""Build a fresh onedir bundle. Never loads a driver or runs the live panel."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools'))
from portable_runtime import safe_path, verify_policy_record

def main():
    if sys.platform != 'win32' or sys.maxsize <= 2**32:
        raise RuntimeError('Use Windows x64 Python 3.12 with Tk')
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Python 3.12 is required')
    verify_policy_record()
    driver = safe_path(root / 'drivers/inpoutx64.sys')
    if hashlib.sha256(driver.read_bytes()).hexdigest() != 'f8965fdce668692c3785afa3559159f9a18287bc0d53abb21902895a8ecf221b':
        raise RuntimeError('Original driver hash mismatch')
    base = safe_path(root / '.build')
    if base.exists(): raise RuntimeError('Existing .build retained; use a fresh source checkout')
    base.mkdir()
    for folder in ('temp','cache','deps','pyinstaller-cache'): (base/folder).mkdir()
    env = os.environ.copy()
    env.update(TEMP=str(base/'temp'),TMP=str(base/'temp'),PYTHONNOUSERSITE='1',
        PYTHONDONTWRITEBYTECODE='1',PIP_CACHE_DIR=str(base/'cache'),PIP_CONFIG_FILE=os.devnull,
        PIP_DISABLE_PIP_VERSION_CHECK='1',PYINSTALLER_CONFIG_DIR=str(base/'pyinstaller-cache'))
    subprocess.run([sys.executable,'-B','-m','pip','install','--only-binary=:all:',
        '--require-hashes','--no-compile','--target',str(base/'deps'),
        '-r',str(root/'build-requirements.txt')],cwd=root,env=env,check=True)
    env['PYTHONPATH'] = str(base/'deps')
    subprocess.run([sys.executable,'-B','-m','PyInstaller','--onedir','--windowed','--noupx',
        '--name','BatteryPanel','--paths',str(root/'tools'),'--add-data',
        str(root/'assets/verified-policy.json')+';assets','--distpath',str(base/'dist'),
        '--workpath',str(base/'work'),'--specpath',str(base),str(root/'portable_entry.py')],
        cwd=root,env=env,check=True)
    bundle = base/'dist/BatteryPanel'
    for folder in ('drivers','licenses','docs'):
        shutil.copytree(root/folder,bundle/folder)
    (bundle/'evidence').mkdir()
    for name in ('README.md','README.en.md','LICENSE_STATUS.md','THIRD_PARTY_NOTICES.md','CHANGELOG.md','VERSION','PACKAGING_REVISION','RELEASE_NOTES.md'):
        shutil.copy2(root/name,bundle/name)
    (bundle/'assets').mkdir()
    for image in (root/'assets').glob('*.png'):
        shutil.copy2(image,bundle/'assets'/image.name)
    (bundle/'RELEASE_VALIDATION.json').write_text(json.dumps({
        'application_version':(root/'VERSION').read_text().strip(),
        'local_rebuild_untested':True,'hardware_calls_during_build':0,
        'driver_loads_during_build':0,
        'scope':'Published validation documents describe the earlier release; this rebuilt executable requires its own verification.'
    },indent=2)+'\n',encoding='utf-8')
    lines = []
    for item in sorted(bundle.rglob('*')):
        if item.is_file():
            lines.append(hashlib.sha256(item.read_bytes()).hexdigest()+'  '+item.relative_to(bundle).as_posix())
    (bundle/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Bundle:',bundle)

if __name__ == '__main__': main()
