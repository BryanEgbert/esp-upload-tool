from PySide6.QtCore import Signal
from esptool.logger import TemplateLogger
from typing import Union, Callable

class SignalLogger(TemplateLogger):
    """
    Custom logger that redirects esptool/espefuse output to a Qt Signal or callable.
    NOTE: esptool.logger.log.set_logger changes the __class__ of the 
    global singleton instance. __init__ is NOT called on that instance.
    We use a class attribute to pass the signal/handler.
    """
    _handler: Union[Signal, Callable[[str], None]] = None

    def print(self, message="", *args, **kwargs):
        if SignalLogger._handler:
            if args:
                message = " ".join([str(message)] + [str(a) for a in args])
            
            msg_str = str(message)
            if isinstance(SignalLogger._handler, Signal):
                SignalLogger._handler.emit(msg_str)
            else:
                SignalLogger._handler(msg_str)

    def note(self, message):
        self.print(f"Note: {message}")

    def warning(self, message):
        self.print(f"Warning: {message}")

    def error(self, message):
        self.print(f"Error: {message}")

    def stage(self, finish=False):
        pass

    def progress_bar(self, cur_iter, total_iters, prefix="", suffix="", bar_length=30):
        if SignalLogger._handler:
            percent = 100 * (cur_iter / float(total_iters)) if total_iters > 0 else 0
            msg = f"{prefix} [{percent:.1f}%] {suffix}"
            if isinstance(SignalLogger._handler, Signal):
                SignalLogger._handler.emit(msg)
            else:
                SignalLogger._handler(msg)

    def set_verbosity(self, verbosity):
        pass
