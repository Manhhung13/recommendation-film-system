#!/usr/bin/env python3
"""Read-only preflight for a proposed task commit. Does NOT commit or push.

Checks explicit staged scope, branch policy and prohibited artifact paths.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import yaml
from agentctl import ROOT, read_state, status, tasks_root


def git(*args):
    p=subprocess.run(['git',*args],cwd=ROOT,capture_output=True,text=True)
    if p.returncode:raise RuntimeError(p.stderr.strip() or 'git error')
    return p.stdout.strip()


def check_allowed_paths(paths, allowed):
    bad=[]
    for p in paths:
        name=p.replace('\\','/')
        path=Path(name)
        if path.is_absolute() or name.startswith('/') or (len(name) >= 3 and name[1] == ':' and name[2] == '/') or '..' in path.parts:
            bad.append(p)
            continue
        matches=False
        for rule in allowed:
            normalized=rule.replace('\\','/')
            if normalized.endswith('/'):
                matches = matches or name.startswith(normalized)
            else:
                matches = matches or name == normalized
        if not matches:bad.append(p)
    return bad

def check_safe_paths(paths):
    """Conservative filename guard; staged content still needs human inspection."""
    bad=[]
    for name in paths:
        p=Path(name.lower().replace('\\','/'))
        if (any(part in {'dataset_linkage_work','.runtime','.git'} for part in p.parts)
                or p.parts[0] in {'data','datasets'}
                or any(part.startswith('.venv') for part in p.parts)
                or (p.name.startswith('.env') and p.name not in {'.env.example','.env.sample'})
                or p.suffix in {'.pem','.key','.pkl','.pt','.pth','.onnx','.parquet'}
                or p.name in {'credentials.json','secrets.json'}):
            bad.append(name)
    return bad



def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('task_id')
    args=cli.parse_args()
    try:
        task=yaml.safe_load((tasks_root(ROOT)/f'{args.task_id}.yaml').read_text(encoding='utf-8'))
        if task['id']!=args.task_id:raise ValueError('task ID mismatch')
        current_status=status(args.task_id,read_state())
        if current_status!='TEST':raise ValueError('Passing local tests missing for '+args.task_id)
        branch=git('branch','--show-current')
        if not branch.startswith('feature/'):
            raise ValueError('Expected feature/ branch; refusing main/other branch: '+branch)
        changed=git('diff','--cached','--name-only').splitlines()
        if not changed:raise ValueError('No file changes to commit')
        bad=check_allowed_paths(changed,task['allowed_paths'])
        bad+=check_safe_paths(changed)
        if bad:raise ValueError('Changes outside allowed task scope: '+', '.join(bad))
        git('diff','--check');git('diff','--cached','--check')
        print('PREFLIGHT PASS:',args.task_id)
        print('Branch:',branch)
        print('Changed paths:',*changed,sep='\n - ')
        print('Next: inspect staged content, commit with TASK-ID, push, then agentctl complete')
        return 0
    except (OSError,ValueError,KeyError,RuntimeError) as exc:
        print('PREFLIGHT FAILED:',exc,file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
