"""Compare steamworks/steamworks.odin against a Steamworks SDK's steam_api.json.

The binding is curated by hand (shortened names, Odin types, comments), so it is
not regenerated wholesale. This tool finds what an SDK update changed and emits
enum bodies in the binding's style so they are not typed by hand.

Usage (from the repository root):
    STEAM_API_JSON=<sdk>/public/steam/steam_api.json python3 tools/sdk_delta.py <mode> [args]

Modes:
    procs                       flat functions added, gone, or with changed parameters
    types                       enums and structs added or with changed fields
    enumnums                    enum values added or removed, compared by value
    orphans                     declared types and callback IDs absent from the SDK
    cmpenum NAME PREFIX         names a regenerated enum would rename or add
    emit NAME PREFIX            print an enum in the binding's style
    replace-enum NAME PREFIX    regenerate an enum in place
    replace-enum-as NAME PREFIX ODIN_NAME [OLD_ODIN_NAME]
    linkcheck EXPORTS           foreign declarations missing from a library's
                                export list (one symbol per line; e.g. from
                                nm -D --defined-only <lib> | awk '{print $3}')
"""
import json,os,re,sys
BINDING=os.environ.get('BINDING', 'steamworks/steamworks.odin')
d=json.load(open(os.environ['STEAM_API_JSON']))
src=open(BINDING).read().split('\n')
# foreign symbols: link symbol -> param list
odin={}; prefix=None; inblock=False
for line in src:
    m=re.match(r'@\(link_prefix\s*=\s*"([^"]*)"',line)
    if m: prefix=m.group(1); continue
    if line.startswith('foreign lib {'): inblock=True; continue
    if inblock and line.startswith('}'): inblock=False; prefix=None; continue
    if inblock:
        m=re.match(r'\s+(\w+)\s*::\s*proc\s*\((.*)\)\s*(->\s*(.+?))?\s*---',line)
        if m:
            params=[p.split(':')[0].strip() for p in m.group(2).split(',') if ':' in p]
            odin[(prefix or '')+m.group(1)]=(params,m.group(4),line.strip())
json_syms={}
for i in d['interfaces']:
    for a in i.get('accessors',[]): json_syms[a['name_flat']]=([],i['classname'])
    for m in i['methods']:
        json_syms[m['methodname_flat'].replace('GetISteam','GetI')]=([p['paramname'] for p in m['params']],m['returntype'])
for s in d['structs']+d['callback_structs']:
    for m in s.get('methods',[]): json_syms[m['methodname_flat']]=([p['paramname'] for p in m['params']],m['returntype'])
mode=sys.argv[1]
if mode=='procs':
    for k in sorted(set(json_syms)-set(odin)): print('ADD ',k,json_syms[k])
    for k in sorted(set(odin)-set(json_syms)):
        if k.startswith('SteamAPI_I') or re.search(r'_v\d+$',k): print('GONE',k)
    for k in sorted(set(odin)&set(json_syms)):
        jp=json_syms[k][0]; op=odin[k][0]
        if op and op[0]=='self': op=op[1:]
        if jp!=op: print('SIG ',k,'json',jp,'odin',op)
text='\n'.join(src)
def odname(n): return re.sub(r'_t$','',n)
if mode=='types':
    for e in d['enums']+[e for i in d['interfaces'] for e in i.get('enums',[])]:
        n=e['enumname']; m=re.search(r'^'+re.escape(n)+r' :: enum[^{]*\{(.*?)^\}',text,re.S|re.M)
        if not m: print('ENUM-ADD',n,len(e['values'])); continue
        body=m.group(1); cnt=len(re.findall(r'^\s+\w+\s*=',body,re.M))
        if cnt!=len(e['values']): print('ENUM-DIFF',n,'json',len(e['values']),'odin',cnt)
    for s in d['structs']+d['callback_structs']:
        n=odname(s['struct']); m=re.search(r'^'+re.escape(n)+r' :: struct[^{]*\{(.*?)^\}',text,re.S|re.M)
        if not m: print('STRUCT-ADD',s['struct'],[f['fieldname'] for f in s['fields']]); continue
        of=re.findall(r'^\s+(\w+)\s*:',m.group(1),re.M)
        jf=[re.sub(r'^m_','',f['fieldname']) for f in s['fields']]
        if of!=jf: print('STRUCT-DIFF',n,'json',jf,'odin',of)
    for c in d['consts']:
        pass
def strip_value(enumname, n):
    for p in ('k_'+enumname+'_', 'k_'+enumname, 'k_'+enumname[1:]+'_', 'k_'+enumname[1:], 'k_'):
        if n.startswith(p): return n[len(p):]
    return n
if mode=='enumvals':
    for e in d['enums']+[e for i in d['interfaces'] for e in i.get('enums',[])]:
        n=e['enumname']; m=re.search(r'^'+re.escape(n)+r' :: enum[^{]*\{(.*?)^\}',text,re.S|re.M)
        if not m: continue
        ov=dict(re.findall(r'^\s+(\w+)\s*=\s*([^,/]+?)\s*,',m.group(1),re.M))
        jv={strip_value(n,v['name']):v['value'] for v in e['values']}
        miss=[(k,v) for k,v in jv.items() if k not in ov]; extra=[k for k in ov if k not in jv]
        chg=[(k,ov[k],jv[k]) for k in jv if k in ov and ov[k].strip()!=jv[k].strip()]
        if miss or extra or chg: print('##',n,'missing',miss,'extra',extra,'changed',chg)
