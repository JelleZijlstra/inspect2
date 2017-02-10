# inspect2
A backport of the Python 3.6 inspect module to Python 2.7-3.5.

This module was based on the code of the inspect module and its tests in the Python 3.6 
standard library and modified to pass tests on earlier Python versions.

I have tried to follow these rules in writing the code:
- Minimize changes relative to the 3.6 source. This should make backporting of future 
  changes easier.
- No support for old-style classes. Python 2 is hard enough without them.
- All functions should be available on all versions. `inspect2.iscoroutinefunction()` 
  just always returns False on Python versions that don't have `async def`.
