from __future__ import annotations

import argparse
import os
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None

from originalchat import (
    NvidiaChat,
    ModelCatalog,
    handle_model_command,
    DEFAULT_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TIMEOUT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
)

class C:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
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


PROMPT_STYLE = Style.from_dict({
    "prompt": "ansicyan bold",
})


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
