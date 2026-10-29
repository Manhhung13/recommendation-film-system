#!/usr/bin/env python3
"""Read-only preflight for a proposed task commit. Does NOT commit or push.

Checks changed-file path allowlist, branch policy and local status. A real controller
MUST separately verify trusted independent review and CI; local state is not secure.
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


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('task_id')
    args=cli.parse_args()
    try:
        task=yaml.safe_load((tasks_root(ROOT)/f'{args.task_id}.yaml').read_text(encoding='utf-8'))
        if task['id']!=args.task_id:raise ValueError('task ID mismatch')
        current_status=status(args.task_id,read_state())
        if current_status!='LOCAL_VERIFIED':raise ValueError('Local verification missing for '+args.task_id)
        branch=git('branch','--show-current')
        if not branch.startswith('feature/'):
            raise ValueError('Expected feature/ branch; refusing main/other branch: '+branch)
        # Note: --others tracks untracked; staged/unstaged tracked changes in diff HEAD
        tracked=[x for x in git('diff','--name-only','HEAD').splitlines() if x]
        other=[x for x in git('ls-files','--others','--exclude-standard').splitlines() if x]
        changed=sorted(set(tracked+other))
        if not changed:raise ValueError('No file changes to commit')
        bad=check_allowed_paths(changed,task['allowed_paths'])
        if bad:raise ValueError('Changes outside allowed task scope: '+', '.join(bad))
        print('PREFLIGHT PASS (not a review approval or permission to push):',args.task_id)
        print('Branch:',branch)
        print('Changed paths:',*changed,sep='\n - ')
        print('Next: obtain separate authorized code review + trusted git publisher')
        return 0
    except (OSError,ValueError,KeyError,RuntimeError) as exc:
        print('PREFLIGHT FAILED:',exc,file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
