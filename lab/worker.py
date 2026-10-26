import json, os, pathlib, re, sys, time
import requests
FIELDS=['goal','changed_files','current_status','remaining_work','verification','risks','next_steps']
SYSTEM='''Return exactly one JSON object per turn. Commands: {"op":"read_file","path":"app/calculator.py"}, {"op":"read_file","path":"HANDOFF.md"}, {"op":"write_file","path":"app/calculator.py","content":"FULL FILE"}, {"op":"write_file","path":"HANDOFF.md","content":"FULL FILE"}, {"op":"finish"}. No shell. Make small correct changes. The controller handles git and tests.'''
TASK={'A':'Fix subtract, implement multiply and divide (zero denominator raises ZeroDivisionError). Fill HANDOFF.md with nonempty lines goal:, changed_files:, current_status:, remaining_work:, verification:, risks:, next_steps:. Finish.', 'B':'Review the checked-out source and seven-field HANDOFF.md. Independently complete or correct calculator implementation, then finish. You cannot see A chat.'}
def main():
    role,work,out=sys.argv[1:]; root=pathlib.Path(work); limits=json.load(open('/project/config/limits.json')); policy=json.load(open('/project/config/tool_policy.json'))
    history=[{'role':'system','content':SYSTEM},{'role':'user','content':TASK[role]}]
    start=time.monotonic(); calls=actions=tokens=0; status='budget_exhausted'; errors=[]; known=True
    try:
        while calls<limits['max_calls_per_agent'] and actions<limits['max_actions_per_agent'] and tokens<limits['max_output_tokens_per_agent']:
            remaining=limits['max_seconds_per_agent']-(time.monotonic()-start)
            if remaining<=0: status='time_limit'; break
            r=requests.post(os.getenv('OLLAMA_URL','http://ollama:11434')+'/api/chat',json={'model':os.getenv('OLLAMA_MODEL','qwen2.5-coder:1.5b'),'messages':history,'stream':False,'format':'json','options':{'temperature':0,'num_predict':min(768,limits['max_output_tokens_per_agent']-tokens)}},timeout=(10,max(1,min(120,remaining))))
            r.raise_for_status(); data=r.json(); calls+=1; n=data.get('eval_count'); known &= isinstance(n,int); tokens+=n if isinstance(n,int) else 768
            raw=data['message']['content']; history.append({'role':'assistant','content':raw})
            try:
                cmd=json.loads(raw); op=cmd['op']
                if op=='finish': status='finished'; break
                if op not in ('read_file','write_file'): raise ValueError('invalid operation')
                path=cmd['path']; allowed=policy['read_file'] if op=='read_file' else policy['write_'+role]
                if path not in allowed: raise ValueError('path denied')
                target=root/path
                if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()): raise ValueError('unsafe path')
                actions+=1
                if op=='read_file': answer=target.read_text()
                else:
                    content=cmd['content']
                    if not isinstance(content,str) or len(content.encode())>16000: raise ValueError('content too large')
                    if path=='HANDOFF.md' and not all(re.search(r'(?m)^'+f+r':\s*\S',content) for f in FIELDS): raise ValueError('seven nonempty fields required')
                    target.write_text(content); answer='write OK'
            except Exception as e: answer='ERROR '+str(e); errors.append(answer)
            history.append({'role':'user','content':answer[:12000]})
    except Exception as e: status='error'; errors.append(str(e))
    pathlib.Path(out).write_text(json.dumps({'status':status,'calls':calls,'actions':actions,'tokens_accounted':tokens,'token_count_known':known,'seconds':round(time.monotonic()-start,2),'errors':errors}))
if __name__=='__main__': main()
