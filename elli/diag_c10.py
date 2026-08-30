import pefile,os,sys,glob
out = []
sp = sys.prefix
c10 = os.path.join(sp,'Lib','site-packages','torch','lib','c10.dll')
out.append(f"C10_PATH: {c10}")
out.append(f"EXISTS: {os.path.exists(c10)}")
if not os.path.exists(c10):
    open('diag_c10_output.txt','w').write('\n'.join(out))
    sys.exit(1)
pe = pefile.PE(c10)
imports = [e.dll.decode('utf-8',errors='ignore') for e in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[])]
out.append(f"IMPORTS_COUNT: {len(imports)}")
for d in imports:
    out.append(d)

paths = os.environ.get('PATH','').split(';')
out.append('\n--- PATH check ---')
for d in imports:
    found = []
    for p in paths:
        if not p: continue
        fp = os.path.join(p,d)
        if os.path.exists(fp):
            found.append(fp)
            if len(found) >= 5: break
    out.append(f"{d} {'FOUND' if found else 'MISSING'}")
    if found:
        for f in found[:5]:
            out.append('  '+f)

open('diag_c10_output.txt','w',encoding='utf-8').write('\n'.join(out))
print('WROTE diag_c10_output.txt')
