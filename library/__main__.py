"""Lets the package run as a program: python -m library --help"""

import sys

from .cli import main

sys.exit(main())
