import os
import threading
import customtkinter as ctk
from tkinter import messagebox
import sys

# Import core functionality
from app_detector.core.detector import AppDetector
from app_detector.core.installer import AppInstaller
from app_detector.core.manifest import Manifest
from app_detector.models.scan_level import ScanLevel

# Dynamically load the correct platform detector/installer
from app_detector.utils.platform_detect import detect_platform
platform_info = detect_platform()
fam = platform_info.family

if fam == "windows":
    from app_detector.platforms.windows import WindowsDetector as Detector
    from app_detector.platforms.windows import WindowsInstaller as Installer
elif fam == "darwin":
    from app_detector.platforms.macos import MacOSDetector as Detector
    from app_detector.platforms.macos import MacOSInstaller as Installer
else:
    from app_detector.platforms.linux import LinuxDetector as Detector
    from app_detector.platforms.linux import LinuxInstaller as Installer


def native_asksaveasfilename(defaultextension: str, filetypes: list, title: str) -> str | None:
    if fam == "linux":
        try:
            from PyQt5.QtWidgets import QApplication, QFileDialog
            app = QApplication.instance() or QApplication([])
            filters = ";;".join([f"{name} ({ext})" for name, ext in filetypes])
            filename, _ = QFileDialog.getSaveFileName(None, title, "", filters)
            return filename if filename else None
        except ImportError:
            pass
            
    from tkinter.filedialog import asksaveasfilename
    return asksaveasfilename(defaultextension=defaultextension, filetypes=filetypes, title=title)


def native_askopenfilename(filetypes: list, title: str) -> str | None:
    if fam == "linux":
        try:
            from PyQt5.QtWidgets import QApplication, QFileDialog
            app = QApplication.instance() or QApplication([])
            filters = ";;".join([f"{name} ({ext})" for name, ext in filetypes])
            filename, _ = QFileDialog.getOpenFileName(None, title, "", filters)
            return filename if filename else None
        except ImportError:
            pass
            
    from tkinter.filedialog import askopenfilename
    return askopenfilename(filetypes=filetypes, title=title)


class AppDetectorGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Appearance configuration
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        
        self.title("App Detector")
        self.geometry("950x700")
        self.minsize(850, 600)
        
        # Configure grid layout (1 row, 2 columns)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ── Navigation Sidebar ──
        # Card-like slightly rounded sidebar instead of sharp flush
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=15)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew", padx=(15, 0), pady=15)
        self.sidebar_frame.grid_rowconfigure(4, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="App Detector 🔍", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20))

        self.home_button = ctk.CTkButton(self.sidebar_frame, text="Home", height=40, font=ctk.CTkFont(size=14, weight="bold"),
                                         fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"),
                                         command=lambda: self.show_frame("home"))
        self.home_button.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        self.scan_button = ctk.CTkButton(self.sidebar_frame, text="Scan OS", height=40, font=ctk.CTkFont(size=14, weight="bold"),
                                         fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"),
                                         command=lambda: self.show_frame("scan"))
        self.scan_button.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        self.restore_button = ctk.CTkButton(self.sidebar_frame, text="Restore", height=40, font=ctk.CTkFont(size=14, weight="bold"),
                                            fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"),
                                            command=lambda: self.show_frame("restore"))
        self.restore_button.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        self.appearance_mode_label = ctk.CTkLabel(self.sidebar_frame, text="Theme:", anchor="w", font=ctk.CTkFont(size=13))
        self.appearance_mode_label.grid(row=5, column=0, padx=20, pady=(10, 0))
        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(self.sidebar_frame, values=["System", "Dark", "Light"],
                                                               command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.grid(row=6, column=0, padx=20, pady=(10, 20))

        # ── Main Content Area ──
        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        # Initialize frames
        self.frames = {}
        
        # Build views
        self.frames["home"] = self.create_home_frame()
        self.frames["scan"] = self.create_scan_frame()
        self.frames["restore"] = self.create_restore_frame()

        # Active button styling logic
        self.nav_buttons = {"home": self.home_button, "scan": self.scan_button, "restore": self.restore_button}

        # Show initial frame
        self.show_frame("home")
        self.set_active_button("home")
        
        # Manifest data for restore
        self.loaded_manifest = None
        self.restore_checkboxes = []

    def set_active_button(self, name: str):
        for btn_name, btn in self.nav_buttons.items():
            if btn_name == name:
                btn.configure(fg_color=("gray75", "gray25"))
            else:
                btn.configure(fg_color="transparent")

    def change_appearance_mode_event(self, new_appearance_mode: str):
        ctk.set_appearance_mode(new_appearance_mode)

    def show_frame(self, name: str):
        for frame in self.frames.values():
            frame.grid_forget()
        self.frames[name].grid(row=0, column=0, sticky="nsew")
        self.set_active_button(name)

    # ── HOME FRAME ─────────────────────────────────────────────────────────

    def create_home_frame(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        
        card = ctk.CTkFrame(frame, corner_radius=15)
        card.place(relx=0.5, rely=0.5, anchor="center")
        
        title = ctk.CTkLabel(card, text="Welcome to App Detector", font=ctk.CTkFont(size=32, weight="bold"))
        title.pack(pady=(50, 20), padx=50)
        
        desc_text = ("Never manually reinstall your apps again.\n\n"
                     "Backup your current OS environment into a portable manifest,\n"
                     "and seamlessly restore it on a new computer.")
        desc = ctk.CTkLabel(card, text=desc_text, font=ctk.CTkFont(size=16), 
                            justify="center", text_color=("gray30", "gray70"))
        desc.pack(pady=(0, 40), padx=50)

        btn_scan = ctk.CTkButton(card, text="Generate Snapshot (Scan)", width=320, height=50, 
                                 font=ctk.CTkFont(size=16, weight="bold"), corner_radius=8,
                                 command=lambda: self.show_frame("scan"))
        btn_scan.pack(pady=10)

        btn_restore = ctk.CTkButton(card, text="Restore from Snapshot", width=320, height=50, 
                                    font=ctk.CTkFont(size=16, weight="bold"), fg_color="transparent", 
                                    border_width=2, text_color=("gray10", "gray90"), corner_radius=8,
                                    command=lambda: self.show_frame("restore"))
        btn_restore.pack(pady=(10, 50))
        
        return frame

    # ── SCAN FRAME ─────────────────────────────────────────────────────────

    def create_scan_frame(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        
        title = ctk.CTkLabel(frame, text="Generate System Snapshot", font=ctk.CTkFont(size=28, weight="bold"), anchor="w")
        title.pack(fill="x", pady=(10, 5))
        
        subtitle = ctk.CTkLabel(frame, text="Scan your computer to detect installed applications and build a manifest file.", 
                                font=ctk.CTkFont(size=14), text_color=("gray40", "gray60"), anchor="w")
        subtitle.pack(fill="x", pady=(0, 25))

        # Card container for settings
        card = ctk.CTkFrame(frame, corner_radius=10)
        card.pack(fill="x", pady=10)
        
        lbl = ctk.CTkLabel(card, text="Select Scanning Scope:", font=ctk.CTkFont(size=16, weight="bold"))
        lbl.pack(anchor="w", padx=20, pady=(20, 10))

        self.scan_level_var = ctk.IntVar(value=3)
        
        ctk.CTkRadioButton(card, text="Level 1: Essential (GUI desktop apps, browsers, games)", 
                           font=ctk.CTkFont(size=14), variable=self.scan_level_var, value=1).pack(anchor="w", padx=30, pady=8)
        ctk.CTkRadioButton(card, text="Level 2: Development (Level 1 + coding tools like compilers, git, docker)", 
                           font=ctk.CTkFont(size=14), variable=self.scan_level_var, value=2).pack(anchor="w", padx=30, pady=8)
        ctk.CTkRadioButton(card, text="Level 3: Comprehensive (All detected packages, command-line tools, libraries)", 
                           font=ctk.CTkFont(size=14), variable=self.scan_level_var, value=3).pack(anchor="w", padx=30, pady=(8, 20))

        # Action Area
        action_frame = ctk.CTkFrame(frame, fg_color="transparent")
        action_frame.pack(fill="x", pady=20)

        self.scan_button_action = ctk.CTkButton(action_frame, text="Start Scan", width=200, height=50, 
                                                font=ctk.CTkFont(size=16, weight="bold"), corner_radius=8,
                                                command=self.run_background_scan)
        self.scan_button_action.pack(pady=10)
        
        self.scan_progress = ctk.CTkProgressBar(action_frame, mode="indeterminate", width=500, height=12)
        self.scan_progress.set(0)
        
        self.scan_status = ctk.CTkLabel(action_frame, text="", font=ctk.CTkFont(size=14, weight="bold"))
        
        self.btn_save_manifest = ctk.CTkButton(action_frame, text="Save Manifest As...", width=200, height=50, 
                                               font=ctk.CTkFont(size=16, weight="bold"), fg_color="#2B8C52", hover_color="#1F693D",
                                               state="disabled", command=self.save_manifest_dialog)
        
        self.scanned_apps = []
        return frame

    def run_background_scan(self):
        self.scan_button_action.configure(state="disabled", text="Scanning...")
        self.scan_progress.pack(pady=(20, 10))
        self.scan_progress.start()
        self.scan_status.pack(pady=5)
        self.scan_status.configure(text="Scanning system... This may take a moment.", text_color=("gray10", "gray90"))
        self.btn_save_manifest.pack_forget()
        
        threading.Thread(target=self._scan_thread_worker, daemon=True).start()
        
    def _scan_thread_worker(self):
        val = self.scan_level_var.get()
        level = ScanLevel.COMPREHENSIVE
        if val == 1: level = ScanLevel.ESSENTIAL
        elif val == 2: level = ScanLevel.DEVELOPMENT

        detector = Detector()
        apps = detector.scan(level=level)
        
        self.after(0, self._scan_complete, apps)

    def _scan_complete(self, apps):
        self.scanned_apps = apps
        self.scan_progress.stop()
        self.scan_progress.pack_forget()
        if not apps:
            self.scan_status.configure(text="Scan failed or no apps found.", text_color=("#CC0000", "#FF4444"))
            self.scan_button_action.configure(state="normal", text="Start Scan")
            return
            
        self.scan_status.configure(text=f"Success! Detected {len(apps)} applications.", text_color=("#1F8A43", "#44FF77"))
        self.btn_save_manifest.pack(pady=20)
        self.btn_save_manifest.configure(state="normal")
        self.scan_button_action.configure(state="normal", text="Scan Again")

    def save_manifest_dialog(self):
        if not self.scanned_apps:
            return
        
        filepath = native_asksaveasfilename(
            defaultextension=".json",
            filetypes=[("All Files", "*.*"), ("App Detector Manifest", "*.json")],
            title="Save Manifest"
        )
        if filepath:
            manifest = Manifest.create(self.scanned_apps, platform_info)
            try:
                manifest.save(filepath)
                messagebox.showinfo("Success", f"Manifest saved to:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save manifest:\n{e}")

    # ── RESTORE FRAME ─────────────────────────────────────────────────────────

    def create_restore_frame(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        
        top_bar = ctk.CTkFrame(frame, fg_color="transparent")
        top_bar.pack(fill="x", pady=(10, 5))
        
        title_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        title_box.pack(side="left")
        ctk.CTkLabel(title_box, text="Restore Environment", font=ctk.CTkFont(size=28, weight="bold")).pack(anchor="w")
        self.restore_info_lbl = ctk.CTkLabel(title_box, text="Load a manifest snapshot to begin.", font=ctk.CTkFont(size=14), text_color=("gray40", "gray60"))
        self.restore_info_lbl.pack(anchor="w")
        
        btn_load = ctk.CTkButton(top_bar, text="Load Manifest...", height=40, font=ctk.CTkFont(size=14, weight="bold"), 
                                 command=self.load_manifest_dialog)
        btn_load.pack(side="right", anchor="e")

        # Scrollable list for apps, enclosed in a card
        self.card_scroll = ctk.CTkFrame(frame, corner_radius=10)
        self.card_scroll.pack(fill="both", expand=True, pady=15)
        
        self.apps_scroll = ctk.CTkScrollableFrame(self.card_scroll, fg_color="transparent")
        self.apps_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        bottom_bar = ctk.CTkFrame(frame, fg_color="transparent")
        bottom_bar.pack(fill="x", pady=(5, 10))
        
        self.btn_select_all = ctk.CTkButton(bottom_bar, text="Select All", width=120, height=40, font=ctk.CTkFont(size=14),
                                            fg_color="transparent", border_width=2, text_color=("gray10", "gray90"),
                                            state="disabled", command=self.select_all_apps)
        self.btn_select_all.pack(side="left")

        self.btn_deselect_all = ctk.CTkButton(bottom_bar, text="Deselect All", width=120, height=40, font=ctk.CTkFont(size=14),
                                              fg_color="transparent", border_width=2, text_color=("gray10", "gray90"),
                                              state="disabled", command=self.deselect_all_apps)
        self.btn_deselect_all.pack(side="left", padx=10)
        
        self.btn_trigger_restore = ctk.CTkButton(bottom_bar, text="Install Selected", height=45, width=180, font=ctk.CTkFont(size=16, weight="bold"), 
                                                 state="disabled", fg_color="#2B8C52", hover_color="#1F693D", command=self.run_restore)
        self.btn_trigger_restore.pack(side="right")
        
        return frame

    def load_manifest_dialog(self):
        filepath = native_askopenfilename(
            filetypes=[("All Files", "*.*"), ("JSON Files", "*.json")],
            title="Open Manifest"
        )
        if filepath:
            try:
                self.loaded_manifest = Manifest.load(filepath)
                self.populate_restore_list()
                os_family = self.loaded_manifest.source_os.get('family', 'unknown').capitalize()
                self.restore_info_lbl.configure(
                    text=f"Loaded: {os.path.basename(filepath)}  •  OS: {os_family}", 
                    text_color=("gray10", "gray90")
                )
                self.btn_select_all.configure(state="normal")
                self.btn_deselect_all.configure(state="normal")
                self.btn_trigger_restore.configure(state="normal")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load manifest:\n{e}")

    def populate_restore_list(self):
        # Clear existing
        for widget in self.apps_scroll.winfo_children():
            widget.destroy()
        self.restore_checkboxes.clear()

        # Build list
        for i, app in enumerate(self.loaded_manifest.apps):
            # Create alternating background for lists
            bg_color = ("gray85", "gray20") if i % 2 == 0 else "transparent"
            row_frame = ctk.CTkFrame(self.apps_scroll, fg_color=bg_color, corner_radius=5)
            row_frame.pack(fill="x", pady=2, ipady=4)
            
            chk_var = ctk.BooleanVar(value=True)
            chk = ctk.CTkCheckBox(row_frame, text=f"{app.name}", font=ctk.CTkFont(size=15, weight="bold"), variable=chk_var)
            chk.pack(side="left", padx=15)
            
            # Subtext for version and source
            sub_lbl = ctk.CTkLabel(row_frame, text=f"v{app.version} ", font=ctk.CTkFont(size=13), text_color=("gray40", "gray60"))
            sub_lbl.pack(side="left", padx=(5, 0))

            cat_lbl = ctk.CTkLabel(row_frame, text=f"[{app.source}]", font=ctk.CTkFont(size=12), text_color=("gray50", "gray50"))
            cat_lbl.pack(side="right", padx=15)
            
            self.restore_checkboxes.append((app, chk_var))

    def select_all_apps(self):
        for app, var in self.restore_checkboxes:
            var.set(True)

    def deselect_all_apps(self):
        for app, var in self.restore_checkboxes:
            var.set(False)

    def run_restore(self):
        selected_apps = [app for app, var in self.restore_checkboxes if var.get()]
        if not selected_apps:
            messagebox.showwarning("Warning", "No applications selected to restore.")
            return
            
        confirm = messagebox.askyesno("Confirm Restore", 
                                      f"Are you sure you want to install {len(selected_apps)} applications?\n\n"
                                      "Note: You may be prompted for Administrator / root password in the terminal.")
        if not confirm:
            return
            
        self.btn_trigger_restore.configure(state="disabled", text="Installing...")
        
        # In a real app we would want an indeterminate progress or log output here
        threading.Thread(target=self._restore_thread_worker, args=(selected_apps,), daemon=True).start()

    def _restore_thread_worker(self, selected_apps):
        installer = Installer()
        success_count = 0
        for app in selected_apps:
            # We enforce latest for simplicity in GUI for now, or user can edit
            app.target_version = "latest"
            if installer.install(app, silent=True):
                success_count += 1
                
        self.after(0, self._restore_complete, success_count, len(selected_apps))

    def _restore_complete(self, success_count, total):
        self.btn_trigger_restore.configure(state="normal", text="Start Restore")
        messagebox.showinfo("Restore Complete", f"Successfully installed {success_count} out of {total} applications.")
