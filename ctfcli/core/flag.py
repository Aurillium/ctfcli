import re
from enum import Enum

class FlagType(Enum):
    STATIC = 0
    REGEX = 1

# Represents a flag, can be used to check a potential submission
class Flag:
    def __init__(self, content: str, type: FlagType = FlagType.STATIC, case_sensitive: bool = True) -> None:
        self.content: str = content if case_sensitive else content.lower()
        self.type: FlagType = type
        self.case_sensitive: bool = case_sensitive
        if self.type == FlagType.REGEX:
            self._regex: re.Pattern = re.compile(self.content if case_sensitive else self.content.lower())

    def check(self, value: str) -> bool:
        if not self.case_sensitive:
            value = value.lower()
        if self.type == FlagType.STATIC:
            return self.content == value
        else:
            return self._regex.match(value)
