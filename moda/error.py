class ModaError(Exception):
  pass

class ModaTimeoutError(ModaError):
  pass

class ModaCannotInteractError(ModaError):
  pass