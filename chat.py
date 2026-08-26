#!/usr/bin/env python3
"""NVIDIA AI API CLI — single file.
 
Multiline prompt_toolkit frontend + originalchat client
(NvidiaChat, ModelCatalog, StreamPrinter).
 
Install:
  pip install prompt_toolkit rich requests
 
Usage:
  export NVIDIA_API_KEY='nvapi-...'
  python nvidia_chat.py
  python nvidia_chat.py --thinking
"""
from __future__ import annotations
 
import argparse
import json
import os
import re
import shutil
import sys
import time
from typing import Any, Dict, List, Optional
 
try:
    import requests
except ImportError:
    print("Missing dependency: requests")
    print("  pip install prompt_toolkit rich requests")
    sys.exit(1)
 
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.styles import Style
except ImportError:
    print("Missing dependency: prompt_toolkit")
    print("  pip install prompt_toolkit rich requests")
    sys.exit(1)
 
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
 
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None
 
 
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
DEFAULT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TIMEOUT = 300
DEFAULT_TEMPERATURE = 1.0
DEFAULT_TOP_P = 0.95
MAX_RETRIES = 2
MODELS_URL = "https://integrate.api.nvidia.com/v1/models"
NON_CHAT_HINTS = (
    "embed",
    "rerank",
    "nvclip",
    "retrieve",
    "stable-diffusion",
    "sdxl",
    "flux",
    "imagen",
    "whisper",
    "parakeet",
    "tts",
    "asr",
    "cosmos",
    "edify",
)
 
 
class C:
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    END = "\033[0m"
 
 
def _enable_windows_ansi() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
 
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass
 
 
_enable_windows_ansi()
 
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
HDR_BG = "\033[48;5;238m"
HDR_FG = "\033[38;5;249m"
CODE_BG = "\033[48;5;236m"
CODE_FG = "\033[38;5;252m"
KW = "\033[38;5;177m"
TYP = "\033[38;5;81m"
FN = "\033[38;5;75m"
STR = "\033[38;5;114m"
CMT = "\033[38;5;244m\033[3m"
NUM = "\033[38;5;215m"
PP = "\033[38;5;208m"
PUN = "\033[38;5;246m"
INLINE_BG = "\033[48;5;238m\033[38;5;228m"
HEAD_FG = "\033[1m\033[38;5;159m"
QUOTE_FG = "\033[38;5;245m"
ANSI_RE = re.compile(r"\033\[[0-9;]*m")
 
 
def _vislen(s: str) -> int:
    return len(ANSI_RE.sub("", s))
 
 
def _term_width() -> int:
    try:
        w = shutil.get_terminal_size((80, 24)).columns
    except Exception:
        w = 80
    return max(48, min(w - 1, 99))
 
 
LANG_ALIASES = {
    "c++": "cpp",
    "cc": "cpp",
    "h": "cpp",
    "hpp": "cpp",
    "hxx": "cpp",
    "c": "c",
    "py": "python",
    "python3": "python",
    "js": "javascript",
    "jsx": "javascript",
    "ts": "javascript",
    "tsx": "javascript",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "console": "bash",
    "yml": "yaml",
    "text": "",
    "txt": "",
    "output": "",
    "plaintext": "",
}
 
