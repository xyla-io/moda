from __future__ import annotations

import pygments

from enum import Enum
from typing import Optional, List, Dict
from pygments.lexers import PythonLexer
from pygments.formatters import TerminalFormatter

class Styling:
  enabled: bool = True

  @property
  def marker(self) -> str:
    return ''

  @property
  def terminator(self) -> str:
    return ''

  def __add__(self, other):
    if isinstance(self, Format) and isinstance(other, Format):
      return type(self)(styles=self.styles + other.styles)
    elif isinstance(self, Format) and isinstance(other, Styling):
      return type(self)(styles=self.styles + [other])
    elif isinstance(other, Styling):
      return Format(styles=[self, other])
    elif isinstance(other, str):
      return CustomStyled(text=other, style=self)
    else:
      raise TypeError(f'Unsupported operand types {type(self)} and {type(other)}')

  def __radd__(self, other):
    return self.__add__(other)

  def __call__(self, text: any) -> str:
    text = str(text)
    return f'{self.marker}{text}{self.terminator}' if self.enabled else text

  def make(self, *args, **kwargs) -> Styling:
    return self

class CustomStyling(Styling):
  _marker: str
  _terminator: str

  def __init__(self, marker: str='', terminator: str=''):
    self.marker = marker
    self.terminator = terminator

  @property
  def marker(self) -> str:
    return self._marker
  
  @marker.setter
  def marker(self, marker: str):
    self._marker = marker

  @property
  def terminator(self) -> str:
    return self._terminator

  @terminator.setter
  def terminator(self, terminator: str):
    self._terminator = terminator

class StylingEnum(Styling, Enum):
  # See http://www.lihaoyi.com/post/BuildyourownCommandLinewithANSIescapecodes.html
  @property
  def marker(self) -> str:
    return self.value

  @property
  def terminator(self) -> str:
    return u'\u001b[0m'

class Color(StylingEnum):
  black = u'\u001b[30m'
  red = u'\u001b[31m'
  green = u'\u001b[32m'
  yellow = u'\u001b[33m'
  blue = u'\u001b[38;5;33m'
  magenta = u'\u001b[35m'
  cyan = u'\u001b[36m'
  white = u'\u001b[37m'
  gray = u'\u001b[30;1m'

  def make(self, white: Optional[float]=None):
    if white is None:
      return self
    code = str(232 + max(0, min(23, int(white * 23))))
    marker = u'\u001b[38;5;' + code + 'm'
    return CustomStyling(marker=marker, terminator=u'\u001b[0m')

class Font(StylingEnum):
  bold = u'\u001b[1m'
  underline = u'\u001b[4m'
  reversed = u'\u001b[7m'

class Format(Styling):
  factories: Dict[str, Styling] = {}
  styles: List[Styling]

  @classmethod
  def add_global_factories(cls, factories: Dict[str, Styling]):
    cls.factories = {
      **cls.factories,
      **factories,
    }

  def add_factories(self, factories: Dict[str, Styling]):
    self.factories = {
      **self.factories,
      **factories,
    }

  def __init__(self, styles: List[Styling]=[], factories: Dict[str, Styling]={}):
    self.factories = {**factories}
    self.styles = [*styles]

  @property
  def marker(self) -> str:
    return ''.join(s.marker for s in self.styles)

  @property
  def terminator(self) -> str:
    return ''.join(s.terminator for s in reversed(self.styles))

  def __repr__(self):
    return object.__repr__(self) + str(self.styles)

  def __dir__(self):
    result = object.__dir__(self)
    result += [k for k in self.factories.keys() if k not in result]
    result += [k for k in type(self).factories.keys() if k not in result]
    return result

  def __getattribute__(self, name):
    try:
      return object.__getattribute__(self, name)
    except Exception as e:
      if name in self.factories:
        factory = self.factories[name]
      elif name in type(self).factories:
        factory = type(self).factories[name]
      else:
        raise e 
      def f(*args, **kwargs):
        return self + factory.make(*args, **kwargs)
      return f

Format.add_global_factories({
  **{s.name: s for s in Color},
  'color': Color.gray,
  **{s.name: s for s in Font},
  'custom': CustomStyling(),
})

class Styled:
  @property
  def text(self) -> str:
    return ''

  @property
  def styled(self) -> str:
    return ''

  def __add__(self, other):
    if isinstance(self, Styleds) and isinstance(other, Styleds):
      return type(self)(parts=self.parts + other.parts)
    elif isinstance(self, Styleds) and isinstance(other, Styled):
      return type(self)(parts=self.parts + [other])
    elif isinstance(other, Styled):
      return Styleds(parts=[self, other])
    elif isinstance(other, Styling):
      return self.make(style=other)
    elif isinstance(other, str):
      return self + CustomStyled(text=other)
    else:
      raise TypeError(f'Unsupported operand types {type(self)} and {type(other)}')

  def __radd__(self, other):
    return self.__add__(other)

  def make(self, style: Optional[Styling]) -> Styled:
    return self

  def format(self, *args, **kwargs) -> Styled:
    return self

class CustomStyled(Styled):
  _text: str
  style: Styling

  def __init__(self, text: str, style: Optional[Styling]=None):
    self.text = text
    self.style = style if style else Format()

  @property
  def text(self) -> str:
    return self._text

  @text.setter
  def text(self, text: str):
    self._text = text

  @property
  def styled(self) -> str:
    return self.style(self.text)

  def make(self, style: Optional[Styling]) -> Styled:
    return type(self)(text=self.text, style=self.style + style if style else self.style)

  def format(self, *args, **kwargs) -> Styled:
    return type(self)(text=self.text.format(*args, **kwargs), style=self.style)

class Styleds(Styled):
  parts: List[Styled]

  def __init__(self, parts: List[Styled]=[]):
    self.parts = [*parts]

  @property
  def text(self) -> str:
    return ''.join(t.text for t in self.parts)

  @property
  def styled(self) -> str:
    return ''.join(t.styled for t in self.parts)

  def make(self, style: Optional[Styling]) -> Styled:
    return type(self)(parts=[p.make(style=style) for p in self.parts])

  def format(self, *args, **kwargs):
    return type(self)(parts=[p.format(*args, **kwargs) for p in self.parts])

class CodeStyled(Styled):
  _text: str
  lexer: pygments.lexer.Lexer
  formatter: pygments.formatter.Formatter

  def __init__(self, text: str, lexer: pygments.lexer.Lexer=PythonLexer(), formatter: pygments.formatter.Formatter=TerminalFormatter(bg='dark', linenos=True)):
    self.lexer = lexer
    self.formatter = formatter
    self._text = text
 
  @property
  def text(self) -> str:
    return self._text

  @text.setter
  def text(self, text: str):
    self._text = text

  @property
  def styled(self) -> str:
    return pygments.highlight(self.text, self.lexer, self.formatter)
