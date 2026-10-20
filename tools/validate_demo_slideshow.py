"""Boot the actual FreeDOS/menu in MartyPC; observe DOS EXEC/return markers.

--real runs all unmodified converted programs, with the production timeout.
Default uses BIOS wait/read stubs to quickly check navigation and grouping.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.demo_slideshow_menu import menu_source,assemble
from tools.demo_freedos_disk import build_disk
from marty_link import launch_config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/demo-slideshow')
    args=parser.parse_args();out=args.output
    rows=json.loads((out/'approved-proposal.json').read_text())['selections']
    run=out/('validation-real' if args.real else 'validation-stubs');run.mkdir(exist_ok=True)
    menu=assemble(menu_source(rows,ticks=182 if args.real else 2,debug=True),run/'MENU.COM')
    sequence=b'R\r\nC\r\nQ\r\n' if args.real else b'N\r\nP\r\nR\r\nC\r\n1\r\n24\r\nQ\r\n'
    # Stub individual selections also must return without a physical key.
    files={'MENU.COM':menu,'CHECK.TXT':sequence,
           'FDAUTO.BAT':b'@ECHO OFF\r\nMENU < CHECK.TXT\r\nDONE\r\n'}
    for r in rows:
        n=r['number'];name=f'EX{n:02}.COM'
        if args.real:payload=(out/name).read_bytes()
        else:
            payload=assemble("bits 16\ncpu 8086\norg 100h\nmov ax,4c00h\nint 21h\n",run/name)
        files[name]=payload
    files['DONE.COM']=assemble("""bits 16
org 100h
mov dx,0e9h
mov al,'Z'
out dx,al
mov al,10
out dx,al
mov ax,0001h
mov bx,0deadh
mov cx,0beefh
int 0f5h
mov ax,0300h
int 0f5h
mov ax,4c00h
int 21h
""",run/'DONE.COM')
    disk=run/'probe.dsk'
    disk.write_bytes(build_disk(files,out/'freedos/720k/x86BOOT.img'))
    install=ROOT/'external/martypc/install'
    configtext=launch_config((install/'martypc-cga.toml').read_text(),disk,False,
                            floppy_type='720k',resource_root=install,run_dir=run)
    configtext=configtext.replace('#terminal_port = 0xE9','terminal_port = 0xE9')
    config=run/'martypc.toml';config.write_text(configtext)
    log=run/'probe.log';started=time.monotonic()
    with log.open('wb') as output:
        proc=subprocess.Popen([str(ROOT/'external/martypc/target/release/martypc.exe'),
                               '--configfile',str(config),'--nosound'],cwd=run,
                              stdout=output,stderr=subprocess.STDOUT,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
                              env={**os.environ,'RUST_LOG':'info'})
        print(f'MartyPC PID {proc.pid}; log {log}',flush=True)
        try:code=proc.wait(timeout=900 if args.real else 120)
        except subprocess.TimeoutExpired:
            proc.terminate();code=proc.wait(timeout=10)
    text=log.read_text(errors='replace')
    import re
    markers=re.findall(r'(?m)^([SE]\d\d)\r?$',text)
    nums=[r['number'] for kind in (False,True) for r in rows if r['display'].startswith('Composite')==kind]
    if not args.real:nums += [1,24]
    expected=[f'{event}{n:02}' for n in nums for event in ('S','E')]
    report={'success':markers==expected and bool(re.search(r'(?m)^Z\r?$',text)),
            'real_exports':args.real,'markers':markers,'expected':expected,
            'seconds':round(time.monotonic()-started,3),'exit_code':code,
            'disk_sha256':hashlib.sha256(disk.read_bytes()).hexdigest()}
    (run/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    if not report['success']:
        print(text[-4000:]);raise SystemExit(1)
if __name__=='__main__':main()
