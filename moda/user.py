import os
import re
import pdb
import code
import glob
import time
import click
import signal
import logging
import collections
import subprocess
import IPython
import bpython
import pandas as pd

from enum import Enum
from datetime import datetime
from pprint import pformat
from typing import List, Optional, Callable, Dict, Union
from .style import Styled, CustomStyled, CodeStyled, Format
from .error import ModaTimeoutError, ModaCannotInteractError
from pathlib import Path

class MenuOption(Enum):
  @property
  def option_text(self) -> str:
    raise NotImplementedError()

  @property
  def styled(self) -> Styled:
    return CustomStyled(text=self.option_text)


class Interaction(MenuOption):
  python = 'p'
  script = 'r'
  debugger = 'd'
  log = 'l'

  @property
  def option_text(self) -> str:
    if self is Interaction.python:
      return '(P)ython interactive shell'
    elif self is Interaction.script:
      return '(R)un python script'
    elif self is Interaction.debugger:
      return '(D)ebugger session'
    elif self is Interaction.log:
      return '(L)og view'

  @property
  def styled(self) -> Styled:
    return CustomStyled(text=self.option_text, style=Format().blue())

class Console(code.InteractiveConsole):
  record: List = None

  def raw_input(self, prompt=''):
    result = super().raw_input(prompt=prompt)
    if self.record is None:
      self.record = []
    self.record.append(result)
    return result

class UserExceptionFormatter(logging.Formatter):
  style: Format = Format().red().bold()
  def formatException(self, exc_info):
    return self.style(super(UserExceptionFormatter, self).formatException(exc_info))

  def format(self, record):
    s = super(UserExceptionFormatter, self).format(record)
    if record.exc_text:
      s = self.style(s)
    return s

class PythonShellType(Enum):
  default = 'default'
  ipython = 'ipython'
  bpython = 'bpython'

