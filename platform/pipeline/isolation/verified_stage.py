"""Verify real returned sealed-stage evidence, never simulated/native-import work.

Trusted single supervisor adapter. Journal retains raw returns BEFORE these checks.
The caller independently qualifies runtime and pins this helper/supervisor/tools.
"""
import json
import os
import re
import uuid
from pathlib import Path
from evaluate import command_for
from staging import read_regular,require,digest

HERE=Path(__file__).resolve().parent


def identity(raw):return {'sha256':digest(raw),'bytes':len(raw)}


def tools_for(runtime,outputs):
    raw={name:read_regular(HERE/name) for name in ('staging.py','evaluation_worker.py')}
    raw['job.json']=json.dumps({'command':command_for(runtime),'outputs':outputs}).encode()
    if runtime=='freecad':
        raw['passwd']=f'worker:x:{os.getuid()}:{os.getgid()}:Evaluation:/work:/usr/bin/false\n'.encode()
        raw['group']=f'worker:x:{os.getgid()}:\n'.encode()
    return {name:identity(data) for name,data in raw.items()}


class VerifiedStages:
    def __init__(self,batch,journal,*,supervisor_sha256,runtime_root):
        require(bool(re.fullmatch('[0-9a-f]{64}',supervisor_sha256)),'supervisor SHA required')
        self.batch,self.journal,self.supervisor_sha256,self.runtime_root=batch,journal,supervisor_sha256,runtime_root
        self.executions=set()

    def run(self,label,stage,deadline):
        wanted={name:identity(raw) for name,raw in stage.inputs.items()}
        tools=tools_for(stage.runtime,stage.outputs)
        row,files=self.journal.run_stage(self.batch,label,dict(stage.inputs),stage.outputs,runtime=stage.runtime,
            runtime_root=self.runtime_root if stage.runtime=='cadquery' else None,case_deadline=deadline)
        require(type(row) is dict and 'simulation' not in row,'not real stage evidence')
        require(row.get('schema')=='isolated-digital-evaluation/v1' and row.get('authority')=='digital-evaluation-only'
                and row.get('manufacturing_qualified') is False,'wrong stage scope')
        require(row.get('label')==label and row.get('runtime')==stage.runtime and row.get('inputs')==wanted
                and row.get('tools')==tools and row.get('supervisor_sha256')==self.supervisor_sha256,'stage identity mismatch')
        command=row.get('profile_command_sha256')
        require(type(command) is str and bool(re.fullmatch('[0-9a-f]{64}',command)),'command audit SHA required')
        eid=row.get('execution_id')
        try:valid=type(eid) is str and str(uuid.UUID(eid))==eid
        except (ValueError,TypeError,AttributeError):valid=False
        require(valid and eid not in self.executions,'stage execution identity reused/invalid')
        self.executions.add(eid)
        require(row.get('status')=='accepted' and type(row.get('exit')) is int and row['exit']==0
                and row.get('reason') is None,'stage not accepted')
        require(row.get('cgroup_removed') is True and row.get('observed',{}).get('cgroup.events')=='populated 0\nfrozen 0',
                'stage cleanup uncertain')
        require(type(files) is dict and set(files)==set(stage.outputs),'stage output set')
        for name,raw in files.items():
            limit=16*1024*1024 if name.endswith('.step') else 4*1024*1024 if name.endswith('.stl') else 1024*1024
            require(type(raw) is bytes and 0<len(raw)<=limit,'stage output bound')
        require(row.get('outputs')=={name:identity(raw) for name,raw in files.items()},'stage output identities')
        return row,dict(files)
