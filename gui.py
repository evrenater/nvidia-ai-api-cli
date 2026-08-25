from __future__ import annotations

import os
import sys
import threading
from typing import Any, Dict, List, Optional

import requests

from originalchat import (
    NvidiaChat,
    ModelCatalog,
    fetch_models,
    is_chat_model,
    DEFAULT_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TIMEOUT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
)

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

BG = "#ffffff"
FG = "#1a1a1a"
SIDEBAR_BG = "#f5f5f5"
ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
USER_BG = "#e8f0fe"
ASSISTANT_BG = "#f1f3f4"
BORDER = "#e0e0e0"
MUTED = "#666666"


def _read_env_key() -> str:
    return os.getenv("NVIDIA_API_KEY", "")


class ChatApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("NVIDIA AI Chat")
        self.root.geometry("1100x720")
        self.root.configure(bg=BG)

        self.client: Optional[NvidiaChat] = None
        self.catalog: Optional[ModelCatalog] = None
        self.all_models: List[str] = []
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.api_key_var = tk.StringVar(value=_read_env_key())
        self.busy = False

        self._pending: List[tuple] = []
        self._stream_flush_scheduled = False

        self._build_ui()
        self._apply_settings()
        self._sync_api_key()
        self._refresh_models_async()


    def _build_ui(self) -> None:
        root = self.root
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(root, bg=SIDEBAR_BG, width=300)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)

        self._build_sidebar(sidebar)

        right = tk.Frame(root, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)

        self._build_chat(right)

    def _build_sidebar(self, sidebar: tk.Frame) -> None:
        title = tk.Label(
            sidebar, text="Settings", bg=SIDEBAR_BG, fg=FG,
            font=("Segoe UI", 14, "bold"), anchor="w",
        )
        title.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))

        fields: List[Dict[str, Any]] = [
            {"label": "Model", "var": self.model_var, "kind": "combo"},
            {"label": "Max tokens", "key": "max_tokens", "kind": "entry",
             "default": str(DEFAULT_MAX_TOKENS)},
            {"label": "Temperature", "key": "temperature", "kind": "entry",
             "default": str(DEFAULT_TEMPERATURE)},
            {"label": "Top-p", "key": "top_p", "kind": "entry",
             "default": str(DEFAULT_TOP_P)},
            {"label": "Timeout (s)", "key": "timeout", "kind": "entry",
             "default": str(DEFAULT_TIMEOUT)},
        ]

        self.entry_vars: Dict[str, tk.StringVar] = {}
        self.combo_model: Optional[ttk.Combobox] = None
        self.check_vars: Dict[str, tk.BooleanVar] = {}
        self.system_var = tk.StringVar(value="")

        row = 1
        for f in fields:
            lbl = tk.Label(sidebar, text=f["label"], bg=SIDEBAR_BG, fg=MUTED,
                           font=("Segoe UI", 9), anchor="w")
            lbl.grid(row=row, column=0, sticky="ew", padx=16, pady=(8, 0))
            row += 1

            if f["kind"] == "combo":
                combo = ttk.Combobox(sidebar, textvariable=self.model_var)
                combo.grid(row=row, column=0, sticky="ew", padx=16, pady=(2, 0))
                self.combo_model = combo
                combo.bind("<<ComboboxSelected>>", self._on_model_selected)
                combo.bind("<KeyRelease>", self._on_model_edited)
            else:
                var = tk.StringVar(value=f["default"])
                self.entry_vars[f["key"]] = var
                entry = ttk.Entry(sidebar, textvariable=var)
                entry.grid(row=row, column=0, sticky="ew", padx=16, pady=(2, 0))
            row += 1

        bool_fields = [
            ("thinking", "Request thinking (when allowed)"),
            ("hide_thinking", "Hide reasoning stream"),
            ("no_stream", "Non-streaming replies"),
        ]
        self.check_vars = {
            "thinking": tk.BooleanVar(value=False),
            "hide_thinking": tk.BooleanVar(value=False),
            "no_stream": tk.BooleanVar(value=False),
        }
        for key, text in bool_fields:
            cb = ttk.Checkbutton(sidebar, text=text, variable=self.check_vars[key])
            cb.grid(row=row, column=0, sticky="w", padx=16, pady=(10, 0))
            row += 1

        lbl = tk.Label(sidebar, text="System prompt", bg=SIDEBAR_BG, fg=MUTED,
                       font=("Segoe UI", 9), anchor="w")
        lbl.grid(row=row, column=0, sticky="ew", padx=16, pady=(14, 0))
        row += 1
        sys_entry = ttk.Entry(sidebar, textvariable=self.system_var)
        sys_entry.grid(row=row, column=0, sticky="ew", padx=16, pady=(2, 0))
        row += 1

        apply_btn = tk.Button(
            sidebar, text="Apply settings", command=self._apply_settings,
            bg=ACCENT, fg="white", activebackground=ACCENT_HOVER,
            activeforeground="white", relief="flat", cursor="hand2",
            font=("Segoe UI", 10, "bold"), pady=6,
        )
        apply_btn.grid(row=row, column=0, sticky="ew", padx=16, pady=(16, 0))
        row += 1

        new_btn = tk.Button(
            sidebar, text="New chat", command=self._new_chat,
            bg="white", fg=FG, activebackground="#e9e9e9",
            relief="flat", cursor="hand2", font=("Segoe UI", 10), pady=4,
            highlightbackground=BORDER, highlightthickness=1,
        )
        new_btn.grid(row=row, column=0, sticky="ew", padx=16, pady=(8, 0))
        row += 1

        sidebar.grid_rowconfigure(row, weight=1)

        key_lbl = tk.Label(sidebar, text="NVIDIA API Key", bg=SIDEBAR_BG,
                           fg=MUTED, font=("Segoe UI", 9), anchor="w")
        key_lbl.grid(row=row + 1, column=0, sticky="ew", padx=16, pady=(8, 0))

        key_entry = ttk.Entry(sidebar, textvariable=self.api_key_var, show="•")
        key_entry.grid(row=row + 2, column=0, sticky="ew", padx=16, pady=(2, 0))

        self.key_status = tk.Label(sidebar, text="", bg=SIDEBAR_BG, fg=MUTED,
                                   font=("Segoe UI", 8), anchor="w")
        self.key_status.grid(row=row + 3, column=0, sticky="ew", padx=16, pady=(2, 0))

        save_key = tk.Button(
            sidebar, text="Save key", command=self._save_key,
            bg="white", fg=FG, activebackground="#e9e9e9",
            relief="flat", cursor="hand2", font=("Segoe UI", 9), pady=3,
            highlightbackground=BORDER, highlightthickness=1,
        )
        save_key.grid(row=row + 4, column=0, sticky="ew", padx=16, pady=(4, 16))

    def _build_chat(self, right: tk.Frame) -> None:
        self.chat_display = scrolledtext.ScrolledText(
            right, bg=BG, fg=FG, wrap="word", state="disabled",
            font=("Consolas", 11), padx=14, pady=12,
            relief="flat", borderwidth=0, cursor="arrow",
        )
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=(0, 0))

        self.chat_display.tag_configure("user", background=USER_BG,
                                        foreground=FG, spacing1=4, spacing3=4,
                                        lmargin1=10, lmargin2=10, rmargin=10)
        self.chat_display.tag_configure("assistant", background=ASSISTANT_BG,
                                        foreground=FG, spacing1=4, spacing3=4,
                                        lmargin1=10, lmargin2=10, rmargin=10)
        self.chat_display.tag_configure("label", foreground=MUTED,
                                        font=("Segoe UI", 8, "bold"))
        self.chat_display.tag_configure("error", foreground="#b91c1c")
        self.chat_display.tag_configure("info", foreground=MUTED,
                                        font=("Segoe UI", 9, "italic"))
        self.chat_display.tag_configure("thinking", foreground="#8b5cf6",
                                        font=("Segoe UI", 10, "italic"),
                                        background="#faf5ff",
                                        spacing1=4, spacing3=4,
                                        lmargin1=10, lmargin2=10, rmargin=10)
        self.chat_display.tag_configure("thinking_label", foreground="#7c3aed",
                                        font=("Segoe UI", 8, "bold"))

        input_frame = tk.Frame(right, bg=BG)
        input_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
        input_frame.grid_columnconfigure(0, weight=1)

        self.input_text = tk.Text(
            input_frame, height=6, wrap="word", bg="#fafafa", fg=FG,
            font=("Consolas", 11), relief="solid", borderwidth=1,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT, padx=8, pady=6,
        )
        self.input_text.grid(row=0, column=0, sticky="ew")

        btn_col = tk.Frame(input_frame, bg=BG)
        btn_col.grid(row=0, column=1, sticky="ns", padx=(8, 0))

        self.send_btn = tk.Button(
            btn_col, text="Send", command=self._send,
            bg=ACCENT, fg="white", activebackground=ACCENT_HOVER,
            activeforeground="white", relief="flat", cursor="hand2",
            font=("Segoe UI", 10, "bold"), padx=18, pady=6,
        )
        self.send_btn.pack(fill="x", pady=(0, 4))

        hint = tk.Label(btn_col, text="Ctrl+Enter\nto send", bg=BG, fg=MUTED,
                        font=("Segoe UI", 8), justify="center")
        hint.pack()

        self.input_text.bind("<Control-Return>", self._send_event)
        self.input_text.bind("<Shift-Return>", self._send_event)
        self.input_text.bind("<Return>", self._enter_key)


    def _enter_key(self, event: Any) -> str:
        self.input_text.insert("insert", "\n")
        return "break"

    def _send_event(self, event: Any) -> str:
        self._send()
        return "break"

    def _sync_api_key(self) -> None:
        env_key = _read_env_key()
        key = self.api_key_var.get().strip()
        if key:
            self.key_status.config(
                text=("✓ key set" if key == env_key else "✓ key set (unsaved)"),
                fg="#16a34a",
            )
        else:
            self.key_status.config(text="no key set — enter one above",
                                   fg="#b91c1c")

    def _save_key(self) -> None:
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("API Key", "Key is empty.")
            return
        try:
            if os.name == "nt":
                os.system(f'setx NVIDIA_API_KEY "{key}" > nul 2>&1')
        except Exception:
            pass
        os.environ["NVIDIA_API_KEY"] = key
        self._sync_api_key()
        self._apply_settings()
        self._refresh_models_async()
        messagebox.showinfo("API Key", "Key saved for this session.\n"
                                       "On Windows it was also set via setx "
                                       "(applies to new terminals).")

    def _on_model_selected(self, event: Any = None) -> None:
        self.model_var.set(self.model_var.get().strip())

    def _on_model_edited(self, event: Any = None) -> None:
        pass

    def _apply_settings(self) -> None:
        key = self.api_key_var.get().strip()
        if not key:
            key = _read_env_key()
        if not key:
            self.client = None
            self._append_info("Enter an NVIDIA API key in the left panel.")
            return

        try:
            max_tokens = int(self.entry_vars["max_tokens"].get())
        except ValueError:
            max_tokens = DEFAULT_MAX_TOKENS
        try:
            temperature = float(self.entry_vars["temperature"].get())
        except ValueError:
            temperature = DEFAULT_TEMPERATURE
        try:
            top_p = float(self.entry_vars["top_p"].get())
        except ValueError:
            top_p = DEFAULT_TOP_P
        try:
            timeout = int(self.entry_vars["timeout"].get())
        except ValueError:
            timeout = DEFAULT_TIMEOUT

        self.client = NvidiaChat(
            api_key=key,
            model=self.model_var.get().strip() or DEFAULT_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            timeout=timeout,
            enable_thinking=self.check_vars["thinking"].get(),
            stream=not self.check_vars["no_stream"].get(),
            show_thinking=not self.check_vars["hide_thinking"].get(),
            on_thinking=self._on_thinking,
            on_content=self._on_content,
        )
        self.catalog = ModelCatalog(key)

        sys_prompt = self.system_var.get().strip()
        if sys_prompt and not self.client.messages:
            self.client.messages.append({"role": "system", "content": sys_prompt})

    def _refresh_models_async(self) -> None:
        key = self.api_key_var.get().strip() or _read_env_key()
        if not key:
            return

        def worker():
            try:
                ids = fetch_models(key)
                chat_ids = [m for m in ids if is_chat_model(m)]
                self.root.after(0, lambda: self._set_models(chat_ids or ids))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _set_models(self, ids: List[str]) -> None:
        self.all_models = ids
        if self.combo_model is not None:
            self.combo_model["values"] = ids

    def _new_chat(self) -> None:
        if self.client is not None:
            self.client.clear()
            sys_prompt = self.system_var.get().strip()
            if sys_prompt:
                self.client.messages.append(
                    {"role": "system", "content": sys_prompt})
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")
        self._append_info("New chat started.")

    def _append_user(self, text: str) -> None:
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", "\n", "label")
        self.chat_display.insert("end", "You\n", "label")
        self.chat_display.insert("end", text + "\n", "user")
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")

    def _append_assistant(self, text: str) -> None:
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", "Assistant\n", "label")
        self.chat_display.insert("end", text + "\n", "assistant")
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")

    def _on_thinking(self, chunk: str) -> None:
        self._queue_stream(("thinking", chunk))

    def _on_content(self, chunk: str) -> None:
        self._queue_stream(("content", chunk))

    def _queue_stream(self, item: tuple) -> None:
        self._pending.append(item)
        if not self._stream_flush_scheduled:
            self._stream_flush_scheduled = True
            self.root.after(10, self._flush_stream)

    def _flush_stream(self) -> None:
        self._stream_flush_scheduled = False
        if not self._pending:
            return
        items = self._pending
        self._pending = []

        self.chat_display.configure(state="normal")
        for kind, text in items:
            if kind == "thinking":
                if text == "__start__":
                    self.chat_display.insert("end", "\nThinking...\n",
                                             "thinking_label")
                    self._thinking_mark = "end-1c"
                elif text == "__end__":
                    pass
                else:
                    self.chat_display.insert("end", text, "thinking")
            elif kind == "content":
                if getattr(self, "_assistant_mark", None) is None:
                    self.chat_display.insert("end", "\nAssistant\n", "label")
                    self._assistant_mark = "assistant-start"
                self.chat_display.insert("end", text, "assistant")
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")

    def _reset_stream_marks(self) -> None:
        self._assistant_mark = None
        self._thinking_mark = None

    def _append_error(self, text: str) -> None:
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", text + "\n", "error")
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")

    def _append_info(self, text: str) -> None:
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", text + "\n", "info")
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")


    def _send(self) -> None:
        if self.busy:
            return
        text = self.input_text.get("1.0", "end").rstrip("\n")
        if not text.strip():
            return
        if self.client is None:
            self._apply_settings()
            if self.client is None:
                self._append_error("Missing API key. Set it in the left panel.")
                return

        self.input_text.delete("1.0", "end")
        self._append_user(text)
        self._reset_stream_marks()

        self.busy = True
        self.send_btn.config(state="disabled", text="…")

        def worker():
            try:
                reply = self.client.chat(text)
            except Exception as e:
                reply = None
                err = str(e)
            else:
                err = None
            self.root.after(0, lambda: self._finish(reply, err))

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, reply: Optional[str], err: Optional[str]) -> None:
        self._flush_stream()
        self.busy = False
        self.send_btn.config(state="normal", text="Send")
        if err:
            self._append_error(f"Error: {err}")
        elif reply is not None and getattr(self, "_assistant_mark", None) is None:
            self._append_assistant(reply)


def main():
    root = tk.Tk()
    app = ChatApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
