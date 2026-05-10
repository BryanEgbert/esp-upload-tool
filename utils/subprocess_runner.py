import subprocess
import re
from typing import Callable

class SubprocessRunner:
    @staticmethod
    def _strip_ansi_escape(text: str) -> str:
        """Remove ANSI escape sequences from text."""
        # Remove ANSI escape sequences (e.g., \x1b[1A, \033[2K, etc.)
        ansi_escape = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
        return ansi_escape.sub('', text)

    @staticmethod
    def run_command(
        command: list[str],
        log_callback: Callable[[str], None],
    ) -> int:
        """
        Runs a command and yields output line by line.
        """
        # Ensure we use the full path to the scripts if they are in the venv
        # This is a precaution since we are in a venv
        log_callback(f"Running command: {' '.join(command)}")
        
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0, # Unbuffered for real-time output
            universal_newlines=True
        )

        if process.stdout:
            while True:
                char = process.stdout.read(1)
                if not char and process.poll() is not None:
                    break
                
                line = char
                if char == '\r' or char == '\n':
                    pass
                else:
                    while True:
                        next_char = process.stdout.read(1)
                        if not next_char or next_char == '\r' or next_char == '\n':
                            break
                        line += next_char
                
                clean_line = line.strip()
                if clean_line:
                    clean_line = SubprocessRunner._strip_ansi_escape(clean_line)
                    log_callback(clean_line)

        return process.wait()
