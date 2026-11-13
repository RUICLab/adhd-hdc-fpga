"""Simulate the exact synthesizable board fixture controller, including restart."""
import argparse
import os
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--classes',type=int,choices=[10,26],default=10)
    ap.add_argument('--vivado',required=True)
    a=ap.parse_args()
    out=ROOT/'build'/f'adhd-board-k{a.classes}'
    binpath=Path(a.vivado)/'bin'
    env=os.environ.copy()
    env['PATH']=str(binpath)+os.pathsep+env['PATH']
    (out/'tb_config.sv').write_text(f'module tb_config; tb_board #(.CLASSES({a.classes})) test(); endmodule\n')
    commands=[('xvlog',['--sv',str(ROOT/'hw/adhd/adhd_hdc.sv'),
        str(ROOT/'hw/adhd/adhd_board_test.sv'),str(ROOT/'sim/adhd/tb_board.sv'),'tb_config.sv']),
        ('xelab',['tb_config','-debug','typical','-s','board_test']),
        ('xsim',['board_test','-runall'])]
    for name,args in commands:
        p=subprocess.run([str(binpath/(name+'.bat'))]+args,cwd=out,env=env,capture_output=True,text=True)
        log=p.stdout+p.stderr
        (out/f'{name}_board_sim.txt').write_text(log)
        if p.returncode or 'Fatal:' in log or 'ERROR:' in log:
            raise RuntimeError(log[-5000:])
    if log.count('BOARD CONTROLLER PASS')!=2: raise RuntimeError(log[-5000:])
    print('\n'.join(line for line in log.splitlines() if 'BOARD CONTROLLER PASS' in line))

if __name__=='__main__': main()
