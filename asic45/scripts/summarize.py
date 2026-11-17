"""Audit final tool evidence and derive per-inference energy without fitted constants."""
from pathlib import Path
from collections import defaultdict
import csv,hashlib,json,math,re
ROOT=Path(__file__).resolve().parents[1]

def kv(path):return dict(line.split('=',1) for line in path.read_text().splitlines() if '=' in line)
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(str,row))+' |' for row in rows])

def main():
    prep=json.loads((ROOT/'reports/preparation.json').read_text())
    assert hashlib.sha256((ROOT/'rtl/adhd_hdc_original.sv').read_bytes()).hexdigest()==prep['original_rtl_sha256']
    area_data=json.loads((ROOT/'vendor/cell_areas.json').read_text())
    areas=area_data['areas_um2']
    library_hash=area_data['source_sha256']
    if (ROOT/'vendor/NangateOpenCellLibrary_typical.lib').exists():
        assert hashlib.sha256((ROOT/'vendor/NangateOpenCellLibrary_typical.lib').read_bytes()).hexdigest()==library_hash
    result={'original_rtl_sha256':prep['original_rtl_sha256'],
        'library_source':json.loads((ROOT/'vendor/library_source.json').read_text()),
        'library_sha256':library_hash,
        'tools':{'synthesis':'Design Compiler X-2025.06-SP3','timing_power':'PrimeTime / PrimePower X-2025.06-SP2','gate_simulation':'VCS X-2025.06-SP1-1','sram':'CACTI 7, commit 1ffd8dfb10303d306ecd8d215320aea07651e878'},
        'assumptions':{'standard_cells':'Nangate45 typical, 1.1 V, 25 C',
            'sram':'45 nm ITRS-LSTP cell/periphery; 1.1 V; 300 K; single bank/one RW port; byte-rounded 16/32-bit words; no ECC/tags/gating; ED^2 optimization',
            'activity':'zero-delay mapped-netlist simulation, exact original board fixture case 2; every query/winner/score/cycle checked; input loading excluded',
            'clock':'ideal clock distribution: no CTS buffers/wire parasitics. Library-modeled FF clock-pin internal power IS included and separately itemized.',
            'interconnect':'Nangate 5K_hvratio_1_1 top wire-load; no physical placement/routing/SPEF',
            'io':'1 ns max / 0 min input and output delays, 2 fF output loads, 50 ps input/clock transition',
            'uncertainty':'100 ps setup and hold; hold-fix mapping enabled',
            'sram_interface':'CACTI read delay; assumed 2 fF input capacitance, 50 ps output slew, 50 ps write setup, zero hold; integration abstract, not characterized IP',
            'fmax':'all-path setup bound with stated I/O/uncertainty and modeled SRAM; 1 ps positive margin; rechecked; not post-layout signoff',
            'fmax_energy':'fixed-workload dynamic energy; dynamic power scales linearly with frequency; leakage fixed at same voltage/temperature; no high-frequency timing-aware activity rerun',
            'excluded':'CTS distribution, routing extraction/glitches, scan/tie/filler/power-grid/margin area, model/feature transfer and writes, host, sensor and digital frontend'},
        'configurations':{}}
    blocks={}
    for k in (10,26):
        folder=ROOT/f'build/k{k}'
        for log in [ROOT/f'reports/synth_k{k}.log',ROOT/f'reports/pt_k{k}.log']:
            text=log.read_text()
            assert not re.search(r'^Error:',text,re.M),f'Final tool error in {log}'
        assert f'ASIC PT ANALYSIS COMPLETE K={k}' in (ROOT/f'reports/pt_k{k}.log').read_text()
        check=(folder/'sim/check.log').read_text();activity=(folder/'sim/activity.log').read_text()
        assert 'ADHD PASS' in check and 'Fatal:' not in check
        assert len(re.findall(r'CASE \d PASS',check))==4
        assert 'ASIC ACTIVITY PASS' in activity and 'Fatal:' not in activity
        assert '100.00%' in (ROOT/f'reports/pt_k{k}.log').read_text()
        assert 'No constrained paths' not in (folder/'timing_sram_read.rpt').read_text()
        c=kv(folder/'cell_metrics.txt');t=kv(folder/'timing_metrics.txt')
        assert int(c['sram_macro_count'])==1
        assert float(t['sram_read_path_arrival_ns'])>0
        assert float(t['hold_slack_100mhz_ns'])>=0
        assert float(t['fmax_setup_slack_ns'])>=0
        window=json.loads((folder/'sim/activity_window.json').read_text())
        assert window['duration_ps']==(8192+5+k)*10000
        powers=list(csv.DictReader((folder/'power_cells.tsv').open(),delimiter='\t'))
        std=[row for row in powers if not row['ref'].startswith('adhd_sram_')]
        macro=[row for row in powers if row['ref'].startswith('adhd_sram_')]
        assert len(macro)==1 and len(std)==int(c['standard_cell_count'])
        assert sum(row['ref'].startswith('DFF') for row in std)==int(c['ff_count'])
        assert math.isclose(sum(areas[r['ref']] for r in std),float(c['standard_cell_area_um2']),abs_tol=1e-5)
        sums={name:sum(float(row[name]) for row in powers) for name in ['internal_w','switching_w','leakage_w','total_w','clock_internal_w']}
        assert math.isclose(sums['internal_w']+sums['switching_w']+sums['leakage_w'],sums['total_w'],rel_tol=1e-7)
        mapping={row['cell']:row['block'] for row in csv.DictReader((folder/'block_members.tsv').open(),delimiter='\t')}
        group=defaultdict(lambda:{'cell_count':0,'ff_count':0,'area_um2':0.,'internal_w':0.,'switching_w':0.,'leakage_w':0.})
        for row in std:
            block=group[mapping[row['cell']]];block['cell_count']+=1
            block['ff_count']+=int(row['ref'].startswith('DFF'))
            block['area_um2']+=areas[row['ref']]
            block['internal_w']+=float(row['internal_w'])-float(row['clock_internal_w'])
            block['switching_w']+=float(row['switching_w']);block['leakage_w']+=float(row['leakage_w'])
        group['register_clock_pins']['internal_w']=sums['clock_internal_w']
        group['sram_interface_nets']['switching_w']=sum(float(r['switching_w']) for r in macro)
        for name in ('internal_w','switching_w','leakage_w'):
            assert math.isclose(sum(b[name] for b in group.values()),sums[name],rel_tol=1e-7,abs_tol=1e-12)
        sram=prep['sram'][str(k)];cycles=8192+5+k;fmax=float(t['fmax_mhz'])
        scenarios={}
        for name,freq in [('100mhz',100.),('fmax',fmax)]:
            latency=cycles/freq
            sc_dyn=(sums['internal_w']+sums['switching_w'])*(freq/100)*latency*1000
            sc_leak=sums['leakage_w']*latency*1000
            sr_read=8192*sram['read_nj'];sr_leak=sram['total_leakage_mw']*latency
            scenarios[name]={'frequency_mhz':freq,'latency_us':latency,
                'standard_cell_dynamic_nj':sc_dyn,'standard_cell_leakage_nj':sc_leak,
                'sram_read_nj':sr_read,'sram_leakage_nj':sr_leak,'sram_total_nj':sr_read+sr_leak,
                'total_nj':sc_dyn+sc_leak+sr_read+sr_leak,
                'standard_cell_internal_mw':sums['internal_w']*freq/100*1000,
                'standard_cell_switching_mw':sums['switching_w']*freq/100*1000,
                'standard_cell_leakage_mw':sums['leakage_w']*1000}
        for b in group.values():
            b['dynamic_nj_100mhz']=(b['internal_w']+b['switching_w'])*scenarios['100mhz']['latency_us']*1000
            b['leakage_nj_100mhz']=b['leakage_w']*scenarios['100mhz']['latency_us']*1000
        cfg={'classes':k,'dimensions':8192,'cycles':cycles,'cell_metrics':c,'timing_metrics':t,
            'standard_cell_area_mm2':float(c['standard_cell_area_um2'])/1e6,
            'sram_area_mm2':sram['area_mm2'],'total_cell_footprint_mm2':float(c['standard_cell_area_um2'])/1e6+sram['area_mm2'],
            'sram_model':sram,'activity_window':window,'gate_checks':'four board fixtures passed; every query bit/address, final winner/score, cycle count; reset/restart/busy guards/backpressure',
            'scenarios':scenarios,'power_block_allocation':dict(group)}
        result['configurations'][str(k)]=cfg;blocks[k]=group
    (ROOT/'reports/results.json').write_text(json.dumps(result,indent=2)+'\n')
    rows=[]
    for k in (10,26):
        cfg=result['configurations'][str(k)]
        for scenario in ['100mhz','fmax']:
            s=cfg['scenarios'][scenario]
            rows.append([k,f"{s['frequency_mhz']:.2f}",f"{s['latency_us']:.3f}",f"{s['standard_cell_dynamic_nj']:.3f}",f"{s['standard_cell_leakage_nj']:.3f}",f"{s['sram_total_nj']:.3f}",f"{s['total_nj']:.3f}"])
    text=['# 45-nm HDC backend: final audited estimates','',table(['K','MHz','Latency us','Std dynamic nJ','Std leakage nJ','SRAM total nJ','Total nJ'],rows),'',
        'Standard-cell dynamic includes the modeled local net switching at the SRAM output interface. SRAM total is exactly 8192 reads * CACTI read energy + CACTI leakage * inference time.','']
    rows=[]
    for k in (10,26):
        c=result['configurations'][str(k)];m=c['cell_metrics'];t=c['timing_metrics']
        rows.append([k,m['standard_cell_count'],m['ff_count'],f"{float(m['standard_cell_area_um2']):.3f}",f"{c['sram_area_mm2']:.7f}",f"{c['total_cell_footprint_mm2']:.7f}",t['critical_data_arrival_ns'],t['setup_slack_100mhz_ns'],t['hold_slack_100mhz_ns']])
    text += [table(['K','Std cells','FFs','Std area um2','SRAM mm2','Total footprint mm2','Worst data arrival ns','Setup slack ns','Hold slack ns'],rows),'',
        'Worst data arrival includes the fixed 1-ns external input delay when the critical startpoint is an input port. Full path reports identify every cell/net. Register-only timing is recorded separately.','']
    for k in (10,26):
        cfg=result['configurations'][str(k)];s=cfg['scenarios']['100mhz'];m=cfg['sram_model']
        text += [f'## K={k}: 100-MHz power and SRAM',f"Internal {s['standard_cell_internal_mw']:.6f} mW; switching {s['standard_cell_switching_mw']:.6f} mW; standard-cell leakage {s['standard_cell_leakage_mw']:.6f} mW.",
            f"SRAM read {m['read_nj']:.8f} nJ/access; total leakage {m['total_leakage_mw']*1000:.6f} uW (subthreshold + gate); area {m['area_mm2']:.7f} mm2.",'']
        rows=[]
        for name,b in blocks[k].items():
            rows.append([name,b['cell_count'],f"{b['area_um2']:.3f}",f"{b['internal_w']*1000:.6f}",f"{b['switching_w']*1000:.6f}",f"{b['leakage_w']*1000:.6f}",f"{b['dynamic_nj_100mhz']:.3f}"])
        text += [table(['Block','Cells','Area um2','Internal mW','Switching mW','Leakage mW','Dynamic nJ/inference'],rows),'']
    text += ['## Assumptions and limits']+[f'- **{name}:** {value}' for name,value in result['assumptions'].items()]
    text += ['','Block attribution is an approximate disjoint capture-register cone partition. Shared combinational logic is assigned in lanes/popcount/classes/control order. Register clock-pin internal power is moved out of those blocks into its own row; no clock power is counted twice. Clock-distribution energy/area is not estimated.','',
        'All final Design Compiler and PrimeTime logs are error-free. The mapped array remains one SRAM black box per K. Final mapped netlist checks and the activity case pass. This is a pre-layout estimate with an analytical SRAM, not silicon measurement or a signoff Fmax.','',
        '## Optional digital frontend baseline','Not run in this backend study. No regional/convolutional frontend area, energy or latency is inferred from CPU timings or from the backend results.','']
    (ROOT/'RESULTS.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(table(['K','MHz','Latency us','Std dynamic nJ','Std leakage nJ','SRAM total nJ','Total nJ'],
        [[k,f"{c['scenarios'][s]['frequency_mhz']:.2f}",f"{c['scenarios'][s]['latency_us']:.3f}",f"{c['scenarios'][s]['standard_cell_dynamic_nj']:.3f}",f"{c['scenarios'][s]['standard_cell_leakage_nj']:.3f}",f"{c['scenarios'][s]['sram_total_nj']:.3f}",f"{c['scenarios'][s]['total_nj']:.3f}"] for k,c in [(10,result['configurations']['10']),(26,result['configurations']['26'])] for s in ['100mhz','fmax']]))
if __name__=='__main__':main()
