#!/usr/bin/env python3
"""Reference task registry, dependency checker and fail-closed local test runner.
Not a secure review/approval/GitHub orchestration engine.
"""
import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import yaml
from readiness import PROTECTED_TASKS, ReadinessError, verify_readiness

KIT_ROOT = Path(__file__).resolve().parents[1]
ROOT = KIT_ROOT.parent
ID_PATTERN = re.compile(r'^[A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d{3}$')

def tasks_root(root=ROOT):
    """Return the integrated task registry while supporting a standalone kit."""
    nested=root/'movie-rec-agent-starter'/'tasks'
    return nested if nested.is_dir() else root/'tasks'

def now():
    return datetime.now(timezone.utc).isoformat()

def load_tasks(root=ROOT):
    registry=tasks_root(root)
    index=yaml.safe_load((registry/'index.yaml').read_text(encoding='utf-8'))
    tasks={}
    for entry in index['tasks']:
        tid=entry['id']
        if not ID_PATTERN.fullmatch(tid) or tid in tasks or entry['file'] != tid+'.yaml':
            raise ValueError('Invalid or duplicate task ID/file '+str(entry))
        task=yaml.safe_load((registry/entry['file']).read_text(encoding='utf-8'))
        if task['id']!=tid: raise ValueError('Task ID mismatch '+tid)
        for key, task_key in (('dependencies','dependencies'),('slides','source_slides'),('type','type')):
            if entry.get(key) != task.get(task_key):
                raise ValueError('Index/contract mismatch '+tid+': '+key)
        tasks[tid]=task
    return tasks

def validate_tasks(tasks):
    errors=[]
    for tid,t in tasks.items():
        if t.get('type') not in ('infra','data','ml','api','ops'):
            errors.append(tid+': unknown type')
        paths=t.get('allowed_paths',[])
        if not paths or any(not isinstance(p,str) or not p or Path(p).is_absolute() or '..' in Path(p).parts or (not p.endswith('/') and '/' in p) for p in paths):
            errors.append(tid+': allowed_paths missing/invalid')
        if not t.get('source_slides') or any(not isinstance(x,int) or x<2 or x>11 for x in t['source_slides']):
            errors.append(tid+': slide reference invalid')
        if not {'independent_review','github_ci'}.issubset(t.get('required_checks',[])):
            errors.append(tid+': missing review or CI gate')
        for dep in t.get('dependencies',[]):
            if dep not in tasks or dep==tid: errors.append(tid+': unknown/self dependency '+str(dep))
        if not t.get('acceptance_criteria'): errors.append(tid+': missing acceptance criteria')
        seen=set()
        for ac in t.get('acceptance_criteria',[]):
            acid=ac.get('id')
            if not isinstance(acid,str) or not acid.startswith(tid+'-AC-') or acid in seen:
                errors.append(tid+': duplicate or invalid AC ID')
            seen.add(acid)
            p=ac.get('planned_test')
            if not isinstance(p,str) or not p.startswith('tests/') or not p.endswith('.py') or '..' in Path(p).parts:
                errors.append(tid+': invalid test path')
            if not re.fullmatch(r'test_[a-z0-9_]+',ac.get('test_case','')):
                errors.append(tid+': missing named test_case')
    done=set(); active=set()
    def visit(tid):
        if tid in active:
            errors.append('Cycle detected involving '+tid)
            return
        if tid in done: return
        active.add(tid)
        for dep in tasks[tid].get('dependencies',[]):
            if dep in tasks: visit(dep)
        active.remove(tid);done.add(tid)
    for tid in tasks: visit(tid)
    return errors

def read_state(root=ROOT):
    p=root/'.runtime/state.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'version':1,'tasks':{}}

