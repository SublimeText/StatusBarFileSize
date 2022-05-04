from collections import defaultdict
from functools import partial, lru_cache
import io
import os.path
import zlib

import sublime
import sublime_plugin


# Format a size in bytes into a nicer string value. Defaults to 1024 convention.
def file_size_str(size, units='binary'):
    if size is None:
        return None
    divisor = 1024 if units == 'binary' else 1000
    binary_middle = "i" if units == 'binary' else ""
    sizes = "KMGTPEZY"
    if size < divisor:
        return "{} {}".format(size, "Bytes" if size != 1 else "Byte")

    size_val = size
    for unit in sizes:
        size_val /= divisor
        if size_val < divisor:
            break
    return "{:.2} {}{}B".format(size_val, unit, binary_middle)


# Far from a perfect system, but seems to be the only way to get a usable Python
# encoding from Sublime Text.
SPECIAL_HEXADECIMAL = "special-hexadecimal"

ENCODING_MAP = {
    "Undefined": "utf-8",
    "Hexadecimal": SPECIAL_HEXADECIMAL,
    "UTF-8": "utf-8",
    "UTF-16 LE": "utf-16le",
    "UTF-16 BE": "utf-16be",

    "Western (Windows 1252)": "windows-1252",
    "Western (ISO 8859-1)": "iso-8859-1",
    "Western (ISO 8859-3)": "iso-8859-3",
    "Western (ISO 8859-15)": "iso-8859-15",
    "Western (Mac Roman)": "mac_roman",
    "DOS (CP 437)": "cp-437",

    "Arabic (Windows 1256)": "windows-1256",
    "Arabic (ISO 8859-6)": "iso-8859-6",

    "Baltic (Windows 1257)": "windows-1257",
    "Baltic (ISO 8859-4)": "iso-8859-4",

    "Celtic (ISO 8859-14)": "iso-8859-14",

    "Central European (Windows 1250)": "windows-1250",
    "Central European (ISO 8859-2)": "iso-8859-2",

    "Cyrillic (Windows 1251)": "windows-1251",
    "Cyrillic (Windows 866)": "windows-866",
    "Cyrillic (ISO 8859-5)": "iso-8859-5",
    "Cyrillic (KOI8-R)": "koi8_r",
    "Cyrillic (KOI8-U)": "koi8_u",

    "Estonian (ISO 8859-13)": "iso-8859-13",

    "Greek (Windows 1253)": "windows-1253",
    "Greek (ISO 8859-7)": "iso-8859-7",

    "Hebrew (Windows 1255)": "windows-1255",
    "Hebrew (ISO 8859-8)": "iso-8859-8",

    "Nordic (ISO 8859-10)": "iso-8859-10",

    "Romanian (ISO 8859-16)": "iso-8859-16",

    "Turkish (Windows 1254)": "windows-1254",
    "Turkish (ISO 8859-9)": "iso-8859-9",

    "Vietnamese (Windows 1258)": "windows-1258",
}

# Ditto for line endings. At least there's only three forms here.
LINE_ENDINGS_MAP = {
    "Unix": "\n",
    "Windows": "\r\n",
    "CR": "\r",
}

BLOCK_SIZE = 1000


class ViewHasChanged(Exception):
    pass


def ranges(start, end, bs):
    i = 0
    while i < end:
        yield (i, min(i + bs, end))
        i += bs


def count_hex_digits(s):
    # Count hexadecimal digits in s.
    return sum(1 for x in s if x in "abcdefABCDEF0123456789")


def estimate_file_size(view, deflate):
    tag = view.change_count()

    try:
        line_endings = LINE_ENDINGS_MAP[view.line_endings()]
        encoding = ENCODING_MAP[view.encoding()]
    except KeyError:
        # Unknown encoding or line ending, so we fail.
        return None, None

    size = 0
    data = io.BytesIO()
    for start, end in ranges(0, view.size(), BLOCK_SIZE):
        if view.change_count() != tag:
            raise ViewHasChanged()
        r = sublime.Region(start, end)
        text = view.substr(r)

        if encoding == SPECIAL_HEXADECIMAL:
            # Special-case handling for the special-case Hexadecimal encoding.
            # The division doesn't truncate on purpose, to count half-bytes when
            # we have uneven numbers of hex digits. The result gets forced into
            # an int on return.
            size += count_hex_digits(text) / 2
        else:
            try:
                encoded_text = text.replace("\n", line_endings).encode(encoding)
                size += len(encoded_text)
                if deflate:
                    data.write(encoded_text)
            except UnicodeError:
                # Encoding failed, we just fail here.
                return None, None

    deflate_size = len(zlib.compress(data.getvalue())) if deflate else None
    return int(size), deflate_size


class StatusBarFileSize(sublime_plugin.EventListener):
    KEY_SIZE = "FileSize"
    SETTINGS = "StatusBarFileSize.sublime-settings"

    @property
    @lru_cache(maxsize=1)
    def settings(self):
        return sublime.load_settings(self.SETTINGS)

    def update_file_size(self, view):
        deflate = self.settings.get("deflate", False)

        size, deflate_size = None, None
        estimate = False

        path = view.file_name()
        if not path or view.is_dirty():
            if self.settings.get("estimate_file_size", True):
                estimate = True
                # Estimate the file size based on encoding and line endings.
                try:
                    size, deflate_size = estimate_file_size(view, deflate)
                except ViewHasChanged:
                    # If the buffer was changed, abort this procedure as another size
                    # calculation is already in progress.
                    # Too many changes to the status bar item would only cause flickering.
                    return
        else:
            try:
                size = os.path.getsize(path)
                if deflate:
                    with open(view.file_name(), 'rb') as f:
                        deflate_size = len(zlib.compress(f.read()))
            except OSError:
                pass

        units = self.settings.get('units', 'binary')
        if size is not None:
            status_texts = [file_size_str(size, units)]
            if deflate and deflate_size:
                status_texts.append("(gzip: {})".format(file_size_str(deflate_size, units)))
            status_text = "{}{}".format("~" if estimate else "", " ".join(status_texts))
            view.set_status(self.KEY_SIZE, status_text)
        else:
            view.erase_status(self.KEY_SIZE)

    # Basically cheap semaphores since we're always on the same thread.
    call_cache = defaultdict(int)

    def _check_call(self, view):
        self.call_cache[view] -= 1
        if self.call_cache[view] == 0:
            del self.call_cache[view]
            self.update_file_size(view)

    def update_file_size_debounced(self, view):
        delay = self.settings.get('typing_delay', 200)
        self.call_cache[view] += 1
        sublime.set_timeout_async(partial(self._check_call, view), delay)

    on_post_save_async = update_file_size_debounced
    on_modified_async = update_file_size_debounced
    on_activated_async = update_file_size_debounced
