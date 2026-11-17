"""Generate ASIC memory adapter, SRAM interfaces and unchanged board fixtures."""
from pathlib import Path
import hashlib,json,re,shutil,tarfile
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent

def write_lf(path,text):
    with path.open('w',encoding='utf-8',newline='\n') as out:out.write(text)

def number(text,pattern):
    return float(re.search(pattern+r'\s*([0-9.eE+-]+)',text)[1])

def memory_lib(k,w,m):
    # This is a timing ABSTRACT, not a characterized foundry SRAM.
    # Array access delay is from CACTI; port load/slew/setup assumptions are explicit.
    name=f'adhd_sram_8192x{w}'
    header=f'''library (adhd_sram_k{k}) {{
  technology(cmos); delay_model : table_lookup;
  time_unit : "1ns"; voltage_unit : "1V"; current_unit : "1mA";
  leakage_power_unit : "1nW"; capacitive_load_unit(1,ff);
  nom_process : 1; nom_temperature : 25; nom_voltage : 1.1;
  operating_conditions(typical) {{ process:1; temperature:25; voltage:1.1; }}
  default_operating_conditions : typical;
  slew_lower_threshold_pct_rise:30; slew_upper_threshold_pct_rise:70;
  slew_lower_threshold_pct_fall:30; slew_upper_threshold_pct_fall:70;
  input_threshold_pct_rise:50; input_threshold_pct_fall:50;
  output_threshold_pct_rise:50; output_threshold_pct_fall:50;
  type(addr_bus) {{ base_type:array; data_type:bit; bit_width:13; bit_from:12; bit_to:0; downto:true; }}
  type(data_bus) {{ base_type:array; data_type:bit; bit_width:{w}; bit_from:{w-1}; bit_to:0; downto:true; }}
  cell({name}) {{
    area : {m['area_mm2']*1e6:.6f}; is_macro_cell:true; interface_timing:true; dont_use:true; dont_touch:true;
    cell_leakage_power:0;
    pin(CLK) {{ direction:input; clock:true; capacitance:2.0; }}
'''
    setup='''timing() { related_pin:"CLK"; timing_type:setup_rising;
      rise_constraint(scalar) { values("0.05"); } fall_constraint(scalar) { values("0.05"); } }
    timing() { related_pin:"CLK"; timing_type:hold_rising;
      rise_constraint(scalar) { values("0.0"); } fall_constraint(scalar) { values("0.0"); } }'''
    for pin in ['CE','WE']:
        header+=f'    pin({pin}) {{ direction:input; capacitance:2.0; {setup} }}\n'
    for pin,bus in [('A','addr_bus'),('D','data_bus')]:
        header+=f'    bus({pin}) {{ bus_type:{bus}; direction:input; pin("{pin}[{12 if pin=="A" else w-1}:0]") {{ capacitance:2.0; {setup} }} }}\n'
    header+='    bus(Q) { bus_type:data_bus; direction:output;\n'
    for bit in range(w):
        header+=f'      pin("Q[{bit}]") {{ max_capacitance:100;\n'
        for pin in [f'A[{i}]' for i in range(13)]+['CE','WE']:
            header+=f'''        timing() {{ related_pin:"{pin}"; timing_type:combinational; timing_sense:non_unate;
          cell_rise(scalar) {{ values("{m['access_ns']:.8f}"); }}
          cell_fall(scalar) {{ values("{m['access_ns']:.8f}"); }}
          rise_transition(scalar) {{ values("0.05"); }} fall_transition(scalar) {{ values("0.05"); }} }}
'''
        header+='      }\n'
    return header+'    }\n  }\n}\n'

