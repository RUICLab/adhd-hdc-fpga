"""Rebase the inference-only capture to zero and retain an exact end marker."""
from pathlib import Path
import argparse,json,hashlib
def main():
    ap=argparse.ArgumentParser();ap.add_argument('classes',type=int,choices=[10,26]);a=ap.parse_args()
    root=Path(__file__).resolve().parents[1];folder=root/f'build/k{a.classes}/sim'
    expected=(8192+5+a.classes)*10000 # picoseconds, 100-MHz clock
    start=last=None;stamp_count=0;clock_id=None;clock_edges=0;clock_value=None
    with (folder/'inference.vcd').open() as source,(folder/'activity.vcd').open('w') as target:
        for line in source:
            if line.strip()=='$dumpoff':break
            if line.startswith('$var'):
                fields=line.split()
                if fields[4]=='clk' and clock_id is None:clock_id=fields[3]
            if line.startswith('#'):
                t=int(line[1:].strip())
                if start is None:start=t
                last=t-start
                if last>expected:raise RuntimeError('Capture contains events after the inference')
                line=f'#{last}\n';stamp_count+=1
            elif clock_id is not None and len(line)>1 and line[0] in '01' and line[1:].strip()==clock_id:
                value=line[0]
                if clock_value is not None and value!=clock_value:clock_edges+=1
                clock_value=value
            target.write(line)
        if start is None:raise RuntimeError('No waveform timestamps')
        if expected-last>1:raise RuntimeError(f'Unexpected end gap: {expected-last} ps')
        if last<expected:target.write(f'#{expected}\n')
    if clock_edges!=2*(8192+5+a.classes):raise RuntimeError(f'Clock edge count mismatch {clock_edges}')
    metadata={'classes':a.classes,'original_start_ps':start,'last_recorded_offset_ps':last,
        'duration_ps':expected,'duration_ns':expected/1000,'clock_edges':clock_edges,
        'clock_period_ns':10,'recording':'zero delay; no SDF; one board fixture case-2 inference; input loading excluded',
        'raw_vcd_sha256':hashlib.sha256((folder/'inference.vcd').read_bytes()).hexdigest(),
        'rebased_vcd_sha256':hashlib.sha256((folder/'activity.vcd').read_bytes()).hexdigest()}
    (folder/'activity_window.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(metadata))
if __name__=='__main__':main()
