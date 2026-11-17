"""Fetch third-party inputs with pinned content; never fetch licensed tools."""
from pathlib import Path
import hashlib,json,subprocess,urllib.request
ROOT=Path(__file__).resolve().parents[1]
CACTI_COMMIT='1ffd8dfb10303d306ecd8d215320aea07651e878'

def fetch(url,path,expected):
    data=path.read_bytes() if path.exists() else urllib.request.urlopen(url,timeout=90).read()
    if hashlib.sha256(data).hexdigest()!=expected:raise RuntimeError(f'Input checksum mismatch: {path.name}')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)

def main():
    source=json.loads((ROOT/'vendor/library_source.json').read_text())
    areas=json.loads((ROOT/'vendor/cell_areas.json').read_text())
    fetch(source['url'],ROOT/'vendor/NangateOpenCellLibrary_typical.lib',areas['source_sha256'])
    models=json.loads((ROOT/'vendor/cell_models_source.json').read_text())
    fetch(models['url'],ROOT/'vendor/NangateOpenCellLibrary.v',models['sha256'])
    path=ROOT/'tools/cacti'
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['git','clone','https://github.com/HewlettPackard/cacti.git',str(path)],check=True)
        subprocess.run(['git','-C',str(path),'checkout','--detach',CACTI_COMMIT],check=True)
    actual=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
    if actual!=CACTI_COMMIT:raise RuntimeError('CACTI checkout is not the pinned commit')
    if subprocess.check_output(['git','-C',str(path),'diff','HEAD','--'],text=True):
        raise RuntimeError('CACTI tracked sources have local changes')
    print('Third-party inputs verified')
if __name__=='__main__':main()
