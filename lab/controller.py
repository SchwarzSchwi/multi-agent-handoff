import ast,csv,hashlib,json,os,pathlib,re,shutil,subprocess,sys,tempfile,time
P=pathlib.Path('/project'); O=pathlib.Path('/output'); F=['goal','changed_files','current_status','remaining_work','verification','risks','next_steps']
def run(args,cwd,timeout=30,check=True):
    return subprocess.run(args,cwd=cwd,timeout=timeout,check=check,capture_output=True,text=True)
def git(cwd,*args): return run(['git',*args],cwd).stdout.strip()
def handoff(path):
    s=path.read_text(); return all(re.search(r'(?m)^'+f+r':\s*\S',s) for f in F)
def evaluate(repo):
    source=(repo/'app/calculator.py').read_text()
    try: names={n.name for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
    except SyntaxError: names=set()
    # Run generated code in a separate low-privilege subprocess with timeout.
    # This is NOT a security sandbox for adversarial code.
    cases={'add':'assert add(2,3)==5','subtract':'assert subtract(7,4)==3','multiply':'assert multiply(6,7)==42','divide':'assert divide(8,2)==4','zero_division':'\ntry: divide(1,0)\nexcept ZeroDivisionError: pass\nelse: raise AssertionError("no zero division error")'}
    passed={}
    for k,body in cases.items():
        code='from app.calculator import add,subtract,multiply,divide\n'+body+'\n'
        r=run([sys.executable,'-c',code],repo,timeout=10,check=False); passed[k]=r.returncode==0
    clean=not git(repo,'status','--porcelain')
    return [{'id':f'T{i:02}','check':c,'passed':(c.split(':')[1] in names if c.startswith('function:') else passed[c.split(':')[1]] if c.startswith('behavior:') else clean)} for i,c in enumerate(json.loads((P/'config/checks.json').read_text()),1)]
def main():
    O.mkdir(exist_ok=True,parents=True)
    limits=json.loads((P/'config/limits.json').read_text()); paths=[P/'config'/n for n in ['checks.json','limits.json','tool_policy.json']]
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}; (O/'frozen_manifest.json').write_text(json.dumps(manifest,indent=2))
    states=[]; workers=[]; errors=[]; checks=[]; start=time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        base=pathlib.Path(tmp); origin=base/'origin'; shutil.copytree(P/'seed',origin)
        git(origin,'init','-q'); git(origin,'config','user.name','Lab'); git(origin,'config','user.email','lab@example.invalid'); git(origin,'add','.'); git(origin,'commit','-qm','seed')
        try:
            for role in ['A','B']:
                if role=='B' and states!=['A_START','A_HANDOFF']: raise RuntimeError('invalid state transition')
                work=base/('agent-'+role.lower()); git(base,'clone','-q',str(origin),str(work))
                states.append(role+'_START')
                if role=='B' and not handoff(work/'HANDOFF.md'): raise RuntimeError('handoff not reproduced')
                out=base/(role+'.json')
                run([sys.executable,'-m','lab.worker',role,str(work),str(out)],P,timeout=limits['max_seconds_per_agent']+15)
                workers.append(json.loads(out.read_text()))
                if role=='A':
                    if not handoff(work/'HANDOFF.md'): raise RuntimeError('A handoff invalid')
                    git(work,'add','app/calculator.py','HANDOFF.md'); git(work,'-c','user.name=Lab','-c','user.email=lab@example.invalid','commit','-qm','A handoff'); git(work,'push','origin','HEAD'); states.append('A_HANDOFF')
                else:
                    git(work,'add','app/calculator.py');
                    if git(work,'status','--porcelain'): git(work,'-c','user.name=Lab','-c','user.email=lab@example.invalid','commit','-qm','B completion')
                    states.append('B_DONE'); checks=evaluate(work)
                    dest=O/'final-repo'; shutil.rmtree(dest,ignore_errors=True); shutil.copytree(work,dest,ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache'))
            if any(hashlib.sha256(p.read_bytes()).hexdigest()!=manifest[p.name] for p in paths): raise RuntimeError('frozen config changed')
        except Exception as e: errors.append(str(e))
    if time.monotonic()-start>limits['max_total_seconds']: errors.append('total time limit exceeded')
    with (O/'metrics.csv').open('w',newline='') as f:
        w=csv.writer(f); w.writerow(['blind_id','calls','actions','tokens_accounted','token_count_known','seconds','status'])
        for i,a in enumerate(workers): w.writerow([f'P{i+1:02}',a['calls'],a['actions'],a['tokens_accounted'],a['token_count_known'],a['seconds'],a['status']])
    report={'states':states,'expected':['A_START','A_HANDOFF','B_START','B_DONE'],'handoff_fields':F,'checks':checks,'passed':sum(x['passed'] for x in checks),'total_checks':10,'workers':workers,'errors':errors,'success':len(states)==4 and len(checks)==10 and all(x['passed'] for x in checks) and not errors}
    (O/'results.json').write_text(json.dumps(report,indent=2)); (O/'events.jsonl').write_text(''.join(json.dumps({'index':i,'event':s})+'\n' for i,s in enumerate(states)))
    print(json.dumps(report,indent=2)); sys.exit(0 if report['success'] else 1)
if __name__=='__main__': main()
