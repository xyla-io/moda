import sys
import time
import shlex
import atexit
import subprocess

from queue import Queue, Empty
from threading import Thread
from typing import List, Tuple, Callable, Optional, Generator, Union
from .log import log

def terminator(process: any, terminate_on_exit: bool=True) -> Callable[[], None]:
  """Creates a function that tries to terminate, then kills a subprocess"""

  def terminate():
    log(f'Terminating subprocess: {process.pid}')
    try:
      process.terminate()
    except ProcessLookupError:
      pass

  if terminate_on_exit:
    atexit.register(terminate)
  return terminate

def split_run_args(command: str) -> List[str]:
  """Splits a shell command string into arguments."""
  return shlex.split(command)

def escape_run_arg(run_arg: any) -> str:
  """Quotes a shell argument."""
  return shlex.quote(str(run_arg))

def escape_run_args(run_args: List[str]) -> List[str]:
  """Quotes shell arguments."""
  # TODO: use shlex.join after upgrading to Python 3.8:
  # return shlex.quote(shlex.join(run_args))
  return [escape_run_arg(a) for a in run_args]

def escape_command(run_args: List[str]) -> str:
  """Quotes a shell command so that it can be used as a run argument."""
  # TODO: use shlex.join after upgrading to Python 3.8:
  # return shlex.quote(shlex.join(run_args))
  return shlex.quote(' '.join(escape_run_args(run_args=run_args)))

def ssh_command(run_args: List[str], user: str, host: str, escape_run_args: bool=True) -> List[str]:
  """Wraps a command in an SSH command to run it on a remote host."""
  return [
    'ssh',
    f'{user}@{host}',
    ' '.join(escape_run_arg(a) if escape_run_args else a for a in run_args),
  ]

def script_command(script: str, shell: str='bash', should_eval: bool=False) -> List[str]:
  """Runs a script string in a specified shell"""
  return [
    *(['eval'] if should_eval else []),
    f'echo {escape_run_arg(script)} | {shell}',
  ]

def call_process(run_args: List[str], shell=False) -> int:
  """Runs a subprocess, blocking until it finishes.

  Returns:
    int: the return code.
  """

  return_code = subprocess.call(args=run_args, shell=shell)
  return return_code

def read_stream(stream: any, chunk_size: int=1024, empty_sleep: float=0.01) -> Tuple[Queue, Queue, Thread]:
  """Reads one byte at a time from a stream on a separate thread.

  Returns:
    tuple: a tuple containing a queue to receive output from the reader, a queue to send a stop signal to the readier, and the thread on which the reader runs.
  """
  queue = Queue()
  stop_queue = Queue()
  def reader():
    stop = False
    while True:
      try:
        stop = stop_queue.get_nowait()
        time.sleep(empty_sleep)
      except Empty:
        pass
      output = stream.read(1)
      if not output:
        if stop:
          queue.put(b'')
          break
        else:
          time.sleep(empty_sleep)
          continue
      try:
        queue_bytes = queue.get_nowait()
        queue.task_done()
        output = queue_bytes + output
      except Empty:
        pass
      queue.put(output)
      if len(output) >= chunk_size:
        queue.join()

  thread = Thread(target=reader)
  thread.setDaemon(True)
  thread.start()

  return (queue, stop_queue, thread)

def run_process_output(run_args: List[str], shell=False) -> Tuple[int, bytes, bytes]:
  """Runs a process, blocking, and returns a tuple of its return code, output bytes, and error bytes"""

  result = subprocess.run(
    args=run_args,
    shell=shell,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
  )
  return (result.returncode, result.stdout, result.stderr)

def spawn_process(run_args: List[str], terminate_on_exit: bool=True) -> Tuple[subprocess.Popen, Callable[[], None]]:
  """Runs a subprocess, without blocking.

  Returns:
    tuple: a tuple containing the process and its terminate function.
  """

  process = subprocess.Popen(args=run_args)

  return (process, terminator(process=process, terminate_on_exit=terminate_on_exit))