KEYWORDS: Dict[str, set] = {
    "python": {
        "and", "as", "assert", "async", "await", "break", "class", "continue",
        "def", "del", "elif", "else", "except", "False", "finally", "for",
        "from", "global", "if", "import", "in", "is", "lambda", "None",
        "nonlocal", "not", "or", "pass", "raise", "return", "True", "try",
        "while", "with", "yield",
    },
    "cpp": {
        "alignas", "alignof", "and", "and_eq", "asm", "auto", "bitand", "bitor",
        "bool", "break", "case", "catch", "char", "char8_t", "char16_t",
        "char32_t", "class", "compl", "concept", "const", "consteval",
        "constexpr", "constinit", "const_cast", "continue", "co_await",
        "co_return", "co_yield", "decltype", "default", "delete", "do",
        "double", "dynamic_cast", "else", "enum", "explicit", "export",
        "extern", "false", "float", "for", "friend", "goto", "if", "inline",
        "int", "long", "mutable", "namespace", "new", "noexcept", "not",
        "not_eq", "nullptr", "operator", "or", "or_eq", "private", "protected",
        "public", "register", "reinterpret_cast", "requires", "return",
        "short", "signed", "sizeof", "static", "static_assert", "static_cast",
        "struct", "switch", "template", "this", "thread_local", "throw", "true",
        "try", "typedef", "typeid", "typename", "union", "unsigned", "using",
        "virtual", "void", "volatile", "wchar_t", "while", "xor", "xor_eq",
        "include", "define", "ifdef", "ifndef", "endif", "pragma", "undef",
    },
    "c": {
        "auto", "break", "case", "char", "const", "continue", "default", "do",
        "double", "else", "enum", "extern", "float", "for", "goto", "if",
        "inline", "int", "long", "register", "restrict", "return", "short",
        "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
        "unsigned", "void", "volatile", "while", "include", "define", "ifdef",
        "ifndef", "endif", "pragma", "_Bool", "_Complex", "true", "false",
        "NULL",
    },
    "javascript": {
        "await", "break", "case", "catch", "class", "const", "continue",
        "debugger", "default", "delete", "do", "else", "export", "extends",
        "false", "finally", "for", "function", "if", "import", "in",
        "instanceof", "let", "new", "null", "return", "static", "super",
        "switch", "this", "throw", "true", "try", "typeof", "undefined", "var",
        "void", "while", "with", "yield", "async", "of",
    },
    "bash": {
        "if", "then", "else", "elif", "fi", "for", "while", "do", "done", "in",
        "case", "esac", "function", "return", "exit", "echo", "export", "local",
        "readonly", "shift", "break", "continue", "true", "false",
    },
    "rust": {
        "as", "async", "await", "break", "const", "continue", "crate", "dyn",
        "else", "enum", "extern", "false", "fn", "for", "if", "impl", "in",
        "let", "loop", "match", "mod", "move", "mut", "pub", "ref", "return",
        "self", "Self", "static", "struct", "super", "trait", "true", "type",
        "unsafe", "use", "where", "while",
    },
    "go": {
        "break", "case", "chan", "const", "continue", "default", "defer",
        "else", "fallthrough", "for", "func", "go", "goto", "if", "import",
        "interface", "map", "package", "range", "return", "select", "struct",
        "switch", "type", "var", "true", "false", "nil",
    },
    "java": {
        "abstract", "assert", "boolean", "break", "byte", "case", "catch",
        "char", "class", "const", "continue", "default", "do", "double", "else",
        "enum", "extends", "final", "finally", "float", "for", "goto", "if",
        "implements", "import", "instanceof", "int", "interface", "long",
        "native", "new", "package", "private", "protected", "public", "return",
        "short", "static", "strictfp", "super", "switch", "synchronized",
        "this", "throw", "throws", "transient", "true", "false", "null", "try",
        "void", "volatile", "while",
    },
}
KEYWORDS["cpp"] = KEYWORDS["cpp"] | KEYWORDS["c"]
 
TYPES = {
    "cpp": {
        "int", "char", "void", "bool", "float", "double", "long", "short",
        "unsigned", "signed", "size_t", "wchar_t", "string", "vector", "map",
        "auto", "int8_t", "int16_t", "int32_t", "int64_t", "uint8_t", "uint32_t",
        "uint64_t",
    },
    "c": {
        "int", "char", "void", "float", "double", "long", "short", "unsigned",
        "signed", "size_t", "FILE",
    },
    "python": {"int", "str", "float", "bool", "list", "dict", "set", "tuple", "None"},
    "javascript": {
        "number", "string", "boolean", "object", "Array", "Promise", "Map", "Set",
    },
}
 
 
def _norm_lang(lang: str) -> str:
    lang = (lang or "").strip().lower()
    return LANG_ALIASES.get(lang, lang)
 
 
