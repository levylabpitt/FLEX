"""FLEX package manager.

Lists, installs, and removes official FLEX packages (driving pip/uv underneath)
and manages driver-level enable/disable in the active configuration. The CLI
and the dashboard are thin UIs over this module.
"""

from flex.pkgmanager.catalog import load_catalog
from flex.pkgmanager.manager import DriverInfo, PackageInfo, PackageManager

__all__ = ["DriverInfo", "PackageInfo", "PackageManager", "load_catalog"]
