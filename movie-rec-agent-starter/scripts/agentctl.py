#!/usr/bin/env python3
"""MovieRec development tasks: dependencies, tests and published Git receipts."""
import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import yaml
from readiness import PROTECTED_TASKS, verify_readiness, digest, read_json

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
        if not paths or any(not isinstance(p,str) or not p or Path(p).is_absolute() or ':' in p or '..' in Path(p).parts for p in paths):
            errors.append(tid+': allowed_paths missing/invalid')
        if not t.get('source_slides') or any(not isinstance(x,int) or x<2 or x>11 for x in t['source_slides']):
            errors.append(tid+': slide reference invalid')
        if not {'unit_tests','integration_tests'}.issubset(t.get('required_checks',[])):
            errors.append(tid+': missing automated test checks')
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
    # Historical VERIFIED is deliberately not migrated to DONE.
    return state.get('tasks',{}).get(tid,{}).get('status','ELIGIBLE')

def git(root, *args):
    proc=subprocess.run(['git', *args],cwd=root,text=True,capture_output=True)
    if proc.returncode:
        raise ValueError(proc.stderr.strip() or 'Git command failed: '+ ' '.join(args))
    return proc.stdout.strip()

def revision(root):
    branch=git(root,'branch','--show-current')
    if not branch.startswith('feature/'):
        raise ValueError('Expected feature/ branch; main and detached HEAD are blocked')
    return {'branch':branch,'head_sha':git(root,'rev-parse','HEAD'),
            'repository':git(root,'remote','get-url','origin')}

def tree_inputs(root, revision='HEAD'):
    return git(root,'ls-tree','-r',revision)

def clean_tracked(root):
    git(root,'diff','--quiet','HEAD','--')

def remote_sha(root, branch):
    line=git(root,'ls-remote','--exit-code','origin','refs/heads/'+branch)
    fields=line.split()
    if len(fields)!=2 or fields[1]!='refs/heads/'+branch:
        raise ValueError('Remote feature branch is missing or ambiguous')
    return fields[0]

def approved_decisions(root):
    path=root/'movie-rec-agent-starter/docs/business/approved_decisions.yaml'
    data=yaml.safe_load(path.read_text(encoding='utf-8')) if path.exists() else {}
    return {key for key,value in data.get('decisions',{}).items()
            if value.get('status')=='APPROVED' and value.get('source')}

def verify_completion(tasks, tid, root, *, active=None):
    """Local receipts are audit records, not signatures or a security boundary.

    Validate real Git history and the remote on every dependency check. A forged
    YAML/runtime status has no effect on eligibility.
    """
    active=set() if active is None else active
    if tid in active: raise ValueError('Dependency cycle')
    active.add(tid)
    try:
        proof=read_json(root/'.runtime/evidence'/tid/'completion.json')
        rev=revision(root)
        if proof.get('task_id')!=tid or proof.get('status')!='DONE' or proof.get('repository')!=rev['repository']:
            raise ValueError('Missing matching completion evidence for '+tid)
        sha=proof['head_sha']
        if not re.fullmatch(r'[0-9a-f]{40}',sha):raise ValueError('Invalid completion SHA')
        git(root,'merge-base','--is-ancestor',sha,'HEAD')
        git(root,'merge-base','--is-ancestor',sha,remote_sha(root,proof['branch']))
        if proof.get('tree_sha')!=git(root,'rev-parse',sha+'^{tree}'):
            raise ValueError('Completion tree mismatch')
        report_path=root/proof['report']
        if not report_path.resolve().is_relative_to(root.resolve()) or digest(report_path)!=proof['report_sha256']:
            raise ValueError('Completion report changed')
        report=read_json(report_path)
        log=root/report['log_path']
        if (report.get('result')!='PASSED' or type(report.get('exit_code')) is not int or report['exit_code']!=0
                or report.get('task_id')!=tid or report.get('head_sha')!=sha
                or report.get('command')!=test_command(tasks[tid],root)
                or not log.resolve().is_relative_to(root.resolve()) or digest(log)!=report['log_sha256']):
            raise ValueError('Missing or changed successful tests for '+tid)
        if report.get('inputs')!=tree_inputs(root,sha):raise ValueError('Tested source tree mismatch')
        if tid=='DATA-QUALITY-001':
            from readiness import artifact
            artifact(root,proof.get('dataset_manifest'))
        if '['+tid+']' not in git(root,'show','-s','--format=%B',sha):
            raise ValueError('Commit does not identify '+tid)
        for dep in tasks[tid].get('dependencies',[]):verify_completion(tasks,dep,root,active=active)
        return proof
    finally:
        active.remove(tid)

