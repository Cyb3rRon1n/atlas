"""
The ATLAS_* environment names were read until 1.2. Since 1.3 only LANXANG_* is read; this finds the old ones so
Lanxang can say which to rename instead of silently ignoring them.
"""

import os


def old_variables(environ=None):

    environ = os.environ if environ is None else environ
    return sorted(key for key, value in environ.items() if key.startswith("ATLAS_") and value)