def write_state(s,root=ROOT):
    p=root/'.runtime/state.json';p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix('.tmp');temp.write_text(json.dumps(s,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');temp.replace(p)

def status(tid,state):
    return state.get('tasks',{}).get(tid,{}).get('status','PLANNED')

def assert_ready(tasks,tid,state,approvals=(),root=ROOT):
    approved=set(approvals)
    if tid in PROTECTED_TASKS:
        approved=verify_readiness(tasks,tid,root)
    if not all(status(dep,state)=='VERIFIED' for dep in tasks[tid].get('dependencies',[])):
        raise ValueError('Task blocked by dependencies')
    if not all(d in approved for d in tasks[tid].get('blocked_on_decision',[])):
        raise ValueError('Task blocked by open business decisions')

def eligible_tasks(tasks,state,approvals=(),root=ROOT):
    approved=set(approvals)
    eligible=[]
    for tid in tasks:
        if status(tid,state) not in ('PLANNED','READY'):continue
        try:assert_ready(tasks,tid,state,approved,root)
        except ValueError:continue
        eligible.append(tid)
    return eligible

def local_tests_for_task(task,root=ROOT):
    selections=[]
    for ac in task['acceptance_criteria']:
        rel=ac['planned_test']; p=root/rel
        if not p.is_file(): raise FileNotFoundError('Missing required acceptance test: '+rel)
        tree=ast.parse(p.read_text(encoding='utf-8'))
        available={n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        if ac['test_case'] not in available:
            raise ValueError('Missing test function '+rel+'::'+ac['test_case'])
        selections.append(rel+'::'+ac['test_case'])
    return selections

def run_local(task,root=ROOT):
    # This direct Python entrypoint is guarded as well as the CLI. Re-check on
    # resume: an old RUNNING state must not authorize changed data/evidence.
    if task['id'] in PROTECTED_TASKS:
        tasks=load_tasks(root)
        assert_ready(tasks,task['id'],read_state(root),root=root)
        if task != tasks[task['id']]:
            raise ValueError('Runner task differs from registered contract')
    tid=task['id'];folder=root/'.runtime/evidence'/tid;folder.mkdir(parents=True,exist_ok=True)
    suffix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report_path=folder/('local-'+suffix+'.json');log_path=folder/('local-'+suffix+'.log')
    report={'task_id':tid,'timestamp':now(),'result':'FAILED','command':None,'exit_code':None,
            'note':'This runner checks named pytest tests only; does not certify independent review, CI or business semantics.'}
    exit_code=1
    try:
        tests=local_tests_for_task(task,root)
        cmd=[sys.executable,'-m','pytest','-q',*tests]
        report['command']=cmd
        proc=subprocess.run(cmd,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
        log_path.write_text(proc.stdout,encoding='utf-8')
        exit_code=proc.returncode
        report['exit_code']=exit_code
        report['result']='PASSED' if exit_code==0 else 'FAILED'
    except (OSError,ValueError,SyntaxError,subprocess.TimeoutExpired) as exc:
        report['error']=str(exc);log_path.write_text(str(exc)+'\n',encoding='utf-8')
    report['log_path']=str(log_path.relative_to(root))
    report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return exit_code,report,str(report_path.relative_to(root))

def main(argv=None):
    cli=argparse.ArgumentParser(description='Reference MovieRec task CLI')
    sub=cli.add_subparsers(dest='action',required=True)
    for action in ('validate','list','next'):sub.add_parser(action)
    for action in ('show','start','run-local'):sub.add_parser(action).add_argument('task_id')
    args=cli.parse_args(argv)
    try:
        tasks=load_tasks();errors=validate_tasks(tasks)
        if errors:
            for e in errors:print('ERROR:',e,file=sys.stderr)
            return 2
        if args.action=='validate':print(f'PASS: {len(tasks)} task contracts valid; no dependency cycles');return 0
        state=read_state()
        if args.action=='list':
            for tid,t in tasks.items():print(tid,status(tid,state),t['title'])
            return 0
        if args.action=='next':
            print('\n'.join(eligible_tasks(tasks,state)) or 'No eligible tasks (dependencies/decisions blocked)')
            return 0
        tid=args.task_id
        if tid not in tasks:raise ValueError('Unknown task '+tid)
        if args.action=='show':
            print(yaml.safe_dump(tasks[tid],sort_keys=False,allow_unicode=True));print('RUNTIME:',status(tid,state));return 0
        if args.action=='start':
            if status(tid,state) not in ('PLANNED','READY'):raise ValueError('Task is not PLANNED or READY')
            assert_ready(tasks,tid,state)
            old=state['tasks'].get(tid,{})
            state['tasks'][tid]={'status':'RUNNING','attempt':old.get('attempt',0)+1,'started_at':now()}
            write_state(state);print(tid,'RUNNING (local demo)');return 0
        if args.action=='run-local':
            if status(tid,state)!='RUNNING':raise ValueError('Must start task before run-local')
            code,report,path=run_local(tasks[tid]);state['tasks'][tid].update(status='LOCAL_VERIFIED' if code==0 else 'NEEDS_REWORK',last_report=path,updated_at=now())
            write_state(state);print(tid,report['result'],'exit',code,'report',path)
            print('Not yet independently reviewed, committed, pushed or GitHub CI verified.')
            return code
    except (ValueError,OSError,KeyError,yaml.YAMLError,json.JSONDecodeError) as exc:
        print('ERROR:',exc,file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