def assert_ready(tasks,tid,state,approvals=None,root=ROOT):
    approved=approved_decisions(root) if approvals is None else set(approvals)
    for dep in tasks[tid].get('dependencies',[]):verify_completion(tasks,dep,root)
    if not all(d in approved for d in tasks[tid].get('blocked_on_decision',[])):
        raise ValueError('Task blocked by open business decisions')
    if tid in PROTECTED_TASKS:verify_readiness(tasks,tid,root)

def eligible_tasks(tasks,state,approvals=None,root=ROOT):
    eligible=[]
    for tid in tasks:
        try:
            verify_completion(tasks,tid,root)
            continue
        except (ValueError,OSError,KeyError):pass
        try:assert_ready(tasks,tid,state,approvals,root)
        except (ValueError,OSError,KeyError):continue
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

def test_command(task,root=ROOT):
    return [sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
            *local_tests_for_task(task,root),*task.get('test_suites',[])]

def run_local(task,root=ROOT):
    # This direct Python entrypoint is guarded as well as the CLI. Re-check on
    # resume: an old RUNNING state must not authorize changed data/evidence.
    tasks=load_tasks(root)
    assert_ready(tasks,task['id'],read_state(root),root=root)
    if task != tasks[task['id']]:raise ValueError('Runner task differs from registered contract')
    tid=task['id'];folder=root/'.runtime/evidence'/tid;folder.mkdir(parents=True,exist_ok=True)
    suffix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report_path=folder/('local-'+suffix+'.json');log_path=folder/('local-'+suffix+'.log')
    report={'task_id':tid,'timestamp':now(),'result':'FAILED','command':None,'exit_code':None,
            'note':'Tests only; completion additionally requires scoped commit and confirmed remote SHA.'}
    exit_code=1
    try:
        cmd=test_command(task,root)
        report['command']=cmd
        report['head_sha']=git(root,'rev-parse','HEAD')
        # Staged candidates are allowed before commit. Record the index and check
        # that execution did not silently change the candidate source tree.
        git(root,'diff','--quiet','--')
        inputs=git(root,'ls-files','--stage')
        report['inputs']=tree_inputs(root) if not git(root,'diff','--cached','--name-only') else None
        proc=subprocess.run(cmd,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
        log_path.write_text(proc.stdout,encoding='utf-8')
        exit_code=proc.returncode
        git(root,'diff','--quiet','--')
        if inputs!=git(root,'ls-files','--stage'):raise ValueError('Index changed during tests')
        report['exit_code']=exit_code
        report['result']='PASSED' if exit_code==0 else 'FAILED'
    except (OSError,ValueError,SyntaxError,subprocess.TimeoutExpired) as exc:
        exit_code=1
        report['result']='FAILED'
        report['error']=str(exc);log_path.write_text(str(exc)+'\n',encoding='utf-8')
    report['log_path']=log_path.relative_to(root).as_posix()
    report['log_sha256']=digest(log_path)
    report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return exit_code,report,str(report_path.relative_to(root))

def complete(tasks,tid,root=ROOT):
    """Re-run tests at the committed tree, then confirm the actual pushed SHA."""
    assert_ready(tasks,tid,read_state(root),root=root)
    rev=revision(root);clean_tracked(root)
    git(root,'diff','--check');git(root,'diff','--cached','--check')
    message=git(root,'show','-s','--format=%B','HEAD')
    if '['+tid+']' not in message:raise ValueError('HEAD commit must identify ['+tid+']')
    from git_preflight import check_allowed_paths, check_safe_paths
    changed=git(root,'diff-tree','--root','--no-commit-id','--name-only','-r','HEAD').splitlines()
    if not changed or check_allowed_paths(changed,tasks[tid]['allowed_paths']) or check_safe_paths(changed):
        raise ValueError('Commit contains files outside task scope or unsafe artifacts')
    if remote_sha(root,rev['branch'])!=rev['head_sha']:raise ValueError('Remote SHA differs from local HEAD; push first')
    code,report,path=run_local(tasks[tid],root)
    if code:raise ValueError('Acceptance tests failed; see '+path)
    clean_tracked(root)
    if revision(root)!=rev or remote_sha(root,rev['branch'])!=rev['head_sha']:
        raise ValueError('Local or remote revision changed during completion')
    proof={**rev,'task_id':tid,'status':'DONE','tree_sha':git(root,'rev-parse','HEAD^{tree}'),
           'changed_files':changed,'report':Path(path).as_posix(),'report_sha256':digest(root/path),
           'completed_at':now(),'ci':'NOT_CHECKED (reported separately)'}
    if tid=='DATA-QUALITY-001':
        from readiness import verify_manifest
        manifest=root/'.runtime/dataset-manifest.json'
        reference={'path':manifest.relative_to(root).as_posix(),'sha256':digest(manifest)}
        verify_manifest(root,reference)
        proof['dataset_manifest']=reference
    dest=root/'.runtime/evidence'/tid/'completion.json'
    dest.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    state=read_state(root)
    previous=state['tasks'].get(tid,{})
    state['tasks'][tid]={**previous,'status':'DONE','head_sha':rev['head_sha'],'completion':dest.relative_to(root).as_posix()}
    write_state(state,root)
    return proof

def display_status(tasks,tid,state,root=ROOT):
    try:
        verify_completion(tasks,tid,root)
        return 'DONE'
    except (ValueError,OSError,KeyError):pass
    try:assert_ready(tasks,tid,state,root=root)
    except (ValueError,OSError,KeyError):return 'BLOCKED'
    cached=status(tid,state)
    return cached if cached in ('IMPLEMENT','TEST','NEEDS_REWORK') else 'ELIGIBLE'

def main(argv=None):
    cli=argparse.ArgumentParser(description='MovieRec development task CLI')
    sub=cli.add_subparsers(dest='action',required=True)
    for action in ('validate','list','next'):sub.add_parser(action)
    for action in ('show','start','run-local','complete','verify'):sub.add_parser(action).add_argument('task_id')
    args=cli.parse_args(argv)
    try:
        tasks=load_tasks();errors=validate_tasks(tasks)
        if errors:
            for e in errors:print('ERROR:',e,file=sys.stderr)
            return 2
        if args.action=='validate':print(f'PASS: {len(tasks)} task contracts valid; no dependency cycles');return 0
        state=read_state()
        if args.action=='list':
            for tid,t in tasks.items():print(tid,display_status(tasks,tid,state),t['title'])
            return 0
        if args.action=='next':
            print('\n'.join(eligible_tasks(tasks,state)) or 'No eligible tasks (dependencies/decisions blocked)')
            return 0
        tid=args.task_id
        if tid not in tasks:raise ValueError('Unknown task '+tid)
        if args.action=='show':
            print(yaml.safe_dump(tasks[tid],sort_keys=False,allow_unicode=True));print('STATUS:',display_status(tasks,tid,state));return 0
        if args.action=='start':
            assert_ready(tasks,tid,state)
            old=state['tasks'].get(tid,{})
            state['tasks'][tid]={'status':'IMPLEMENT','attempt':old.get('attempt',0)+1,'started_at':now()}
            write_state(state);print(tid,'IMPLEMENT');return 0
        if args.action=='run-local':
            code,report,path=run_local(tasks[tid]);state['tasks'].setdefault(tid,{}).update(status='TEST' if code==0 else 'NEEDS_REWORK',last_report=path,updated_at=now())
            write_state(state);print(tid,report['result'],'exit',code,'report',path)
            print('Commit and push required; complete re-runs tests and confirms remote SHA. CI is separate.')
            return code
        if args.action in ('complete','verify'):
            proof=complete(tasks,tid) if args.action=='complete' else verify_completion(tasks,tid,ROOT)
            print(tid,'DONE',proof['head_sha'],'branch',proof['branch']);return 0
    except (ValueError,OSError,KeyError,yaml.YAMLError,json.JSONDecodeError) as exc:
        print('ERROR:',exc,file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
