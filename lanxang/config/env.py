"""
Settings in the environment under the new LANXANG_ names or the old ATLAS_ ones (until 1.2). Each name that is set
fills its missing counterpart, so the code reads LANXANG_* only and old .env files, compose files and atlas.yaml
${ATLAS_*} references keep working. An empty variable (compose's ${X:-}) counts as unset.
"""

import os

NEW, OLD = "LANXANG_", "ATLAS_"


def mirror(environ=None):
    environ = os.environ if environ is None else environ
    for src, dst in ((NEW, OLD), (OLD, NEW)):
        for key, value in list(environ.items()):
            if key.startswith(src) and value and not environ.get(dst + key[len(src):]):
                environ[dst + key[len(src):]] = value
