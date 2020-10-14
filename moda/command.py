from typing import Callable

def invoke_subcommand(context_aware: bool=True, moda_aware: bool=False) -> Callable[[Callable], Callable]:
  def decorator(f: Callable):
    def wrapper(*args, **kwargs):
      context = args[0]
      command_args = args if context_aware else args[1:]
      command_kwargs = kwargs if moda_aware else {k: v for k, v in kwargs.items() if k not in ['_moda_subcommand', '_moda_subcommand_parameters']}
      result = f(*command_args, **command_kwargs)
      if '_moda_subcommand' in kwargs:
        subcommand_result = context.invoke(
          kwargs['_moda_subcommand'],
          **(kwargs['_moda_subcommand_parameters'] if '_moda_subcommand_parameters' in kwargs else {}),
        )
        return subcommand_result
      else:
        return result
    return wrapper
  return decorator