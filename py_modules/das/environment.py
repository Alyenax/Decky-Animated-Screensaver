"""Only explicitly verified library paths may enter media subprocesses."""
import os

def clean_environment():
    value=dict(os.environ)
    for name in ('LD_LIBRARY_PATH','LD_PRELOAD','PYTHONHOME','PYTHONPATH'):
        value.pop(name,None)
    return value
