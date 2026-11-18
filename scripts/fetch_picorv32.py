"""Fetch a pinned, small CPU RTL source; no tool installation or system changes."""
import hashlib,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/vendor/picorv32';OUT.mkdir(parents=True,exist_ok=True)
COMMIT='ef203c2b0a3fb793280f5114941416c425c5b461'
EXPECTED={'picorv32.v':'0836050971b3c6cdd28ac3b1e5719a67fb645161912bef1e472e63995ceb0622',
          'COPYING':'041ebc727233e5bf096dd41260cbb81014d3d29ca007a15f3b1807d4e9ff288e'}
manifest={'repository':'https://github.com/YosysHQ/picorv32','commit':COMMIT,'files':{}}
for name in ('picorv32.v','COPYING'):
    url=f'https://raw.githubusercontent.com/YosysHQ/picorv32/{COMMIT}/{name}'
    data=urllib.request.urlopen(url,timeout=60).read()
    if hashlib.sha256(data).hexdigest()!=EXPECTED[name]:raise RuntimeError('Vendor hash mismatch: '+name)
    (OUT/name).write_bytes(data)
    manifest['files'][name]=hashlib.sha256(data).hexdigest()
(OUT/'source.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
