from typing import Dict
from contextlib import contextmanager

class Connector:
  def connect(self, **kwargs):
    pass

  def disconnect(self):
    pass

  @contextmanager
  def connected(self, **kwargs):
    self.connect(**kwargs)
    try:
      yield
    finally:
      self.disconnect()