def run_process(run_args: List[str], terminate_on_exit: bool=True, chunk_size: int=1024, message_delimiters: List[bytes]=[b'\n'], encoding: Optional[str]=None, echo: bool=False, empty_sleep: float=0.01) -> Tuple[subprocess.Popen, Callable[[], None], Generator[Tuple[Optional[bytes], List[Union[bytes, str]], bool], bytes, int]]:
  """Runs a subprocess, without blocking and supports two-way interaction.

  Returns:
    tuple: a tuple containing the process, its terminate function, and a generator that will generate tuples with output bytes, output messages, a flag to indicate whether the output is error output and an optional return code.
  """

  process = subprocess.Popen(run_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
  terminate = terminator(process=process, terminate_on_exit=terminate_on_exit)

  def output():
    def handle_input(input_bytes: Optional[Union[bytes, str]]):
      if input_bytes is not None:
        process.stdin.write(input_bytes)
        process.stdin.flush()

    partial_messages = {
      False: b'',
      True: b'',
    }
    readers = {
      False: read_stream(stream=process.stdout, chunk_size=chunk_size, empty_sleep=empty_sleep),
      True: read_stream(stream=process.stderr, chunk_size=chunk_size, empty_sleep=empty_sleep),
    }
    is_stderr = True
    def parse_messages(output_bytes: bytes):
      nonlocal partial_messages
      nonlocal is_stderr
      messages = [partial_messages[is_stderr] + output_bytes]
      for delimiter in message_delimiters:
        messages = [m for o in message_delimiters for m in o.split(delimiter)]
      partial_messages[is_stderr] = messages[-1]
      messages = messages[:-1]
      if encoding:
        messages = map(lambda m: m.decode(encoding), messages)
      return messages

    input_bytes = yield (b'', [], False)
    handle_input(input_bytes)

    return_code = None
    empty_countdown = 2
    stop_countdown = 2
    while True:
      is_stderr = not is_stderr
      try:
        output = readers[is_stderr][0].get_nowait()
        readers[is_stderr][0].task_done()
        if not output:
          stop_countdown -= 1
      except Empty:
        if return_code is not None and stop_countdown:
          time.sleep(empty_sleep)
          continue
        else:
          output = b''

      if output == b'':
        empty_countdown -= 1
        if empty_countdown:
          continue
        time.sleep(empty_sleep)
        if return_code is None:
          return_code = process.poll()
          empty_countdown = 2
          if return_code is not None:
            for _, reader in readers.items():
              reader[1].put(True)
          continue
        else:    
          break

      empty_countdown = 2
    
      messages = parse_messages(output)
      if echo:
        if encoding:
          if messages:
            print('\n'.join(messages))
            sys.stdout.flush()
        else:
          string_output = '\n'.join(str(b)[2:-1] for b in output.split(b'\n'))
          print(string_output, end='')
          sys.stdout.flush()

      input_bytes = yield (output, message_delimiters, is_stderr)
      handle_input(input_bytes)

    if terminate_on_exit:
      atexit.unregister(terminate)

    for is_stderr in (False, True):
      if partial_messages[is_stderr] == b'':
        continue
      last_messages = [partial_messages[is_stderr].decode(encoding)] if encoding else [partial_messages[is_stderr]]
      yield (b'', last_messages, is_stderr)

    return return_code

  return (process, terminate, output())

def run_process_combined(run_args: List[str], on_output: Optional[Callable[[subprocess.Popen, str, bytes], Optional[bytes]]]=None, echo: bool=False) -> Tuple[int, str, bytes]:
  """Runs a subprocess, without blocking, supports two-way interaction, and combines then stdout and stderr streams.

  This function is a simpler implementation of run_process() at the cost of combining stdout and stderr.

  Returns:
    tuple: a tuple containing the return code, the combined collected output string and the combined collected output bytes.
  """
  process = subprocess.Popen(run_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
  collected_bytes = b''
  collected_output = ''

  while True:
    output = process.stdout.read(1)

    if output == b'':
      if process.poll() is not None:
        break
      else:
        continue

    collected_bytes += output
    string_output = '\n' if output == b'\n' else str(output)[2:-1]
    collected_output += string_output
    if echo:
      print(string_output, end='')
      sys.stdout.flush()

    if on_output:
      input_bytes = on_output(process, collected_output, collected_bytes)
      if input_bytes is not None:
        process.stdin.write(input_bytes)
        process.stdin.flush()
        if echo:
          print(str(input_bytes)[2:-1], end='')

  return_code = process.poll()
  return (return_code, collected_output, collected_bytes)