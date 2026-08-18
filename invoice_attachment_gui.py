import contextlib
import ctypes
import queue
import sys
import threading
import traceback
from pathlib import Path


def enable_high_dpi_awareness():
    """在创建任何窗口前启用 Windows Per-Monitor V2 DPI 感知。"""
    if sys.platform != "win32":
        return

    try:
        set_context = ctypes.windll.user32.SetProcessDpiAwarenessContext
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = ctypes.c_bool
        if set_context(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass

    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return
    except (AttributeError, OSError):
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


enable_high_dpi_awareness()

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import rename_invoices_orders as processor


class QueueWriter:
    def __init__(self, event_queue):
        self.event_queue = event_queue

    def write(self, text):
        if text:
            self.event_queue.put(("log", text))

    def flush(self):
        pass


class InvoiceAttachmentApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("报销附件整理工具")
        self.dpi = self._get_window_dpi()
        self.ui_scale = self.dpi / 96.0
        self.tk.call("tk", "scaling", self.dpi / 72.0)
        self.geometry(f"{round(820 * self.ui_scale)}x{round(610 * self.ui_scale)}")
        self.minsize(round(720 * self.ui_scale), round(520 * self.ui_scale))

        self.csv_path = tk.StringVar()
        self.attach_root = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.name_template = tk.StringVar(value=processor.DEFAULT_NAME_TEMPLATE)
        self.dry_run = tk.BooleanVar(value=True)
        self.status_text = tk.StringVar(value="请选择 CSV 和附件目录")
        self.event_queue = queue.Queue()
        self.running = False

        self._configure_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_events)

    def _get_window_dpi(self):
        if sys.platform != "win32":
            return 96
        try:
            get_dpi = ctypes.windll.user32.GetDpiForWindow
            get_dpi.argtypes = [ctypes.c_void_p]
            get_dpi.restype = ctypes.c_uint
            return max(96, int(get_dpi(self.winfo_id())))
        except (AttributeError, OSError, ValueError):
            return 96

    def _configure_style(self):
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Hint.TLabel", foreground="#5f6368")
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"))

    def _build_ui(self):
        container = ttk.Frame(self, padding=18)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        ttk.Label(container, text="报销附件整理工具", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            container,
            text="选择导出的数据表和附件目录，先预演，确认后再正式复制。",
            style="Hint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        form = ttk.LabelFrame(container, text="输入与输出", padding=12)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        self._add_path_row(form, 0, "CSV 数据表", self.csv_path, self._choose_csv)
        self._add_path_row(form, 1, "附件根目录", self.attach_root, self._choose_attach_root)
        self._add_path_row(form, 2, "结果保存目录", self.output_dir, self._choose_output_dir)

        ttk.Label(form, text="文件命名格式", width=13).grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=self.name_template).grid(
            row=3, column=1, sticky="ew", padx=(0, 8), pady=5
        )
        ttk.Button(form, text="说明…", command=self._show_template_help, width=9).grid(
            row=3, column=2, pady=5
        )
        ttk.Label(
            form,
            text="扩展名自动保留；建议包含 {编号} 和 {附件标记}，避免文件重名。",
            style="Hint.TLabel",
        ).grid(row=4, column=1, columnspan=2, sticky="w", pady=(0, 5))

        options = ttk.Frame(form)
        options.grid(row=5, column=1, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Checkbutton(
            options,
            text="仅预演（不复制文件、不生成汇总表）",
            variable=self.dry_run,
        ).pack(side="left")

        log_frame = ttk.LabelFrame(container, text="处理日志", padding=8)
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
            background="#fafafa",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        footer = ttk.Frame(container)
        footer.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        footer.columnconfigure(0, weight=1)

        status_area = ttk.Frame(footer)
        status_area.grid(row=0, column=0, sticky="ew")
        status_area.columnconfigure(0, weight=1)
        ttk.Label(status_area, textvariable=self.status_text).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(status_area, mode="indeterminate", length=180)
        self.progress.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.progress.grid_remove()

        buttons = ttk.Frame(footer)
        buttons.grid(row=1, column=0, sticky="e", pady=(10, 0))
        self.clear_button = ttk.Button(buttons, text="清空日志", command=self._clear_log)
        self.clear_button.pack(side="left", padx=(0, 8))
        self.start_button = ttk.Button(
            buttons,
            text="开始处理",
            command=self._start_processing,
            style="Primary.TButton",
        )
        self.start_button.pack(side="left")

    def _add_path_row(self, parent, row, label, variable, command):
        ttk.Label(parent, text=label, width=13).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky="ew", padx=(0, 8), pady=5
        )
        ttk.Button(parent, text="浏览…", command=command, width=9).grid(
            row=row, column=2, pady=5
        )

    def _choose_csv(self):
        selected = filedialog.askopenfilename(
            parent=self,
            title="选择报销数据 CSV",
            filetypes=(("CSV 文件", "*.csv"), ("所有文件", "*.*")),
        )
        if not selected:
            return

        csv_path = Path(selected)
        self.csv_path.set(str(csv_path))
        self.output_dir.set(str(csv_path.parent / "重命名结果"))

        guessed_attach_root = csv_path.parent / f"{csv_path.stem}_附件"
        if guessed_attach_root.is_dir():
            self.attach_root.set(str(guessed_attach_root))

    def _choose_attach_root(self):
        selected = filedialog.askdirectory(parent=self, title="选择附件根目录")
        if selected:
            self.attach_root.set(selected)

    def _choose_output_dir(self):
        selected = filedialog.askdirectory(parent=self, title="选择结果保存目录")
        if selected:
            self.output_dir.set(selected)

    def _show_template_help(self):
        messagebox.showinfo(
            "命名格式说明",
            "可用占位符：\n\n"
            "{编号}  {上传人}  {用途}  {金额}\n"
            "{附件标记}  {附件类型}  {序号}  {总数}\n\n"
            "示例：\n"
            "{上传人}_{用途}_{金额}_{编号}_{附件标记}\n\n"
            "文件扩展名会自动保留，不需要写入格式。",
            parent=self,
        )

    def _validate_inputs(self):
        csv_path = Path(self.csv_path.get().strip())
        attach_root = Path(self.attach_root.get().strip())

        if not self.csv_path.get().strip() or not csv_path.is_file():
            raise ValueError("请选择存在的 CSV 数据表。")
        if not self.attach_root.get().strip() or not attach_root.is_dir():
            raise ValueError("请选择存在的附件根目录。")
        if not (attach_root / "发票").is_dir():
            raise ValueError("附件根目录中缺少“发票”子目录。")
        if not (attach_root / "订单截图").is_dir():
            raise ValueError("附件根目录中缺少“订单截图”子目录。")

        output_text = self.output_dir.get().strip()
        output_dir = Path(output_text) if output_text else csv_path.parent / "重命名结果"
        self.output_dir.set(str(output_dir))
        try:
            name_template = processor.validate_name_template(self.name_template.get())
        except ValueError as error:
            raise ValueError(str(error)) from error
        self.name_template.set(name_template)
        return csv_path, attach_root, output_dir, name_template

    def _start_processing(self):
        if self.running:
            return

        try:
            csv_path, attach_root, output_dir, name_template = self._validate_inputs()
        except ValueError as error:
            messagebox.showerror("输入有误", str(error), parent=self)
            return

        if not self.dry_run.get():
            confirmed = messagebox.askyesno(
                "确认正式处理",
                "程序将复制并重命名附件，同时生成 summary.csv。是否继续？",
                parent=self,
            )
            if not confirmed:
                return

        self._clear_log()
        self.running = True
        self.start_button.configure(state="disabled")
        self.clear_button.configure(state="disabled")
        self.progress.grid()
        self.progress.start(12)
        self.status_text.set("正在预演…" if self.dry_run.get() else "正在处理…")

        worker = threading.Thread(
            target=self._run_worker,
            args=(csv_path, attach_root, output_dir, name_template, self.dry_run.get()),
            daemon=True,
        )
        worker.start()

    def _run_worker(self, csv_path, attach_root, output_dir, name_template, dry_run):
        arguments = [
            "--csv", str(csv_path),
            "--attach-root", str(attach_root),
            "--output-dir", str(output_dir),
            "--name-template", name_template,
        ]
        if dry_run:
            arguments.append("--dry-run")

        writer = QueueWriter(self.event_queue)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                processor.main(arguments)
            self.event_queue.put(("done", dry_run))
        except BaseException as error:
            self.event_queue.put(("log", traceback.format_exc()))
            self.event_queue.put(("error", str(error) or error.__class__.__name__))

    def _poll_events(self):
        try:
            while True:
                event, payload = self.event_queue.get_nowait()
                if event == "log":
                    self._append_log(payload)
                elif event == "done":
                    self._finish_success(payload)
                elif event == "error":
                    self._finish_error(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _append_log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _reset_running_state(self):
        self.running = False
        self.progress.stop()
        self.progress.grid_remove()
        self.start_button.configure(state="normal")
        self.clear_button.configure(state="normal")

    def _finish_success(self, dry_run):
        self._reset_running_state()
        if dry_run:
            self.status_text.set("预演完成，没有复制文件")
            messagebox.showinfo("预演完成", "请检查日志；本次没有复制文件。", parent=self)
        else:
            self.status_text.set("处理完成")
            messagebox.showinfo("处理完成", "附件和汇总表已经生成。", parent=self)

    def _finish_error(self, message):
        self._reset_running_state()
        self.status_text.set("处理失败，请查看日志")
        messagebox.showerror("处理失败", message, parent=self)

    def _on_close(self):
        if self.running:
            messagebox.showwarning("正在处理", "请等待当前处理完成后再关闭。", parent=self)
            return
        self.destroy()


def main():
    app = InvoiceAttachmentApp()
    app.mainloop()


if __name__ == "__main__":
    main()
