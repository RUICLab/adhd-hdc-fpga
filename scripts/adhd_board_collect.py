"""Archive compact, attributable evidence only after both hardware runs pass."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    summary={'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             'tool':'Vivado/XSim 2025.2 SW build 6299465',
             'board_target':'See per-configuration hardware_results.txt',
             'part':'xc7z020clg400-1','requested_core_clock_mhz':100,
             'scope':'Physical FPGA synthetic ROM fixtures, JTAG restart/readback; no trained accuracy or measured power',
             'source_sha256':{},'configurations':{}}
    sources=[ROOT/'hw/adhd/adhd_hdc.sv',ROOT/'hw/adhd/adhd_board_test.sv',
             ROOT/'hw/adhd/adhd_board_top.sv',ROOT/'hw/adhd/pynq_z2_board.xdc']
    sources+=sorted((ROOT/'scripts').glob('adhd_board*'))
    sources+=[ROOT/'sim/adhd/tb_board.sv',ROOT/'scripts/adhd_verify.py']
    summary['source_sha256']={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sources}
    for k in (10,26):
        build=ROOT/'build'/f'adhd-board-k{k}'
        hw=(build/'hardware_results.txt').read_text()
        if hw.count('BOARD PASS run=')!=5 or 'ADHD HARDWARE PASS:' not in hw:
            raise RuntimeError(f'Incomplete hardware evidence for K={k}')
        dest=ROOT/'docs/adhd'/f'board-2025.2-k{k}'
        dest.mkdir(parents=True,exist_ok=True)
        for name in ['hardware_results.txt','build_metrics.txt','timing_route.rpt',
                     'utilization_route.rpt','drc_route.rpt','xsim_board_sim.txt','rom_audit.txt']:
            shutil.copyfile(build/name,dest/name)
        shutil.copyfile(ROOT/'build'/f'adhd-sim-k{k}-d8192/simulate.txt',dest/'core_simulation.txt')
        summary['configurations'][str(k)]={'bitstream_sha256':sha(build/'board.bit'),
            'probes_sha256':sha(build/'board.ltx'),'fixture_sha256':{
                p.name:sha(p) for p in sorted(build.glob('board_*.hex'))},
            'hardware_batches':5,'hardware_inferences':20,'hardware_query_comparisons':163840,
            'hardware_errors':0,'core_cycles':8192+5+k,
            'core_time_us_from_cycles_at_requested_clock':(8192+5+k)/100,
            'timing':(build/'build_metrics.txt').read_text().splitlines()}
    path=ROOT/'docs/adhd/board_metrics.json'
    path.write_text(json.dumps(summary,indent=2)+'\n')
    print(path)

if __name__=='__main__': main()
