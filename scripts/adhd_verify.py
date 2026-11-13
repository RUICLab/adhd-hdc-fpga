"""Independent direct-parity golden vs Gray-code streaming RTL, using XSim.
Run: python scripts/adhd_verify.py --classes 10 (also 26).
Synthetic tests validate arithmetic, not trained classification accuracy.
"""
import argparse
import json
import random
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(cmd, folder, name):
    p = subprocess.run(cmd, cwd=folder, capture_output=True, text=True)
    (folder / (name + '.txt')).write_text(p.stdout + p.stderr)
    if p.returncode:
        raise RuntimeError(f'{name} failed: {p.stdout[-3000:]} {p.stderr[-1000:]}')
    return p.stdout

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--classes', type=int, choices=[10,26], default=10)
    ap.add_argument('--bits', type=int, default=13)
    ap.add_argument('--saif', action='store_true', help='capture random inference activity only')
    ap.add_argument('--netlist', action='store_true', help='verify routed functional netlist and capture mapped activity')
    ap.add_argument('--vivado', required=True, help='installed Vivado root, containing bin/')
    a = ap.parse_args()
    d, k = 1 << a.bits, a.classes
    out = ROOT / 'build' / f'adhd-{"gate" if a.netlist else "sim"}-k{k}-d{d}'
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261112+k+d)
    # Reference evaluates direct parity at NATURAL dimension indices. No Gray
    # recurrence, tree popcount, or RTL implementation code is reused here.
    cases = []
    for case in range(4):
        levels = [rng.getrandbits(d) for _ in range(4)]
        features = [case if case < 2 else rng.randrange(4) for _ in range(196)]
        if case == 1:
            features = [3]*196
        query = []
        for j in range(d):
            c = sum((((1597*(i+1)) % d & j).bit_count() & 1) ^
                    ((levels[v] >> j) & 1) for i,v in enumerate(features))
            query.append(int(c >= 96))
        # Exact all-class tie tests full-D counter width and tie policy.
        qword = sum(q << j for j,q in enumerate(query))
        prototypes = [qword]*k if case == 0 else [rng.getrandbits(d) for _ in range(k)]
        if case == 3:
            prototypes[-1] = qword  # winning last class exercises scan final edge
        words = [sum(((v >> j) & 1) << l for l,v in enumerate(levels)) |
                 sum(((p >> j) & 1) << (4+c) for c,p in enumerate(prototypes))
                 for j in range(d)]
        scores = [d - (qword ^ p).bit_count() for p in prototypes]
        winner = max(range(k), key=lambda c:scores[c])
        for name, vals, width in [('model',words,8),('features',features,1),
                                 ('query',query,1),('scores',scores,4)]:
            (out/f'{name}{case}.hex').write_text(''.join(f'{v:0{width}x}\n' for v in vals))
        cases.append(dict(case=case,winner=winner,scores=scores))
    (out/'expected.json').write_text(json.dumps(cases,indent=2))
    binpath=Path(a.vivado)/'bin'
    import os
    env=os.environ.copy()
    env['PATH']=str(binpath)+os.pathsep+env['PATH']
    # .bat tool launchers need Windows cmd; paths passed as separate arguments.
    def invoke(tool,args,name):
        cmd=[str(binpath/(tool+'.bat'))]+args
        p=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True)
        (out/(name+'.txt')).write_text(p.stdout+p.stderr)
        if p.returncode: raise RuntimeError((p.stdout+p.stderr)[-5000:])
        return p.stdout
    wrapper=out/'tb_config.sv'
    wrapper.write_text(f'module tb_config; tb_adhd #(.CLASSES({k}),.DIM_BITS({a.bits}),.CAPTURE({int(a.saif)})) test(); endmodule\n')
    source=ROOT/f'build/adhd-k{k}/adhd_funcsim.v' if a.netlist else ROOT/'hw/adhd/adhd_hdc.sv'
    compile_args=['--sv']+(['-d','ADHD_NETLIST'] if a.netlist else [])
    sources=[str(source),str(ROOT/'sim/adhd/tb_adhd.sv'),str(wrapper)]
    if a.netlist: sources.append(str(Path(a.vivado)/'data/verilog/src/glbl.v'))
    invoke('xvlog',compile_args+sources,'compile')
    invoke('xelab',['tb_config']+(['glbl','-L','unisims_ver'] if a.netlist else [])+
           ['-debug','typical','-s','adhd_test'],'elaborate')
    if a.saif:
        script=out/'capture.tcl'
        script.write_text('run all\nopen_saif inference.saif\n'
                          'log_saif [get_objects -r /tb_config/test/dut/*]\n'
                          'run all\nclose_saif\nrun all\nquit\n')
        log=invoke('xsim',['adhd_test','-tclbatch',script.name],'simulate')
    else:
        log=invoke('xsim',['adhd_test','-runall'],'simulate')
    if 'ADHD PASS' not in log or 'FATAL' in log: raise RuntimeError(log[-4000:])
    print(log[log.find('CASE'):log.rfind('$finish')])

if __name__=='__main__': main()