class UserInteractor:
  locals: Dict[str, any]
  timeout: Optional[int]
  interactive: bool
  quiet: bool
  python_shell_type: PythonShellType
  editor_command: List[str]
  script_directory_components: List[str]
  output_directory_components: List[str]
  _last_script_name: Optional[str]=None

  def __init__(self, locals: Dict[str, any]={}, timeout: Optional[int]=30, interactive: bool=True, quiet: bool=False, python_shell_type: PythonShellType=PythonShellType.ipython, editor_command: List[str]=['vi'], script_directory_components: List[str]=['output', 'python', 'scripts'], output_directory_components: List[str]=['output', 'python']):
    self.timeout = timeout
    self.locals = self.python_locals
    self.locals = {**locals}
    self.interactive = interactive
    self.quiet = quiet
    self.python_shell_type = python_shell_type
    self.editor_command = editor_command
    self.script_directory_components = script_directory_components
    self.output_directory_components = output_directory_components

  @classmethod
  def shell(cls, driver: Optional[any]=None, locals: Dict[str, any]={}):
    user = cls(locals=locals)
    user.present_python_shell()

  @classmethod
  def date_file_name(cls) -> str:
    return datetime.now().strftime('%Y-%m-%d_%H_%M_%S')
    
  @classmethod
  def safe_file_name(cls, name: str) -> str:
    return re.sub(r'[/:]', '_', name)

  @property
  def python_locals(self) -> Dict[str, any]:
    return {}

  def present_prompt(self, prompt: str, response_type: any=str, default_response: Optional[any]=None, prompter: Optional[Callable[[str, any, Optional[any]], any]]=None):
    if prompter is None:
      def prompter(prompt: str, response_type:any, default_response: Optional[any]) -> any:
         return click.prompt(prompt, type=response_type, default=default_response)

    if self.interactive:
      if self.timeout is None:
        response = prompter(prompt, response_type, default_response)
      elif self.timeout <= 0:
        response = default_response
      else:
        def handle_alarm(signum, frame):
          raise ModaTimeoutError()
        original_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, handle_alarm)
        original_time = time.time()
        original_alarm = signal.alarm(self.timeout)
        try:
          print(f'Will continue automaticially after {self.timeout} seconds with reponse [{default_response}]')
          response = prompter(prompt, response_type, default_response)
          signal.alarm(0)
        except ModaTimeoutError:
          print(f' => {default_response} (continuing automaticially after {self.timeout} seconds)')
          response = default_response
        signal.signal(signal.SIGALRM, original_handler)
        if original_alarm:
          new_alarm = original_alarm - (time.time() - original_time)
          if new_alarm > 0:
            signal.setitimer(signal.ITIMER_REAL, new_alarm)
          else:
            signal.setitimer(signal.ITIMER_REAL, 0.01)
            time.sleep(1)
    else:
      response = default_response
    return response

  def present_error(self, error: Exception):
    handler = logging.StreamHandler()
    formatter = UserExceptionFormatter()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.addHandler(handler)
    logging.exception(error)
    root.removeHandler(handler)

  def present_message(self, message: Optional[str]=None, prompt: Optional[str]=None, error: Optional[Exception]=None, response_type: any=str, default_response: Optional[any]=None):
    response = None
    if error is not None:
      self.present_error(error)
    if message is not None:
      if not self.quiet:
        print(message)
    if prompt is not None:
        response = self.present_prompt(prompt=prompt, response_type=response_type, default_response=default_response)
    return response

  def present_confirmation(self, prompt: str='Continue', default_response: bool=False) -> bool:
    def prompter(prompt: str, response_type: any, default_response: bool) -> bool:
      return click.confirm(prompt, default=default_response)
    return self.present_prompt(prompt=prompt, response_type=bool, default_response=default_response, prompter=prompter)

  def present_report(self, report: Union[pd.DataFrame, pd.Series], title: Optional[str]=None, prefix: Optional[str]=None, suffix: Optional[str]=None):
    with pd.option_context('display.max_rows', None, 'display.max_columns', None):
      prefix = f'{prefix}\n' if prefix else ''
      report_text = report.to_string() if not report.empty else 'Empty report.'
      suffix = f'\n{suffix}' if suffix else ''
      self.present_title(title=title)
      self.present_message(f'{prefix}{report_text}{suffix}')

  def present_menu(self, options: List[MenuOption], default_option: Optional[MenuOption]=None, message: Optional[str]=None) -> MenuOption:
    prompt = '\n'.join([
      (o.styled + Format().underline()).styled if o is default_option else o.styled.styled for o in options
      ] + [message if message is not None else ''])
    option_values = [o.value for o in options]

    assert default_option is None or default_option in options
    assert len(option_values) == len(set(option_values)), str([o for o in options if collections.Counter(option_values)[o.value] > 1])

    choice = self.present_message(
      prompt=prompt,
      response_type=click.Choice(option_values, case_sensitive=False),
      default_response=default_option.value if default_option else None
    )
    option = next(filter(lambda o: o.value == choice, options))
    return option

  def interact(self, interaction: Interaction) -> bool:
    if interaction is Interaction.python:
      self.present_python_shell()
    elif interaction is Interaction.script:
      self.run_script()
    elif interaction is Interaction.debugger:
      self.debug()
    elif interaction is Interaction.log:
      log = self.locals['log'] if 'log' in self.locals else pd.DataFrame()
      self.present_log(log=log)

  def python_shell(self) -> str:
    if not self.interactive:
      raise ModaCannotInteractError()
    print('Local variables:')
    for name, value in self.locals.items():
      print(f'  {name}:\n    {pformat(value)}')
    if self.python_shell_type is PythonShellType.default:
      console = Console(locals=self.locals)
      console.interact(banner='Python shell. Type CTRL-D to exit.')
      return '\n'.join(console.record)
    elif self.python_shell_type is PythonShellType.ipython:
      print('IPython shell. Type CTRL-D to exit.')
      console = IPython.terminal.embed.InteractiveShellEmbed()
      import builtins
      console.mainloop(local_ns=self.locals, module=builtins)
      record = ''
      for index, line in enumerate(console.history_manager.input_hist_raw):
        record += f'{line}\n'
        if index in console.history_manager.output_hist:
          record += f'# {str(console.history_manager.output_hist[index])}\n'
      return record
    elif self.python_shell_type is PythonShellType.bpython:
      history_path = os.path.join(*self.output_directory_components, 'history.py')
      try:
        os.remove(history_path)
      except FileNotFoundError:
        pass
      bpython.embed(args=['--config=bpython_config'], locals_=self.locals, banner='bpython shell. Type CTRL-D to exit.')
      if os.path.isfile(history_path):
        with open(history_path, 'r') as f:
          record = f.read()
      else:
        record = ''
      return record
  
  def present_python_shell(self):
    record = self.python_shell()
    if not record.strip():
      return
    choice = click.prompt('(S)ave, (E)dit, or (D)elete record of interaction?', type=click.Choice(['s', 'e', 'd'], case_sensitive=False), default='d').lower()
    if choice in ['s', 'e']:
      path = os.path.join(*self.output_directory_components, f'{type(self).date_file_name()}_interaction.py')
      with open(path, 'w') as f:
        f.write(record)
      if choice == 'e':
        subprocess.call([
          self.editor_command,
          path,
        ])
        while True:
          script_name = click.prompt('To save this interaction as a script enter a script name, or press return to continue.', default='')
          if not script_name:
            break
          script_name = self.safe_file_name(script_name)
          script_path = os.path.join([*self.script_directory_components, f'{script_name}.py'])
          if os.path.exists(script_path):
            if not click.confirm(f'A script alread exists at \'{script_path}\'\nWould you like to replace it', abort=True):
              continue
          with open(path, 'r') as f:
            with open(script_path, 'w') as g:
              g.write(f.read())
          print(f'Script written to \'{script_path}\'\nIt will be available for future use as \'{script_name}\'')
          break
      else:
        print(f'{record}\n\nWritten to {path}')

  def run_script_path(self, script_path: str):
    path = Path(script_path)
    assert path.suffix == '.py', 'Script files must use the .py extension'
    script_name = path.stem
    previous_script_directory_components = self.script_directory_components
    self.script_directory_components = path.parent.parts
    try:
      self.run_script(script_name=script_name)
    finally:
      self.script_directory_components = previous_script_directory_components

  def run_script(self, script_name: Optional[str]=None):
    script_paths = glob.glob(os.path.join(*self.script_directory_components, '*.py'))
    if not script_paths:
      print(f'No scripts found in \'{os.path.join(self.script_directory_components)}/\'')
      return
    script_names = {os.path.splitext(os.path.basename(p))[0]: p for p in script_paths}
    if script_name is None and self.interactive:
      default_script = self._last_script_name if self._last_script_name in script_names.keys() else None
      script_name = click.prompt('Enter a script to execute', type=click.Choice(sorted(script_names.keys())), default=default_script)
    if not script_name:
      return
    self._last_script_name = script_name
    with open(script_names[script_name], 'r') as f:
      script = f.read()
    self.run_code(code=script, file_path=script_names[script_name], description=f'from \'{script_names[script_name]}\'')

  def run_code(self, code: str, file_path: str, description: str, confirm: Optional[bool]=True):
    if confirm:
      message_style = Format().cyan()
      prompt = CustomStyled(text=f'Script...\n{"–" * 9}\n', style=message_style) + CodeStyled(text=code) + CustomStyled(text=f'{"–" * 9}\n...Script\n', style=message_style) + f'Run this script ({description})'
      if not self.present_confirmation(prompt=prompt.styled, default_response=True):
        return
    compiled = compile(code, file_path, 'exec')
    namespace = {**self.locals}
    exec(compiled, namespace, namespace)
    print(f'Ran script ({description})')    

  def debug(self):
    pdb.set_trace()

  def present_title(self, title: str=''):
    title = Format().cyan()(f'\n{title}\n{"–" * len(title)}\n') if title else ''
    print(title)

  def present_log(self, log: pd.DataFrame):
    self.present_title(title='Flight Log')
    index_style = Format().gray()
    maneuver_style = Format().bold()
    attempt_style = Format().blue()
    error_style = Format().red().bold()
    result_style = Format().green().bold()
    for index, row in log.iterrows():
      mission = f'{row.mission}.' if row.mission else ''
      print(f'{index_style(str(index))} {mission}{maneuver_style(row.maneuver)}')
      if row.error:
        print(error_style(f'  = {row.option} – {row.error}'))
      elif row.result:
        print(result_style(f'  = {row.option} : {row.result}'))
      else: 
        print(attempt_style(f'  = {row.option}'))
    print(f'{len(log)} actions logged')
