import os
import atexit
import tempfile

from pathlib import Path
from typing import Optional, Dict

def evaluate(code: str, path: Optional[str]='', context: Optional[Dict[str, any]]=None, repair_user: Optional['UserInteractor']=None):
  # TODO: Implement path and repair options
  assert path == '', 'Only the empty string path option is currently supported'
  assert repair_user is None, 'Only passing None for the repair_user option is currently supported'
  if context is None:
    context = {}
  file, path = tempfile.mkstemp(suffix='.py')
  os.close(file)
  exit_handler = atexit.register(lambda: Path(path).unlink())
  with open(path, mode='w+') as f:
    f.write(code)
    compiled = compile(code, path, 'exec')
    exec(compiled, context, context)
  atexit.unregister(exit_handler)
  exit_handler()
  return context