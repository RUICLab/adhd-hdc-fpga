"""Sensitivity model, NOT a hardware timing measurement or cycle-accurate sim.
Input must be dynamic executed instructions for one full kernel invocation,
not a static assembly line count or wall time spent running an emulator.
"""
import argparse,json
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument('--instructions10',type=int,required=True)
ap.add_argument('--instructions26',type=int,required=True)
ap.add_argument('--source',required=True,help='How instruction counts were obtained')
ap.add_argument('--evidence',type=Path,required=True)
ap.add_argument('--mhz',type=float,default=160)
ap.add_argument('--cpi',type=float,nargs='+',default=[1,2,3])
ap.add_argument('--out',type=Path)
a=ap.parse_args()
if not a.evidence.is_file():ap.error('Provide the actual counting evidence file')
if min(a.instructions10,a.instructions26,a.mhz,*a.cpi)<=0:ap.error('Counts, MHz and CPI must be positive')
result=dict(target='ESP32-C3',kind='analytical instruction/CPI sensitivity; not measured runtime',
    frequency_mhz=a.mhz,instruction_count_source=a.source,evidence=str(a.evidence),
    warning='CPI values are assumptions, not calibrated ESP32 timings or hardware bounds',results=[])
for k,n in [(10,a.instructions10),(26,a.instructions26)]:
    for cpi in a.cpi:
        us=n*cpi/a.mhz
        result['results'].append(dict(classes=k,instructions=n,assumed_cpi=cpi,
            estimated_us=us,estimated_mcu_over_fpga=us/(82.07 if k==10 else 82.23)))
text=json.dumps(result,indent=2)+'\n'
if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text)
print(text)
