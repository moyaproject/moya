"""
Runs the Moya command line app

This allows Moya to be run with the following:

    python -m moya

"""

import sys
from .command.app import main

sys.exit(main())
