"""Optional passive evidence wrapper; delegates containment/acceptance unchanged.

Inputs are retained before invocation, returned records before semantic checks.
Interrupted/cleanup-uncertain calls retain only an exception record, never invented
exit/cleanup/success evidence. Trusted single-threaded local evaluation only.
"""
import json
from pathlib import Path

from evaluate import run_stage
from check_host import run_control
from staging import name_ok, digest, require


def write_json(path, value):
    path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')


class Journal:
    def __init__(self, root, *, stage_runner=run_stage, control_runner=run_control):
        self.root=Path(root)
        self.stage_runner=stage_runner
        self.control_runner=control_runner

    def _prepare(self,label,inputs,metadata):
        name_ok(label)
        folder=self.root/label;folder.mkdir()
        for name,raw in inputs.items():
            name_ok(name,nested=True);require(type(raw) is bytes,'journal expects bytes')
            path=folder/'inputs'/name;path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as f:f.write(raw)
        write_json(folder/'attempt.json',dict(metadata,inputs={n:{'sha256':digest(b),'bytes':len(b)} for n,b in inputs.items()}))
        return folder

    def run_stage(self,batch,label,inputs,expected,**kwargs):
        folder=self._prepare(label,inputs,{'kind':'stage','runtime':kwargs.get('runtime','python'),'expected':list(expected)})
        try:
            row,files=self.stage_runner(batch,label,inputs,expected,**kwargs)
            write_json(folder/'stage-record.json',row)
            for name,raw in files.items():
                name_ok(name)
                with (folder/name).open('xb') as f:f.write(raw)
            return row,files
        except BaseException as exc:
            write_json(folder/'exception.json',{'type':type(exc).__name__,'cleanup_proven':False,'accepted':False})
            raise

    def run_control(self,root,canary,name,code,seconds,deadline,**kwargs):
        folder=self._prepare('host-'+name,{'control.py':code.encode()},
            {'kind':'host-control','seconds':seconds,'deadline_epoch':deadline,**kwargs})
        try:
            row=self.control_runner(root,canary,name,code,seconds,deadline,**kwargs)
            write_json(folder/'control-record.json',row)
            return row
        except BaseException as exc:
            write_json(folder/'exception.json',{'type':type(exc).__name__,'cleanup_proven':False,'accepted':False})
            raise
