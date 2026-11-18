"""Run existing ESP32-C3 firmware, validate UART and count executed kernel PCs.

Requires an ESP-IDF Python environment. QEMU counters are not hardware time.
Raw instruction traces stay in the ignored build folder (can be several GB).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--idf', type=Path, required=True)
ap.add_argument('--qemu', type=Path, required=True)
ap.add_argument('--toolchain-bin', type=Path, required=True)
ap.add_argument('--build', type=Path, required=True)
ap.add_argument('--classes', type=int, choices=[10, 26], required=True)
ap.add_argument('--out', type=Path, required=True)
ap.add_argument('--timeout', type=int, default=600)
a = ap.parse_args()
b = a.build.resolve()
a.out.mkdir(parents=True, exist_ok=True)
elf = b / 'adhd_esp32_benchmark.elf'
def tool(name):
    return str(a.toolchain_bin / ('riscv32-esp-elf-' + name + ('.exe' if os.name == 'nt' else '')))
nm = subprocess.check_output([tool('nm'), '-S', str(elf)], text=True)
symbol = re.search(r'^([0-9a-f]+) ([0-9a-f]+) [Tt] hdc_packed32$', nm, re.M)
if not symbol:
    raise RuntimeError('Missing hdc_packed32 symbol')
start, size = (int(x, 16) for x in symbol.groups())
dis = subprocess.check_output([tool('objdump'), '-d', '--disassemble=hdc_packed32', str(elf)], text=True)
(a.out / 'kernel_disassembly.txt').write_text(dis)
# The address-filtered count is complete only for an entirely inline kernel.
if re.search(r'\b(?:jal|jalr|call|tail)\b', dis):
    raise RuntimeError('Kernel contains a call/indirect jump; extend trace coverage before counting')
subprocess.run([sys.executable, '-m', 'esptool', '--chip=esp32c3', 'merge-bin',
                '--output=qemu_flash.bin', '--pad-to-size=4MB', '@flash_args'], cwd=b, check=True)
sys.path.insert(0, str(a.idf / 'tools'))
from idf_py_actions.qemu_ext import QEMU_TARGETS
efuse = b / 'qemu_efuse.bin'
efuse.write_bytes(QEMU_TARGETS['esp32c3'].default_efuse)
trace = b / 'kernel_trace.txt'
cmd = [str(a.qemu), '-M', 'esp32c3', '-drive', f'file={b / "qemu_flash.bin"},if=mtd,format=raw',
       '-drive', f'file={efuse},if=none,format=raw,id=efuse', '-global',
       'driver=nvram.esp32c3.efuse,property=drive,value=efuse', '-global',
       'driver=timer.esp32c3.timg,property=wdt_disable,value=true', '-nographic', '-serial', 'mon:stdio',
       '-accel', 'tcg,one-insn-per-tb=on', '-d', 'exec,nochain',
       '-dfilter', f'0x{start:x}..0x{start+size-1:x}', '-D', str(trace)]
(a.out / 'command.json').write_text(json.dumps(cmd, indent=2) + '\n')
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding='utf-8', errors='replace', bufsize=1)
timer = threading.Timer(a.timeout, proc.kill)
timer.start()
lines = []
passed = False
try:
    with (a.out / 'uart.txt').open('w') as uart:
        for line in proc.stdout:
            uart.write(line)
            uart.flush()
            lines.append(line)
            if 'ESP32_HDC' in line:
                print(line.rstrip(), flush=True)
            if f'ESP32_HDC PASS classes={a.classes};' in line:
                passed = True
                proc.stdin.write('\x01x')  # QEMU mon:stdio exit, after the full PASS marker.
                proc.stdin.flush()
        proc.wait(timeout=15)
finally:
    timer.cancel()
    if proc.poll() is None:
        proc.kill()
        proc.wait()
if not passed or any('ESP32_HDC FAIL' in line for line in lines):
    raise RuntimeError('Functional QEMU validation did not pass; inspect uart.txt')
# With one-insn-per-tb and chaining disabled each Trace record executes one
# instruction. A new entry PC starts each call; no recursive calls exist.
counts = []
count = 0
last_pc = None
return_pcs = {int(x, 16) for x in re.findall(r'^\s*([0-9a-f]+):.*\bret\b', dis, re.M)}
if not return_pcs:
    raise RuntimeError('No kernel return instruction found')
digest = hashlib.sha256()
pattern = re.compile(rb'Trace \d+: .*\[[0-9a-f]+/([0-9a-f]+)/')
with trace.open('rb') as f:
    for line in f:
        digest.update(line)
        m = pattern.search(line)
        if not m:
            continue
        pc = int(m[1], 16)
        if not start <= pc < start+size:
            raise RuntimeError('Trace contains a PC outside the kernel')
        if pc == start:
            if count:
                if last_pc not in return_pcs:
                    raise RuntimeError('Incomplete kernel call in trace')
                counts.append(count)
            count = 0
        if not count and pc != start:
            raise RuntimeError('Trace started in the middle of a kernel call')
        count += 1
        last_pc = pc
if count:
    if last_pc not in return_pcs:
        raise RuntimeError('Final traced call did not finish at a kernel return')
    counts.append(count)
if len(counts) != 13 or len(set(counts[4:])) != 1:
    raise RuntimeError(f'Expected four verification + nine identical timed calls, got {counts}')
result = dict(target='ESP32-C3', classes=a.classes, kind='QEMU functional + dynamic instruction count',
              kernel_address=hex(start), kernel_size=size, call_instructions=counts,
              timed_instructions=counts[4], trace_bytes=trace.stat().st_size,
              trace_sha256=digest.hexdigest(), elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
              compiler=subprocess.check_output([tool('gcc'), '--version'], text=True).splitlines()[0],
              qemu=subprocess.check_output([str(a.qemu), '--version'], text=True).splitlines()[0],
              warning='No hardware cycle timing is modeled by this QEMU execution')
(a.out / 'results.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2), flush=True)
