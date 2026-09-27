"""Entry script for the frozen app.

PyInstaller runs its entry script as a top-level module, where the relative
imports in ``label_printer/__main__.py`` wouldn't work, so this imports the
package normally instead.
"""

import sys

from label_printer.__main__ import main

sys.exit(main())
