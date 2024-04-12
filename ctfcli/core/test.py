import os
import shutil
import stat
import subprocess
import tempfile
from enum import Enum
from os import PathLike
from pathlib import Path
from typing import Dict, List, Optional

class TestType(Enum):
    SOLUTION = 0
    STATUS = 1

    def __str__(self) -> str:
        if self == TestType.SOLUTION:
            return "solution"
        elif self == TestType.STATUS:
            return "status"

class Test:
    def __init__(self, script: PathLike, type: TestType, files: List[PathLike], base_path: Optional[PathLike] = None):
        self.type = type
        self.files: List[Path] = []
        self.base_path = Path(base_path) if base_path else Path(".")
        self.script: Path = Path(script)
        for file in files:
            new_file: Path = Path(file)
            if not (self.base_path / new_file).exists():
                raise FileNotFoundError(f"Could not find file '{file}' from test '{script}'")
            elif not (self.base_path / new_file).is_file():
                raise ValueError(f"'{file}' (required by '{script}') is not a file.")
            self.files.append(new_file)

    def run(self, timeout: float, environment: Dict[str, str] = {}) -> subprocess.CompletedProcess:
        # Just in case the test doesn't complete
        result: Optional[subprocess.CompletedProcess] = None
        # Set up for if we get an error
        error: Optional[Exception] = None
        # subprocess.TimeoutExpired will be the error we get if the test timed out

        # Create temporary folder
        temp_dir: str = tempfile.mkdtemp()
        
        # Enter try block so we can delete the folder if anything goes wrong
        try:
            # Copy accessible files
            for file in self.files:
                final_path: Path = Path(temp_dir, file)
                os.makedirs(final_path.parent, exist_ok=True)
                shutil.copy2(self.base_path / file, final_path)

            # Copy script
            script_path: Path = Path(temp_dir, self.script)
            os.makedirs(script_path.parent, exist_ok=True)
            shutil.copy2(self.base_path / self.script, script_path)

            # Make the script executable by current user if it wasn't
            st = os.stat(script_path)
            os.chmod(script_path, st.st_mode | stat.S_IEXEC)

            result = subprocess.run([script_path], capture_output=True, text=True, timeout=timeout, cwd=temp_dir, env=environment)

        except Exception as e:
            error = e
        finally:
            # Delete temporary files
            shutil.rmtree(temp_dir)

        if error:
            raise error
        else:
            return result