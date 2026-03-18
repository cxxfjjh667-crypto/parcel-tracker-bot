import os
import sys
import threading
import asyncio
import logging
from dotenv import set_key, load_dotenv
import customtkinter as ctk

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ensure DATA_DIR is set properly
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

os.environ["DATA_DIR"] = application_path
ENV_PATH = os.path.join(application_path, ".env")

# Ensure .env exists
if not os.path.exists(ENV_PATH):
    open(ENV_PATH, 'a', encoding="utf-8").close()

load_dotenv(ENV_PATH)

# Setup basic logging to string buffer for GUI display
import queue
log_queue = queue.Queue()

class QueueHandler(logging.Handler):
    def emit(self, record):
        log_queue.put(self.format(record))

log_handler = QueueHandler()
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s", "%H:%M:%S"))
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class ParcelTrackerGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Parcel Tracker Bot - Manager")
        self.geometry("600x650")
        self.resizable(False, False)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        # Title
        self.label_title = ctk.CTkLabel(self, text="📦 Parcel Tracker Bot", font=ctk.CTkFont(size=24, weight="bold"))
        self.label_title.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Status Badge
        self.label_status = ctk.CTkLabel(self, text="🔴 Offline", text_color="red", font=ctk.CTkFont(size=14, weight="bold"))
        self.label_status.grid(row=1, column=0, padx=20, pady=(0, 20))

        # Frame for Inputs
        self.frame_inputs = ctk.CTkFrame(self)
        self.frame_inputs.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.frame_inputs.grid_columnconfigure(1, weight=1)

        # 1. Telegram Token
        ctk.CTkLabel(self.frame_inputs, text="Telegram Bot Token:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.entry_tg = ctk.CTkEntry(self.frame_inputs, placeholder_text="Enter Telegram Bot Token (from @BotFather)")
        self.entry_tg.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        # 2. eTrackings API Key
        ctk.CTkLabel(self.frame_inputs, text="eTrackings API Key:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.entry_et_key = ctk.CTkEntry(self.frame_inputs, placeholder_text="Enter eTrackings API Key")
        self.entry_et_key.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        # 3. eTrackings Key Secret
        ctk.CTkLabel(self.frame_inputs, text="eTrackings Secret:").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.entry_et_sec = ctk.CTkEntry(self.frame_inputs, placeholder_text="Enter eTrackings Key Secret")
        self.entry_et_sec.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        # Load existing values
        self.entry_tg.insert(0, os.environ.get("TELEGRAM_BOT_TOKEN", ""))
        self.entry_et_key.insert(0, os.environ.get("ETRACKINGS_API_KEY", ""))
        self.entry_et_sec.insert(0, os.environ.get("ETRACKINGS_KEY_SECRET", ""))

        # Saved Keys Dropdown
        ctk.CTkLabel(self.frame_inputs, text="Saved API Keys:").grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.key_dropdown = ctk.CTkOptionMenu(self.frame_inputs, values=["No saved keys"], command=self.load_selected_key)
        self.key_dropdown.grid(row=3, column=1, padx=10, pady=10, sticky="ew")

        # Load saved keys
        self.saved_keys = []
        self._load_saved_keys_from_env()

        # Save Button
        self.btn_save = ctk.CTkButton(self, text="💾 Save Settings", command=self.save_settings)
        self.btn_save.grid(row=3, column=0, padx=20, pady=10)

        # Start Bot Button
        self.btn_start = ctk.CTkButton(self, text="🚀 Start Bot", fg_color="green", hover_color="darkgreen", command=self.start_bot)
        self.btn_start.grid(row=4, column=0, padx=20, pady=(0, 20))

        # Log Console
        self.log_box = ctk.CTkTextbox(self, width=560, height=200, state="disabled")
        self.log_box.grid(row=5, column=0, padx=20, pady=10, sticky="nsew")

        self.bot_thread = None
        self.running = False
        
        # Start log updater
        self.update_logs()

    def _load_saved_keys_from_env(self):
        saved_str = os.environ.get("SAVED_ETRACKINGS_KEYS", "")
        if saved_str:
            self.saved_keys = [tuple(k.split(':', 1)) for k in saved_str.split('|') if ':' in k]
        
        if self.saved_keys:
            values = [f"Key {i+1} ({k[0][:8]}...)" for i, k in enumerate(self.saved_keys)]
            self.key_dropdown.configure(values=values)
            
            # Find which one is currently active
            current_key = os.environ.get("ETRACKINGS_API_KEY", "")
            for i, k in enumerate(self.saved_keys):
                if k[0] == current_key:
                    self.key_dropdown.set(values[i])
                    break
            else:
                self.key_dropdown.set(values[0])
        else:
            self.key_dropdown.configure(values=["No saved keys"])
            self.key_dropdown.set("No saved keys")

    def load_selected_key(self, choice):
        if choice == "No saved keys" or not self.saved_keys:
            return
            
        try:
            # Extract index from 'Key X (...)'
            idx = int(choice.split(' ')[1]) - 1
            key, sec = self.saved_keys[idx]
            self.entry_et_key.delete(0, 'end')
            self.entry_et_key.insert(0, key)
            self.entry_et_sec.delete(0, 'end')
            self.entry_et_sec.insert(0, sec)
        except Exception:
            pass

    def update_logs(self):
        """Consume logs from queue and show in textbox"""
        while not log_queue.empty():
            msg = log_queue.get()
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(100, self.update_logs)

    def save_settings(self):
        tg = self.entry_tg.get().strip()
        et_key = self.entry_et_key.get().strip()
        et_sec = self.entry_et_sec.get().strip()
        
        set_key(ENV_PATH, "TELEGRAM_BOT_TOKEN", tg)
        set_key(ENV_PATH, "ETRACKINGS_API_KEY", et_key)
        set_key(ENV_PATH, "ETRACKINGS_KEY_SECRET", et_sec)
        
        os.environ["TELEGRAM_BOT_TOKEN"] = tg
        os.environ["ETRACKINGS_API_KEY"] = et_key
        os.environ["ETRACKINGS_KEY_SECRET"] = et_sec
        
        # Add to saved keys history if it's new
        if et_key and et_sec:
            new_pair = (et_key, et_sec)
            if new_pair not in self.saved_keys:
                self.saved_keys.append(new_pair)
                
            saved_str = "|".join([f"{k}:{s}" for k, s in self.saved_keys])
            set_key(ENV_PATH, "SAVED_ETRACKINGS_KEYS", saved_str)
            os.environ["SAVED_ETRACKINGS_KEYS"] = saved_str
            self._load_saved_keys_from_env()
        
        # If bot is running, update credentials dynamically!
        if self.running:
            from api.etrackings_client import ETrackingsClient
            from bot.handlers import etrackings, scanner
            etrackings.update_credentials(et_key, et_sec)
            scanner.client.update_credentials(et_key, et_sec)
            logging.getLogger("GUI").info("API Credentials updated on the fly!")
            
        logging.getLogger("GUI").info("Settings saved to .env")

    def _run_bot_thread(self, token):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            from telegram.ext import Application
            from bot.handlers import setup_handlers
            app = Application.builder().token(token).build()
            setup_handlers(app)
            logging.getLogger("GUI").info("Bot started successfully. Listening for messages...")
            app.run_polling(drop_pending_updates=True, stop_signals=None)
        except Exception as e:
            logging.getLogger("GUI").error(f"Bot execution error: {e}")
            self.running = False
            self.label_status.configure(text="🔴 Error", text_color="red")
            self.btn_start.configure(state="normal", text="🚀 Start Bot")

    def start_bot(self):
        tg_token = self.entry_tg.get().strip()
        if not tg_token:
            logging.getLogger("GUI").error("Missing Telegram Bot Token!")
            return

        self.save_settings()
        
        self.running = True
        self.btn_start.configure(state="disabled", text="Bot is Running...")
        self.label_status.configure(text="🟢 Online", text_color="green")
        
        self.bot_thread = threading.Thread(target=self._run_bot_thread, args=(tg_token,), daemon=True)
        self.bot_thread.start()

if __name__ == "__main__":
    app = ParcelTrackerGUI()
    app.mainloop()