def highlight_line(line: str, lang: str) -> str:
    lang = _norm_lang(lang)
    kws = KEYWORDS.get(lang, set())
    types = TYPES.get(lang, set())
    if not line:
        return ""
    out: List[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if lang in ("python", "bash", "yaml") and ch == "#" and (
            i == 0 or line[i - 1].isspace()
        ):
            out.append(CMT + line[i:] + RESET + CODE_BG + CODE_FG)
            break
        if lang not in ("python", "bash") and line[i : i + 2] == "//":
            out.append(CMT + line[i:] + RESET + CODE_BG + CODE_FG)
            break
        if line[i : i + 2] == "/*":
            end = line.find("*/", i + 2)
            if end == -1:
                out.append(CMT + line[i:] + RESET + CODE_BG + CODE_FG)
                break
            out.append(CMT + line[i : end + 2] + RESET + CODE_BG + CODE_FG)
            i = end + 2
            continue
        if ch == "#" and i == 0 and lang in ("cpp", "c"):
            m = re.match(r"(#\s*\w+)(.*)$", line)
            if m:
                rest = m.group(2)
                rest_h = re.sub(
                    r'(<[^>]+>|"[^"]+")',
                    lambda mm: STR + mm.group(0) + RESET + CODE_BG + CODE_FG,
                    rest,
                )
                return PP + m.group(1) + RESET + CODE_BG + CODE_FG + rest_h
            out.append(PP + line + RESET + CODE_BG + CODE_FG)
            break
        if ch in ('"', "'"):
            q = ch
            j = i + 1
            while j < n:
                if line[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if line[j] == q:
                    j += 1
                    break
                j += 1
            out.append(STR + line[i:j] + RESET + CODE_BG + CODE_FG)
            i = j
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and line[i + 1].isdigit()):
            j = i + 1
            while j < n and (line[j].isalnum() or line[j] in "._"):
                j += 1
            out.append(NUM + line[i:j] + RESET + CODE_BG + CODE_FG)
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (line[j].isalnum() or line[j] == "_"):
                j += 1
            word = line[i:j]
            nxt = line[j] if j < n else ""
            if word in kws:
                out.append(KW + word + RESET + CODE_BG + CODE_FG)
            elif word in types:
                out.append(TYP + word + RESET + CODE_BG + CODE_FG)
            elif nxt == "(":
                out.append(FN + word + RESET + CODE_BG + CODE_FG)
            else:
                out.append(CODE_FG + word)
            i = j
            continue
        out.append(PUN + ch + RESET + CODE_BG + CODE_FG)
        i += 1
    return "".join(out)
 
 
def _paint(content_ansi: str, width: int, bg: str = CODE_BG) -> str:
    pad_l = 2
    inner = max(8, width - pad_l)
    vis = _vislen(content_ansi)
    if vis > inner:
        raw = ANSI_RE.sub("", content_ansi)[: inner - 1] + "…"
        content_ansi = CODE_FG + raw
        vis = _vislen(content_ansi)
    pad = inner - vis
    return f"{bg}{' ' * pad_l}{content_ansi}{' ' * pad}{RESET}"
 
 
def _paint_header(lang: str, width: int) -> str:
    label = _norm_lang(lang) or "code"
    text = f"{HDR_FG}{label}{RESET}{HDR_BG}"
    return _paint(text, width, bg=HDR_BG)
 
 
class StreamPrinter:
    def __init__(self, out=None):
        self.out = out or sys.stdout
        self.width = _term_width()
        self.in_code = False
        self.collecting_lang = False
        self.lang_buf = ""
        self.lang = ""
        self.code_line = ""
        self.code_at_line_start = False
        self.close_probe = ""
        self.closing = False
        self.partial_code = False
        self.at_line_start = True
        self.fence_probe = ""
        self.struct_buf: Optional[str] = None
        self.inline = "n"
        self.inline_buf = ""
 
    def _w(self, s: str) -> None:
        self.out.write(s)
        self.out.flush()
 
    def feed(self, chunk: str) -> None:
        if not chunk:
            return
        for ch in chunk:
            self._ch(ch)
 
    def finish(self) -> None:
        if self.fence_probe:
            self._prose(self.fence_probe)
            self.fence_probe = ""
        if self.struct_buf is not None:
            self._emit_structural(self.struct_buf)
            self.struct_buf = None
        if self.inline != "n":
            marker = {
                "tick": "`",
                "star": "*",
                "italic": "*",
                "bold": "**",
                "bold2": "**",
            }[self.inline]
            self._w(marker + self.inline_buf)
            self.inline = "n"
            self.inline_buf = ""
        if self.in_code:
            if self.collecting_lang:
                self.lang = self.lang_buf.strip()
                self.collecting_lang = False
                self._open_block(self.lang)
            if self.close_probe:
                self._code_text(self.close_probe)
                self.close_probe = ""
            self._close_block()
            self.in_code = False
        if not self.at_line_start:
            self._w("\n")
            self.at_line_start = True
 
    def _open_block(self, lang: str) -> None:
        self.width = _term_width()
        self._w("\033[?25l")
        self._w("\n" + _paint_header(lang, self.width) + "\n")
        self.partial_code = False
 
    def _close_block(self) -> None:
        if self.code_line or self.partial_code:
            self._commit_code_line()
        self._w(_paint("", self.width) + "\n\n")
        self._w("\033[?25h")
 
    def _ch(self, ch: str) -> None:
        if ch == "\r":
            return
        if self.in_code:
            self._code_ch(ch)
            return
        if self.struct_buf is not None:
            if ch == "\n":
                self._emit_structural(self.struct_buf)
                self.struct_buf = None
                self.at_line_start = True
            else:
                self.struct_buf += ch
            return
        if self.at_line_start:
            if self.fence_probe:
                if ch == "`" and len(self.fence_probe) < 3:
                    self.fence_probe += "`"
                    if self.fence_probe == "```":
                        self.fence_probe = ""
                        self.in_code = True
                        self.collecting_lang = True
                        self.lang_buf = ""
                        self.at_line_start = False
                    return
                self._prose(self.fence_probe)
                self.fence_probe = ""
                self.at_line_start = False
                self._ch(ch)
                return
            if ch == "`":
                self.fence_probe = "`"
                return
            if ch in "#>":
                self.struct_buf = ch
                self.at_line_start = False
                return
            if ch == "\n":
                self._w("\n")
                return
            self.at_line_start = False
        if ch == "\n":
            self._prose("\n")
            self.at_line_start = True
            return
        self._prose(ch)
 
    def _code_ch(self, ch: str) -> None:
        if self.collecting_lang:
            if ch == "\n":
                self.lang = self.lang_buf.strip()
                self.collecting_lang = False
                self.code_at_line_start = True
                self.code_line = ""
                self._open_block(self.lang)
            else:
                self.lang_buf += ch
            return
        if self.closing:
            if ch == "\n":
                self._close_block()
                self.in_code = False
                self.closing = False
                self.at_line_start = True
            return
        if self.code_at_line_start:
            if self.close_probe:
                if ch == "`" and len(self.close_probe) < 3:
                    self.close_probe += "`"
                    if self.close_probe == "```":
                        self.close_probe = ""
                        self.closing = True
                    return
                self._code_text(self.close_probe)
                self.close_probe = ""
                self.code_at_line_start = False
                self._code_ch(ch)
                return
            if ch == "`":
                self.close_probe = "`"
                return
            if ch == "\n":
                self._commit_code_line()
                self.code_at_line_start = True
                return
            self.code_at_line_start = False
            self._code_text(ch)
            return
        if ch == "\n":
            self._commit_code_line()
            self.code_at_line_start = True
            return
        self._code_text(ch)
 
    def _code_text(self, s: str) -> None:
        self.code_line += s
        painted = _paint(highlight_line(self.code_line, self.lang), self.width)
        self._w("\r\033[2K" + painted)
        self.partial_code = True
 
    def _commit_code_line(self) -> None:
        painted = _paint(highlight_line(self.code_line, self.lang), self.width)
        self._w("\r\033[2K" + painted + "\n")
        self.code_line = ""
        self.partial_code = False
 
    def _prose(self, s: str) -> None:
        for ch in s:
            self._prose_ch(ch)
 
    def _prose_ch(self, ch: str) -> None:
        if ch == "\n":
            if self.inline != "n":
                marker = {
                    "tick": "`",
                    "star": "*",
                    "italic": "*",
                    "bold": "**",
                    "bold2": "**",
                }[self.inline]
                self._w(marker + self.inline_buf)
                self.inline = "n"
                self.inline_buf = ""
            self._w("\n")
            return
        if self.inline == "n":
            if ch == "`":
                self.inline = "tick"
                self.inline_buf = ""
                return
            if ch == "*":
                self.inline = "star"
                self.inline_buf = ""
                return
            self._w(ch)
            return
        if self.inline == "tick":
            if ch == "`":
                self._w(INLINE_BG + " " + self.inline_buf + " " + RESET)
                self.inline = "n"
                self.inline_buf = ""
            else:
                self.inline_buf += ch
            return
        if self.inline == "star":
            if ch == "*":
                self.inline = "bold"
                return
            self.inline = "italic"
            self.inline_buf += ch
            return
        if self.inline == "italic":
            if ch == "*":
                self._w(ITALIC + self.inline_buf + RESET)
                self.inline = "n"
                self.inline_buf = ""
            else:
                self.inline_buf += ch
            return
        if self.inline == "bold":
            if ch == "*":
                self.inline = "bold2"
            else:
                self.inline_buf += ch
            return
        if self.inline == "bold2":
            if ch == "*":
                self._w(BOLD + self.inline_buf + RESET)
                self.inline = "n"
                self.inline_buf = ""
            else:
                self.inline_buf += "*" + ch
                self.inline = "bold"
            return
 
    def _emit_structural(self, line: str) -> None:
        stripped = line.lstrip()
        if stripped.startswith("###"):
            title = stripped.lstrip("#").strip()
            self._w(f"\n{HEAD_FG}{title}{RESET}\n")
        elif stripped.startswith("##"):
            title = stripped.lstrip("#").strip()
            self._w(f"\n{HEAD_FG}{BOLD}{title}{RESET}\n")
        elif stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            self._w(f"\n{HEAD_FG}{BOLD}{title}{RESET}\n")
        elif stripped.startswith(">"):
            body = stripped[1:].lstrip()
            self._w(f"{QUOTE_FG}│ {RESET}")
            saved = (self.inline, self.inline_buf)
            self.inline, self.inline_buf = "n", ""
            self._prose(body)
            self.inline, self.inline_buf = saved
            self._w("\n")
        else:
            self._prose(line)
            self._w("\n")
 
 
def fetch_models(api_key: str, url: str = MODELS_URL, timeout: int = 30) -> List[str]:
    resp = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    items = data.get("data") or data.get("models") or []
    ids: List[str] = []
    for item in items:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            mid = item.get("id") or item.get("name")
            if mid:
                ids.append(str(mid))
    return sorted(set(ids), key=str.lower)
 
 
def is_chat_model(model_id: str) -> bool:
    low = model_id.lower()
    return not any(h in low for h in NON_CHAT_HINTS)
 
 
class ModelCatalog:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.all_ids: List[str] = []
        self.last_shown: List[str] = []
        self.pick_pending = False
 
    def ensure(self) -> List[str]:
        if not self.all_ids:
            print(f"{C.DIM}Fetching model list...{C.END}")
            self.all_ids = fetch_models(self.api_key)
        return self.all_ids
 
 
def print_model_list(models: List[str], current: str) -> None:
    if not models:
        print(f"{C.YELLOW}No models to show.{C.END}")
        return
    width = len(str(len(models)))
    for i, mid in enumerate(models, 1):
        mark = "*" if mid == current else " "
        line = f"{mark} {str(i).rjust(width)}. {mid}"
        if mid == current:
            print(f"{C.GREEN}{C.BOLD}{line}{C.END}")
        else:
            print(line)
    print(f"\n{len(models)} models | current: {C.CYAN}{current}{C.END}")
    print("Select with  /model <number>  or  /model <id>")
    print("Filter with  /model llama")
 
 
def handle_model_command(arg: str, client: NvidiaChat, catalog: ModelCatalog) -> None:
    arg = arg.strip().strip('"').strip("'")
    try:
        all_ids = catalog.ensure()
    except Exception as e:
        print(f"{C.RED}Could not list models:{C.END} {e}")
        return
    chat_ids = [m for m in all_ids if is_chat_model(m)]
    pool = chat_ids or all_ids
    if not arg:
        catalog.last_shown = pool
        catalog.pick_pending = True
        print_model_list(pool, client.model)
        return
    if arg.isdigit():
        source = catalog.last_shown or pool
        idx = int(arg)
        if 1 <= idx <= len(source):
            client.model = source[idx - 1]
            catalog.pick_pending = False
            print(f"{C.GREEN}Model set to {client.model}{C.END}")
            return
        print(f"{C.RED}No model #{idx}.{C.END} Run /model first.")
        return
    exact = [m for m in all_ids if m.lower() == arg.lower()]
    if exact:
        client.model = exact[0]
        catalog.pick_pending = False
        print(f"{C.GREEN}Model set to {client.model}{C.END}")
        return
    matches = [m for m in pool if arg.lower() in m.lower()]
    if len(matches) == 1:
        client.model = matches[0]
        catalog.pick_pending = False
        print(f"{C.GREEN}Model set to {client.model}{C.END}")
        return
    if matches:
        catalog.last_shown = matches
        catalog.pick_pending = True
        print_model_list(matches, client.model)
        return
    print(f"{C.RED}No model matching {arg!r}{C.END}")
    print("Try /model to list, or paste a full id like nvidia/nemotron-3-super-120b-a12b")
 
 
class NvidiaChat:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_URL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        timeout: int = DEFAULT_TIMEOUT,
        enable_thinking: bool = False,
        stream: bool = True,
        show_thinking: bool = True,
        on_thinking: Optional[Any] = None,
        on_content: Optional[Any] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout
        self.enable_thinking = enable_thinking
        self.stream = stream
        self.show_thinking = show_thinking
        self.on_thinking = on_thinking
        self.on_content = on_content
        self.messages: List[Dict[str, Any]] = []
 
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if self.stream else "application/json",
        }
 
    def _payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": self.stream,
        }
        if self.enable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": True}
        return payload
 
    def _print_thinking_header(self) -> None:
        print(f"\n{C.DIM}🤔 Thinking...{C.END}")
 
    def _print_thinking_chunk(self, text: str) -> None:
        print(f"{C.DIM}{text}{C.END}", end="", flush=True)
 
    def _print_assistant_header(self) -> None:
        print(f"\n{C.GREEN}{C.BOLD}Assistant:{C.END}")
 
    def _stream_response(self, response: requests.Response) -> str:
        full_content: List[str] = []
        thinking_started = False
        answer_started = False
        printer: Optional[StreamPrinter] = None
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8").strip()
                if line == "data: [DONE]":
                    break
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if reasoning and self.show_thinking:
                    if not thinking_started:
                        thinking_started = True
                        self._print_thinking_header()
                        if self.on_thinking is not None:
                            self.on_thinking("__start__")
                    self._print_thinking_chunk(reasoning)
                    if self.on_thinking is not None:
                        self.on_thinking(reasoning)
                content = delta.get("content")
                if not content:
                    continue
                if not answer_started:
                    print()
                    self._print_assistant_header()
                    printer = StreamPrinter()
                    answer_started = True
                    if self.on_thinking is not None:
                        self.on_thinking("__end__")
                full_content.append(content)
                if printer is not None:
                    printer.feed(content)
                if self.on_content is not None:
                    self.on_content(content)
        finally:
            if printer is not None:
                printer.finish()
            if self.on_thinking is not None and thinking_started and not answer_started:
                self.on_thinking("__end__")
        return "".join(full_content)
 
    def _non_stream_response(self, response: requests.Response) -> str:
        data = response.json()
        message = data["choices"][0]["message"]
        content = message.get("content", "") or ""
        reasoning = message.get("reasoning_content") or message.get("reasoning")
        if reasoning and self.show_thinking:
            print(f"\n{C.DIM}thinking...\n{reasoning}{C.END}\n")
        if reasoning and self.on_thinking is not None:
            self.on_thinking("__start__")
            self.on_thinking(reasoning)
            self.on_thinking("__end__")
        self._print_assistant_header()
        printer = StreamPrinter()
        printer.feed(content)
        printer.finish()
        if self.on_content is not None:
            self.on_content(content)
        return content
 
    def chat(self, user_content: Any) -> Optional[str]:
        self.messages.append({"role": "user", "content": user_content})
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with requests.post(
                    self.base_url,
                    headers=self._headers(),
                    json=self._payload(),
                    stream=self.stream,
                    timeout=self.timeout,
                ) as resp:
                    if resp.status_code != 200:
                        print(f"\n{C.RED}❌ HTTP {resp.status_code}:{C.END} {resp.text[:500]}")
                        self.messages.pop()
                        return None
                    if self.stream:
                        reply = self._stream_response(resp)
                    else:
                        reply = self._non_stream_response(resp)
                    if reply is not None:
                        self.messages.append({"role": "assistant", "content": reply})
                        return reply
            except requests.exceptions.Timeout:
                print(f"\n{C.YELLOW}⏳ Timeout (attempt {attempt}/{MAX_RETRIES}){C.END}")
                if attempt == MAX_RETRIES:
                    print(f"{C.YELLOW} Try lower --max-tokens or disable --thinking{C.END}")
                    self.messages.pop()
                    return None
                time.sleep(2)
            except requests.exceptions.RequestException as e:
                print(f"\n{C.RED}❌ Network error: {e}{C.END}")
                self.messages.pop()
                return None
        return None
 
    def clear(self):
        self.messages.clear()
 
 
