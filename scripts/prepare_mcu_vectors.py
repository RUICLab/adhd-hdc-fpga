"""Generate standalone MCU fixtures from independent natural-index parity.
No trained models or third-party packages required. Outputs remain in build/.
"""
import json
import random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/mcu-vectors'
OUT.mkdir(parents=True,exist_ok=True)
D,N=8192,196
def array(name,kind,values):
    return f'static const {kind} {name}[{len(values)}]={{\n'+''.join(
        ','.join(f'0x{x:x}u' for x in values[i:i+8])+',\n'
        for i in range(0,len(values),8))+'};\n'
for k in (10,26):
    rng=random.Random(20261112+k+D)
    text='#include <stdint.h>\n'
    cases=[]
    for case in range(4):
        levels=[rng.getrandbits(D) for _ in range(4)]
        features=[case if case<2 else rng.randrange(4) for _ in range(N)]
        if case==1:features=[3]*N
        q=[]
        for j in range(D):
            count=sum((((1597*(i+1))%D & j).bit_count()&1)^((levels[v]>>j)&1)
                      for i,v in enumerate(features))
            q.append(int(count>=96))
        query=sum(bit<<j for j,bit in enumerate(q))
        prototypes=[query]*k if case==0 else [rng.getrandbits(D) for _ in range(k)]
        if case==3:prototypes[-1]=query
        words=[sum(((v>>j)&1)<<l for l,v in enumerate(levels))|
               sum(((v>>j)&1)<<(4+c) for c,v in enumerate(prototypes)) for j in range(D)]
        scores=[D-(query^p).bit_count() for p in prototypes]
        qw=[(query>>(32*i))&0xffffffff for i in range(D//32)]
        for suffix,kind,values in [('model','uint32_t',words),('features','uint8_t',features),
                                   ('scores','uint16_t',scores),('query','uint32_t',qw)]:
            text+=array(f'k{k}_case{case}_{suffix}',kind,values)
        cases.append(dict(case=case,winner=max(range(k),key=lambda c:scores[c]),scores=scores))
    (OUT/f'vectors_k{k}.h').write_text(text,encoding='utf-8')
    (OUT/f'expected_k{k}.json').write_text(json.dumps(cases,indent=2))
print(f'Generated independent fixtures in {OUT}')
