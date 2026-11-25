"""Passive comparison against a caller-pinned installed runtime inventory."""
from runtime_inventory import file_hash,tree_inventory
from staging import require


def verify_inventory(runtime_root,inventory,observations=()):
    root=str(runtime_root)
    require(inventory['environment']['root']==root,'runtime root changed')
    require(tree_inventory(runtime_root)['tree_sha256']==inventory['environment']['tree_sha256'],'runtime tree changed')
    require(all(file_hash(p)==h for p,h in inventory['system_files'].items()),'system files changed')
    for observed in observations:
        for path,expected in observed['native_libraries'].items():
            actual=root+path[len('/runtime'):] if path.startswith('/runtime/') else path
            require(file_hash(actual)==expected,'mapped native bytes changed')
