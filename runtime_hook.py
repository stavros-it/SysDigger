import os
import sys

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))
    os.environ.setdefault("QT_PLUGIN_PATH",
                          os.path.join(sys._MEIPASS, "PySide6", "plugins"))
