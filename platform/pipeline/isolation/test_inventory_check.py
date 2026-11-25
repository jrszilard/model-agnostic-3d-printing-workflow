import unittest
from unittest.mock import patch
from inventory_check import verify_inventory


class InventoryTests(unittest.TestCase):
 def test_exact_root_tree_system_and_mapped_bytes(self):
  hashes={'/usr/tool':'system','/installed/lib/a.so':'mapped'}
  with patch('inventory_check.tree_inventory',return_value={'tree_sha256':'tree'}),patch('inventory_check.file_hash',side_effect=hashes.__getitem__):
   verify_inventory('/installed',{'environment':{'root':'/installed','tree_sha256':'tree'},'system_files':{'/usr/tool':'system'}},
                    [{'native_libraries':{'/runtime/lib/a.so':'mapped'}}])
 def test_changed_root_or_tree_denied(self):
  with patch('inventory_check.tree_inventory',return_value={'tree_sha256':'changed'}):
   for root in ('/wrong','/installed'):
    with self.assertRaises(ValueError):verify_inventory(root,{'environment':{'root':'/installed','tree_sha256':'tree'},'system_files':{}})
 def test_changed_mapped_library_denied(self):
  with patch('inventory_check.tree_inventory',return_value={'tree_sha256':'tree'}),patch('inventory_check.file_hash',return_value='changed'):
   with self.assertRaises(ValueError):verify_inventory('/installed',{'environment':{'root':'/installed','tree_sha256':'tree'},'system_files':{}},
                                                    [{'native_libraries':{'/runtime/lib/a.so':'expected'}}])
