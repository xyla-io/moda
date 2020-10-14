import os
import psutil
import pandas as pd

from datetime import datetime
from pympler import muppy, summary
from typing import Callable

def default_message_loggger(message: str, end: str='\n'):
  print(message, end=end)

log_message = default_message_loggger

def set_message_logger(message_logger: Callable[[str, str], None]):
  global log_message
  log_message = message_logger

def log(message: str, end: str='\n'):
  log_message(message=message, end=end)

def log_memory_usage(context: str=''):
  process = psutil.Process(os.getpid())
  memory = process.memory_info().rss
  time_format = '%Y-%m-%dT%h:%m:%s'
  print(f'Process memory {memory:,}')
  with open(os.path.join('output', 'test', 'memory.txt'), 'a') as file:
    file.write(f'{memory:,},{context},{datetime.now().strftime(time_format)}\n')
  all_objects = muppy.get_objects()
  sum1 = summary.summarize(all_objects)
  summary.print_(sum1)
  dataframes = [ao for ao in all_objects if isinstance(ao, pd.DataFrame)]
  for d in dataframes:
    print(d.columns.values)
    print(f'Rows: {len(d)}')