PROMPT_STYLE = Style.from_dict(
    {
        "prompt": "ansicyan bold",
    }
)
 
 
def build_session() -> PromptSession:
    kb = KeyBindings()
 
    @kb.add("enter")
    def _enter(event):
        event.current_buffer.insert_text("\n")
 
    def _submit(event):
        if event.current_buffer.text.strip():
            event.current_buffer.validate_and_handle()
 
    @kb.add("escape", "enter")
    def _meta_enter(event):
        _submit(event)
 
    @kb.add("c-d")
    def _ctrl_d(event):
        if event.current_buffer.text.strip():
            _submit(event)
        else:
            event.app.exit(result=None)
 
    return PromptSession(multiline=True, key_bindings=kb, style=PROMPT_STYLE)
 
 
def main() -> None:
    parser = argparse.ArgumentParser(description="NVIDIA AI API CLI (multiline input)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--top-p", type=float, default=DEFAULT_TOP_P)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--thinking", action="store_true")
    parser.add_argument("--hide-thinking", action="store_true")
    parser.add_argument("--no-stream", action="store_true")
    parser.add_argument("--system", type=str)
    args = parser.parse_args()
 
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        print("NVIDIA_API_KEY not set")
        print("  PowerShell -> $env:NVIDIA_API_KEY = 'nvapi-...'")
        print("  bash       -> export NVIDIA_API_KEY='nvapi-...'")
        sys.exit(1)
 
    client = NvidiaChat(
        api_key=api_key,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        timeout=args.timeout,
        enable_thinking=args.thinking,
        stream=not args.no_stream,
        show_thinking=not args.hide_thinking,
    )
    catalog = ModelCatalog(api_key)
    if args.system:
        client.messages.append({"role": "system", "content": args.system})
 
    print_help = (
        "Commands:\n"
        "  /help              Show this help\n"
        "  /model             List chat models\n"
        "  /model <n|id>      Select a model\n"
        "  /quit              Exit\n"
        "\n"
        "Input:\n"
        "  Enter              New line (paste code freely)\n"
        "  Esc then Enter     Send  (Alt+Enter)\n"
        "  Ctrl+D             Send (empty line quits)\n"
        "  Ctrl+C             Quit\n"
    )
 
    if RICH_AVAILABLE:
        title = Text(" NVIDIA AI API CLI ", style="bold white on green")
        console.print(Panel.fit(title, border_style="bright_green"))
        console.print(f"[dim]Model: {args.model}[/dim]")
        console.print(print_help)
    else:
        print(f"{C.CYAN}{C.BOLD}╭─────────────────────╮")
        print("│ NVIDIA AI API CLI │")
        print(f"╰─────────────────────╯{C.END}")
        print(f"{C.DIM}Model: {args.model}\n")
        print(print_help)
 
    session = build_session()
    while True:
        try:
            if RICH_AVAILABLE:
                text = session.prompt([("class:prompt", "You: ")])
            else:
                text = session.prompt(f"{C.BLUE}{C.BOLD}You:{C.END} ")
        except KeyboardInterrupt:
            print("\nBye!")
            break
        except EOFError:
            print("\nBye!")
            break
 
        if text is None:
            print("\nBye!")
            break
 
        text = text.strip("\n").rstrip()
        if not text:
            continue
 
        parts = text.split(maxsplit=1)
        head = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
 
        if head in ("/quit", "/exit", "/bye", "/q"):
            print("Bye!")
            break
        if head == "/help":
            if RICH_AVAILABLE:
                console.print(print_help)
            else:
                print(print_help)
            continue
        if head in ("/model", "/models"):
            handle_model_command(arg, client, catalog)
            continue
        if catalog.pick_pending and text.isdigit():
            handle_model_command(text, client, catalog)
            continue
        catalog.pick_pending = False
        client.chat(text)
 
 
if __name__ == "__main__":
    main()
 