if mode=='enumnums':
    for e in d['enums']+[e for i in d['interfaces'] for e in i.get('enums',[])]:
        n=e['enumname']; m=re.search(r'^'+re.escape(n)+r' :: enum[^{]*\{(.*?)^\}',text,re.S|re.M)
        if not m: continue
        ov=re.findall(r'^\s+(\w+)\s*=\s*(-?\d+)\s*,',m.group(1),re.M)
        onums={int(v) for _,v in ov}
        if not ov: print('## (non-literal)',n); continue
        new=[(strip_value(n,v['name']),v['value']) for v in e['values'] if re.fullmatch(r'-?\d+',v['value']) and int(v['value']) not in onums]
        jn={int(v['value']) for v in e['values'] if re.fullmatch(r'-?\d+',v['value'])}
        gone=[k for k,v in ov if int(v) not in jn]
        if new or gone: print('##',n,'new',new,'gone',gone)
if mode=='orphans':
    names={odname(s['struct']) for s in d['structs']+d['callback_structs']}|{s['struct'] for s in d['structs']+d['callback_structs']}
    enames={e['enumname'] for e in d['enums']}|{i['classname']+'_'+e['enumname'] for i in d['interfaces'] for e in i.get('enums',[])}|{e['enumname'] for i in d['interfaces'] for e in i.get('enums',[])}
    for m in re.finditer(r'^(\w+) :: struct',text,re.M):
        if m.group(1) not in names: print('STRUCT',m.group(1))
    for m in re.finditer(r'^(\w+) :: enum',text,re.M):
        if m.group(1) not in enames: print('ENUM',m.group(1))
    cb={odname(s['struct']) for s in d['callback_structs']}
    im=re.search(r'^ICallback :: enum[^{]*\{(.*?)^\}',text,re.S|re.M).group(1)
    for n in re.findall(r'^\s+(\w+)\s*=',im,re.M):
        if n not in cb: print('ICALLBACK',n)
    for s in d['callback_structs']:
        if odname(s['struct']) not in re.findall(r'^\s+(\w+)\s*=',im,re.M): print('ICALLBACK-MISSING',odname(s['struct']),s['callback_id'])
def emit_enum(name, prefix, extra_values=()):
    e=[x for x in d['enums']+[e for i in d['interfaces'] for e in i.get('enums',[])] if x['enumname']==name][0]
    vals=[(v['name'][len(prefix):] if v['name'].startswith(prefix) else v['name'], v['value']) for v in e['values']]
    w=max(len(n) for n,_ in vals)
    return name+' :: enum i32 {\n'+''.join('    %s = %s,\n'%(n.ljust(w),v) for n,v in vals)+'}\n'
if mode=='emit':
    print(emit_enum(sys.argv[2], sys.argv[3]))
if mode=='cmpenum':
    name,prefix=sys.argv[2],sys.argv[3]
    e=[x for x in d['enums'] if x['enumname']==name][0]
    gen=[(v['name'][len(prefix):] if v['name'].startswith(prefix) else v['name'], v['value']) for v in e['values']]
    body=re.search(r'^'+name+r' :: enum[^{]*\{(.*?)^\}',text,re.S|re.M).group(1)
    cur=re.findall(r'^\s+(\w+)\s*=\s*(-?\w+)\s*,',body,re.M)
    cm=dict(cur); gm=dict(gen)
    print('renamed/removed:',[(k,v) for k,v in cur if gm.get(k)!=v])
    print('added:',len([k for k in gm if k not in cm]))
if mode=='replace-enum':
    name,prefix=sys.argv[2],sys.argv[3]
    p=BINDING
    src_text=open(p).read()
    m=re.search(r'^'+name+r' :: enum[^{]*\{.*?^\}\n',src_text,re.S|re.M)
    src_text=src_text[:m.start()]+emit_enum(name,prefix)+src_text[m.end():]
    open(p,'w').write(src_text)
if mode=='replace-enum-as':
    name,prefix,odin_name=sys.argv[2],sys.argv[3],sys.argv[4]
    p=BINDING
    s=open(p).read()
    m=re.search(r'^'+re.escape(sys.argv[5] if len(sys.argv)>5 else odin_name)+r' :: enum[^{]*\{.*?^\}\n',s,re.S|re.M)
    s=s[:m.start()]+emit_enum(name,prefix).replace(name+' :: enum',odin_name+' :: enum',1)+s[m.end():]
    open(p,'w').write(s)
if mode=='linkcheck':
    ex=set(open(sys.argv[2]).read().split())
    missing=[k for k in odin if k not in ex]
    print(len(odin),'declared;',len(missing),'unresolved')
    for k in missing: print('  ',k)
