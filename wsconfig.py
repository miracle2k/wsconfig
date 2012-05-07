#!/usr/bin/env python

# Exists to run this from a development checkout. Because we cannot run
# the wsconfig.script module directly due to relative imports.

import wsconfig.script
wsconfig.script.run()
