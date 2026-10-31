"""SETUP-001 acceptance: real graph validation, executable CI and CLI protocol."""
import copy
import configparser
from pathlib import Path
import subprocess
import sys
import yaml

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'movie-rec-agent-starter/scripts'))
import agentctl


def test_setup_001_ac_01():
    tasks=agentctl.load_tasks()
    assert agentctl.validate_tasks(tasks)==[]
    assert tasks['SETUP-001']['dependencies']==['SDLC-INTEGRATION-001']
    assert set(tasks['DATA-QUALITY-001']['dependencies'])=={f'DATA-{i:03}' for i in range(1,7)}
    assert tasks['RESEARCH-001']['dependencies']==['DATA-QUALITY-001']
    assert tasks['EDA-001']['dependencies']==['RESEARCH-001']
    assert set(tasks['SPLIT-001']['dependencies'])=={'DATA-006','EDA-001'}
    broken=copy.deepcopy(tasks);broken['SETUP-001']['dependencies']=['UNKNOWN-001']
    assert any('unknown/self dependency' in error for error in agentctl.validate_tasks(broken))
    gates=yaml.safe_load((ROOT/'movie-rec-agent-starter/.agents/policies/quality_gates.yaml').read_text())
    assert gates['phase_order']==['ELIGIBLE','IMPLEMENT','TEST','COMMIT','PUSH','DONE']
    assert {'acceptance_tests','task_dependencies','dataset_integrity','scoped_commit','successful_push','remote_head_sha_match'}<=set(gates['always_required'])
    for task in tasks.values():
        assert {'unit_tests','integration_tests'}<=set(task['required_checks'])
        assert not {'independent_review','github_ci'}&set(task['required_checks'])


def test_setup_001_ac_02():
    config=configparser.ConfigParser();config.read(ROOT/'pytest.ini')
    for name in config['pytest']['testpaths'].split():assert (ROOT/name).is_dir()
    assert '--strict-markers' in config['pytest']['addopts']
    pins=(ROOT/'requirements-test.txt').read_text().splitlines()
    packages={line.split('==')[0] for line in pins if line and not line.startswith('#')}
    assert {'pytest','PyYAML','pluggy','packaging','iniconfig','Pygments','colorama'}<=packages
    assert all('==' in line and '>=' not in line for line in pins if line and not line.startswith('#'))
    for file,job in [('agent-contracts.yml','validate-contracts'),('movie-rec-product.yml','test')]:
        workflow=yaml.load((ROOT/'.github/workflows'/file).read_text(),Loader=yaml.BaseLoader)
        assert workflow['permissions']=={'contents':'read'}
        assert workflow['on']['push']['branches']==['main','feature/**']
        steps=workflow['jobs'][job]['steps']
        assert steps[1]['with']['python-version']=='3.12'
        commands=[step['run'] for step in steps if 'run' in step]
        assert 'python -m pip install -r requirements-test.txt' in commands
        assert not any('acquire' in command or 'dataset_linkage_work' in command for command in commands)
        if job=='test':assert commands[-1]=='python -B -m pytest -q tests'
        else:assert any('unittest discover' in command for command in commands)


def test_setup_001_ac_03():
    cli=ROOT/'movie-rec-agent-starter/scripts/agentctl.py'
    validation=subprocess.run([sys.executable,'-B',str(cli),'validate'],cwd=ROOT,capture_output=True,text=True)
    assert validation.returncode==0,validation.stderr
    assert '28 task contracts valid' in validation.stdout
    help_result=subprocess.run([sys.executable,'-B',str(cli),'--help'],cwd=ROOT,capture_output=True,text=True)
    assert help_result.returncode==0
    for command in ('start','run-local','complete','verify'):assert command in help_result.stdout
    protocol=' '.join((ROOT/'docs/agent/DEVELOPMENT_SDLC.md').read_text().split())
    for command in ('git commit','git push','complete TASK-ID','verify TASK-ID'):assert command in protocol
    assert 'origin feature ref equals local HEAD' in protocol
    assert 'CI is reported separately' in protocol
    assert (ROOT/'docs/agent/SETUP_001.md').is_file()
