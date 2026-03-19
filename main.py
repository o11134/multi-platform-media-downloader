from __future__ import annotations

import sys
import traceback

import customtkinter as ctk

from ui.main_window import MainWindow


def _show_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(message, file=sys.stderr)


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    sys.excepthook = _show_unhandled_exception

    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
