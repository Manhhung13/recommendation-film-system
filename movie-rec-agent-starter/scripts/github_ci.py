#!/usr/bin/env python3
"""Read-only GitHub check-run verifier for an exact SHA. Requires GITHUB_TOKEN.
No task status is updated by this script; trusted controller must do that.
"""
import argparse, json, os, re, sys, urllib.request, urllib.error

def verify_checks(checks,sha,required):
    issues=[]
    for name in required:
        matches=[c for c in checks if c.get('name')==name and c.get('head_sha')==sha]
        if not matches:issues.append(name+': no check-run for exact SHA');continue
        newest=max(matches,key=lambda c:(c.get('started_at') or '',c.get('id') or 0))
        if newest.get('status')!='completed' or newest.get('conclusion')!='success':
            issues.append(name+': status='+str(newest.get('status'))+' conclusion='+str(newest.get('conclusion')))
    return issues

def fetch_checks(repo,sha,token):
    checks=[]
    for page in range(1,6):
        url=f'https://api.github.com/repos/{repo}/commits/{sha}/check-runs?per_page=100&page={page}'
        req=urllib.request.Request(url,headers={'Authorization':f'Bearer {token}',
          'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'MovieRec-CI-Reader'})
        with urllib.request.urlopen(req,timeout=20) as r:response=json.load(r)
        found=response.get('check_runs',[]);checks.extend(found)
        if len(found)<100:break
    return checks

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--repo',required=True);cli.add_argument('--sha',required=True)
    cli.add_argument('--required',action='append',required=True);args=cli.parse_args()
    try:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',args.repo):raise ValueError('repo should be OWNER/REPO')
        if not re.fullmatch(r'[0-9a-fA-F]{40}',args.sha):raise ValueError('sha must be 40 hex characters')
        token=os.environ.get('GITHUB_TOKEN')
        if not token:raise ValueError('Missing GITHUB_TOKEN in environment')
        issues=verify_checks(fetch_checks(args.repo,args.sha,token),args.sha,args.required)
        if issues:
            for issue in issues:print('FAIL:',issue,file=sys.stderr)
            return 1
        print('PASS required GitHub checks at exact SHA',args.sha)
        return 0
    except (ValueError,urllib.error.URLError,TimeoutError) as exc:
        print('ERROR:',exc,file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
