"""Compile RV32 firmware and run real CPU RTL, recording cycle counts.
This is a PicoRV32 reference MCU, NOT an ESP32 hardware timing simulation.
"""
import argparse,hashlib,json,os,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser()
ap.add_argument('--vivado',default='C:/vivado/2026.1/Vivado')
ap.add_argument('--gcc',default='C:/vivado/2026.1/Vivado/gnu/riscv/linux_toolchain/nt32/bin/riscv32-amd-linux-gcc.exe')
a=ap.parse_args()
out=ROOT/'build/mcu-rtl';out.mkdir(parents=True,exist_ok=True)
compiler=Path(a.gcc);binpath=Path(a.vivado)/'bin'
env=os.environ.copy();env['PATH']=str(compiler.parent)+os.pathsep+str(binpath)+os.pathsep+env['PATH']
def run(cmd,name):
    p=subprocess.run(list(map(str,cmd)),cwd=out,env=env,capture_output=True,text=True)
    (out/(name+'.txt')).write_text(p.stdout+p.stderr,encoding='utf-8')
    if p.returncode:raise RuntimeError(name+' failed\n'+(p.stdout+p.stderr)[-5000:])
    return p.stdout+p.stderr
run([sys.executable,ROOT/'scripts/prepare_mcu_vectors.py'],'vectors')
if not (ROOT/'build/vendor/picorv32/picorv32.v').exists():
    run([sys.executable,ROOT/'scripts/fetch_picorv32.py'],'fetch')
vendor=ROOT/'build/vendor/picorv32/picorv32.v'
if hashlib.sha256(vendor.read_bytes()).hexdigest()!='0836050971b3c6cdd28ac3b1e5719a67fb645161912bef1e472e63995ceb0622':
    raise RuntimeError('PicoRV32 source differs from the pinned reference')
flags=['-O3','-march=rv32imc_zicsr_zicntr','-mabi=ilp32','-ffreestanding',
       '-fno-builtin','-fno-pie','-no-pie','-fno-stack-protector',
       '-fno-tree-loop-distribute-patterns','-msmall-data-limit=0',
       '-fdata-sections','-ffunction-sections','-nostdlib','-nostartfiles','-static',
       '-I',ROOT/'bench/mcu','-I',ROOT/'build/mcu-vectors',
       '-Wl,--gc-sections,--no-relax,--build-id=none','-Wl,-Map,firmware.map',
       '-T',ROOT/'bench/mcu/link.ld']
print(run([compiler,'--version'],'compiler').splitlines()[0],flush=True)
run([compiler,*flags,ROOT/'bench/mcu/start.S',ROOT/'bench/mcu/hdc_packed.c',
     ROOT/'bench/mcu/firmware.c','-o','firmware.elf'],'compile_firmware')
objcopy=compiler.with_name(compiler.name.replace('gcc','objcopy'))
objdump=compiler.with_name(compiler.name.replace('gcc','objdump'))
run([objcopy,'-O','binary','firmware.elf','firmware.bin'],'objcopy')
run([objdump,'-d','firmware.elf'],'disassembly')
data=(out/'firmware.bin').read_bytes()
if len(data)>512*1024:raise RuntimeError('Firmware exceeds modeled RAM')
data+=bytes(512*1024-len(data))
(out/'firmware.hex').write_text(''.join(f'{int.from_bytes(data[i:i+4],"little"):08x}\n'
                                      for i in range(0,len(data),4)))
suffix='.bat' if os.name=='nt' else ''
run([binpath/('xvlog'+suffix),'--sv',ROOT/'build/vendor/picorv32/picorv32.v',
     ROOT/'sim/adhd/tb_mcu.sv'],'xvlog')
run([binpath/('xelab'+suffix),'tb_mcu','-s','mcu_snapshot'],'xelab')
print('Running MCU RTL simulation (no hardware acceleration)...',flush=True)
# Stream simulator output so progress and any traps are visible immediately.
cmd=[str(binpath/('xsim'+suffix)),'mcu_snapshot','-runall']
with (out/'simulate.txt').open('w',encoding='utf-8') as log:
    p=subprocess.Popen(cmd,cwd=out,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    lines=[]
    for line in p.stdout:
        log.write(line);log.flush();lines.append(line)
        if any(s in line for s in ('MCU_','PASS MCU','Fatal:','ERROR:')):print(line.rstrip(),flush=True)
    code=p.wait()
text=''.join(lines)
if code or 'PASS MCU RTL' not in text or 'Fatal:' in text:raise RuntimeError(text[-5000:])
pattern=r'MCU_RESULT K=(\d+) raw_cycles=(\d+) overhead=(\d+) cycles=(\d+) instructions=(\d+) winner=(\d+) score=(\d+)'
results=[]
for match in re.finditer(pattern,text):
    k,raw,overhead,cycles,insns,winner,score=map(int,match.groups())
    results.append(dict(classes=k,raw_cycles=raw,overhead_cycles=overhead,cycles=cycles,
      instructions=insns,winner=winner,score=score,latency_us_at_100mhz=cycles/100,
      mcu_over_fpga_latency=(cycles/100)/(82.07 if k==10 else 82.23)))
if {r['classes'] for r in results}!={10,26}:raise RuntimeError('Missing class variants')
(out/'results.json').write_text(json.dumps(dict(model='PicoRV32 RV32IMC',clock_mhz=100,
    memory='512KiB SRAM; registered one-cycle native-bus response; no cache/flash/interrupts',
    kernel='Gray-code packed32 feature lanes and bit-plane class counters',results=results),indent=2)+'\n')
print(json.dumps(results,indent=2))
