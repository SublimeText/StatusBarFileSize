# Status Bar File Size

Displays file size in the Sublime Text status bar.
Where possible, the size is queried from the file system.
If this information is not available
-- e.g. for a buffer that was modified and not yet saved --
the file size is estimated
from the buffer contents and chosen encoding.

Additionally,
the file size after DEFLATE compression, as used by gzip,
can be enabled in the settings.


## Installation

Use [Package Control][pkgctrl].

This package only supports Sublime Text 3 and 4.

[pkgctrl]: https://packagecontrol.io


## Configuration

The default and user configuration files can be accessed from the Sublime Text
menu bar, *Preferences -> Package Settings -> Status Bar File Size*.


## About

The source code is available on [GitHub][src]
and licensed under a BSD 3-Clause License.

[src]: https://github.com/SublimeText/StatusBarFileSize