def main():
    original_path=SOURCE/'hw/adhd/adhd_hdc.sv'
    if not original_path.exists():original_path=ROOT/'rtl/adhd_hdc_original.sv'
    original=original_path.read_bytes()
    (ROOT/'rtl/adhd_hdc_original.sv').write_bytes(original)
    manifest={'original_rtl_sha256':hashlib.sha256(original).hexdigest(),'sram':{}}
    model_modules=[]
    for k,w,physical in [(10,14,16),(26,30,32)]:
        report=(ROOT/f'reports/cacti_k{k}.txt').read_text()
        m={'logical_words':8192,'logical_width':w,'physical_width':physical,
           'access_ns':number(report,r'Access time \(ns\):'),
           'cycle_ns':number(report,r'Cycle time \(ns\):'),
           'read_nj':number(report,r'Total dynamic read energy per access \(nJ\):'),
           'subthreshold_leakage_mw':number(report,r'Total leakage power of a bank \(mW\):'),
           'gate_leakage_mw':number(report,r'Total gate leakage power of a bank \(mW\):'),
           'area_mm2':number(report,r'Data array: Area \(mm2\):')}
        m['total_leakage_mw']=m['subthreshold_leakage_mw']+m['gate_leakage_mw']
        manifest['sram'][str(k)]=m
        text=original.decode()
        decl='    (* ram_style="block" *) reg [CLASSES+3:0] model [0:D-1];'
        assert text.count(decl)==1
        text=text.replace(decl,'    // ASIC array storage is a black-box SRAM; word0 remains the original read register.')
        start=text.index('    // Synchronous writable/readable BRAM; never reset array contents.')
        end=text.index('    always @(posedge clk) begin\n        if(!resetn)',start)
        adapter=f'''    // SRAM extraction: same writes and synchronous read behavior, no extra cycle.
    wire sram_write=resetn && ready && !start && model_we;
    wire sram_read=resetn && state==RUN;
    wire [CLASSES+3:0] sram_q;
    adhd_sram_8192x{w} model_sram(.CLK(clk),.CE(sram_write || sram_read),
        .WE(sram_write),.A(sram_read ? j : model_addr),
        .D(model_data[CLASSES+3:0]),.Q(sram_q));
    always @(posedge clk) begin
        if(sram_read) word0<=sram_q;
    end
'''
        text=text[:start]+adapter+text[end:]
        folder=ROOT/f'build/k{k}';folder.mkdir(parents=True,exist_ok=True)
        write_lf(folder/'adhd_hdc_asic.sv',text)
        write_lf(ROOT/f'rtl/sram_k{k}.lib',memory_lib(k,w,m))
        model_modules.append(f'''module adhd_sram_8192x{w}(input CLK,CE,WE,input [12:0] A,input [{w-1}:0] D,output [{w-1}:0] Q);
    reg [{w-1}:0] mem[0:8191];
    always @(posedge CLK) if(CE && WE) mem[A]<=D;
    assign Q=(CE && !WE) ? mem[A] : {w}'b0;
endmodule
''')
        target=folder/'fixtures';target.mkdir(exist_ok=True)
        fixtures=SOURCE/f'build/adhd-sim-k{k}-d8192'
        if fixtures.exists():
            for p in fixtures.glob('*.hex'):shutil.copyfile(p,target/p.name)
            shutil.copyfile(fixtures/'expected.json',target/'expected.json')
        else:
            assert (target/'expected.json').exists(),'Supply the original reference fixture files'
    write_lf(ROOT/'rtl/sram_models.sv','`timescale 1ns/1ps\n'+''.join(model_modules))
    if (SOURCE/'sim/adhd/tb_adhd.sv').exists():
        shutil.copyfile(SOURCE/'sim/adhd/tb_adhd.sv',ROOT/'rtl/tb_adhd_original.sv')
    (ROOT/'reports/preparation.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (ROOT/'tools').mkdir(exist_ok=True)
    with tarfile.open(ROOT/'tools/flow-inputs.tar.gz','w:gz') as tar:
        for folder in ['rtl','scripts','constraints']:
            for p in (ROOT/folder).glob('*'):
                if p.is_file() and p.suffix not in ['.pyc']:tar.add(p,arcname=p.relative_to(ROOT))
        for k in [10,26]:
            p=ROOT/f'build/k{k}/adhd_hdc_asic.sv'
            tar.add(p,arcname=p.relative_to(ROOT))
            for p in (ROOT/f'build/k{k}/fixtures').glob('*'):
                if p.is_file():tar.add(p,arcname=p.relative_to(ROOT))
        tar.add(ROOT/'vendor/NangateOpenCellLibrary.v',arcname='vendor/NangateOpenCellLibrary.v')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
