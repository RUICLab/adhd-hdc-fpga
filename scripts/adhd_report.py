"""Summarize FPGA implementation evidence; standard library only."""
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def value(text,key):
    match=re.search(r"\|\s*"+re.escape(key)+r"\s*\|\s*([\d.]+)",text)
    if not match:
        raise ValueError(key)
    return float(match.group(1))

results=[]
for classes in (10,26):
    folder=ROOT/"build"/f"adhd-k{classes}"
    metrics=dict(line.split("=",1) for line in (folder/"metrics.txt").read_text().splitlines())
    utilization=(folder/"utilization_route.rpt").read_text()
    power=(folder/"power_gate_saif.rpt").read_text()
    latency=int(metrics["cycles"])/100
    results.append(dict(classes=classes,luts=int(value(utilization,"Slice LUTs")),
        flip_flops=int(value(utilization,"Slice Registers")),
        bram36_equivalents=value(utilization,"Block RAM Tile"),
        cycles=int(metrics["cycles"]),latency_us=latency,
        setup_slack_ns=float(metrics["setup_slack_ns"]),
        hold_slack_ns=float(metrics["hold_slack_ns"]),
        estimated_dynamic_energy_nj=value(power,"Dynamic (W)")*latency*1000))
print(json.dumps(results,indent=2))
