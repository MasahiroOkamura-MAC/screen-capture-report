import time
import schedule
import rumps
import threading
import os
from datetime import datetime
from src.capturer import ScreenCapturer
from src.analyzer import GeminiAnalyzer
from src.diagram import NanobananaClient
from src.notifier import EmailNotifier
from src.utils import setup_logger, get_config

logger = setup_logger(__name__)

from src.image_manager import ImageManager

class ScreenCaptureApp(rumps.App):
    def __init__(self):
        super(ScreenCaptureApp, self).__init__("SCApp")
        self.capturer = ScreenCapturer()
        self.analyzer = GeminiAnalyzer()
        self.diagram_client = NanobananaClient()
        self.notifier = EmailNotifier()
        self.image_manager = ImageManager()
        
        # Cleanup old captures on startup
        self.image_manager.cleanup_old_captures(days=1)
        
        self.current_batch = []
        self.daily_log = []
        self.is_running = False
        
        self.menu = ["Start Capture", "Stop Capture", None, "Capture Now", "Analyze Now", "Generate Report Now", None, "Open Data Folder", None, "Reset Settings"]
        
        # Start the scheduler in a separate thread
        self.scheduler_thread = threading.Thread(target=self.run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        
        # Check for missed reports on startup
        self.flush_reports()
        
        # Auto-start capture
        self.start_capture(None)

    def run_scheduler(self):
        while True:
            if self.is_running:
                schedule.run_pending()
            time.sleep(1)

    @rumps.clicked("Start Capture")
    def start_capture(self, _):
        if not self.is_running:
            self.is_running = True
            schedule.every(1).minutes.do(self.capture_task)
            # Schedule end of day report (e.g., at 18:00)
            schedule.every().day.at("18:00").do(self.flush_reports)
            logger.info("Capture started.")
            rumps.notification("Screen Capture", "Started", "Screen capture has started.")

    @rumps.clicked("Stop Capture")
    def stop_capture(self, _):
        if self.is_running:
            self.is_running = False
            schedule.clear()
            logger.info("Capture stopped.")
            rumps.notification("Screen Capture", "Stopped", "Screen capture has stopped.")

    @rumps.clicked("Capture Now")
    def manual_capture(self, _):
        logger.info("Manual capture triggered.")
        self.capture_task()
        rumps.notification("Screen Capture", "Captured", "Screen captured manually.")

    @rumps.clicked("Analyze Now")
    def manual_analyze(self, _):
        logger.info("Manual analysis triggered.")
        if not self.current_batch:
            logger.info("Batch empty, capturing one image for analysis...")
            self.capture_task()
            
        self.process_batch(force=True)
        rumps.notification("Screen Capture", "Analyzed", "Batch analysis completed.")

    @rumps.clicked("Generate Report Now")
    def manual_report(self, _):
        # Manually trigger flush, which will send today's report if it exists (even if < 18:00? No, flush logic checks time)
        # User expects "Generate Now" to force send.
        # So we should probably force send TODAY's content regardless of time.
        
        # Let's just call flush_reports, but we need a way to force today.
        # Or just implement manual logic here.
        
        # For manual trigger, let's just send everything currently in the log as "Today's Report" (or whatever dates are there)
        # ignoring the time check.
        
        self.force_flush_reports()

    @rumps.clicked("Open Data Folder")
    def open_data_folder(self, _):
        import subprocess
        subprocess.call(["open", "data"])

    @rumps.clicked("Reset Settings")
    def reset_settings(self, _):
        response = rumps.alert(
            title="Reset Settings",
            message="Are you sure you want to delete .env and reset all settings? The application will quit.",
            ok="Reset & Quit",
            cancel="Cancel"
        )
        if response == 1: # OK clicked
            if os.path.exists(".env"):
                try:
                    os.remove(".env")
                    logger.info(".env file deleted.")
                except Exception as e:
                    logger.error(f"Failed to delete .env: {e}")
                    rumps.alert(f"Failed to delete .env: {e}")
                    return
            rumps.quit_application()

    def capture_task(self):
        filepath = self.capturer.capture()
        self.current_batch.append(filepath)
        
        if len(self.current_batch) >= 5:
            self.process_batch()

    def process_batch(self, force=False):
        if not self.current_batch:
            return

        logger.info(f"Processing batch of {len(self.current_batch)} images...")
        
        # Read current log
        full_log_content = ""
        log_path = "data/daily_log.txt"
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                full_log_content = f.read()

        # Determine current hour block with DATE
        now = datetime.now()
        current_date_str = now.strftime("%Y-%m-%d")
        current_hour_str = now.strftime("%H:00 - %H:59")
        header = f"## [{current_date_str} {current_hour_str}]"
        
        past_log = full_log_content
        current_hour_log = ""
        
        # Check if we are already in the current hour block
        if header in full_log_content:
            # Split at the last occurrence of the header
            parts = full_log_content.rsplit(header, 1)
            past_log = parts[0].strip()
            current_hour_log = parts[1].strip()
        else:
            # New hour block
            past_log = full_log_content.strip()
            current_hour_log = ""

        # Analyze and get updated hourly report
        updated_hour_log = self.analyzer.analyze_batch(self.current_batch, current_hour_log)
        
        # Reconstruct the full log
        new_full_log = past_log
        if new_full_log:
            new_full_log += "\n\n"
            
        new_full_log += f"{header}\n{updated_hour_log}"
        
        # Overwrite log file
        with open(log_path, "w") as f:
            f.write(new_full_log)
        
        # Update internal state
        self.daily_log = [new_full_log]
        
        # Clear batch
        self.current_batch = []

    def flush_reports(self):
        """Checks daily_log.txt for any reports that need to be sent (past days or today > 18:00)."""
        logger.info("Checking for pending reports...")
        
        log_path = "data/daily_log.txt"
        if not os.path.exists(log_path):
            return

        with open(log_path, "r") as f:
            content = f.read()
            
        if not content.strip():
            return

        # Simple parsing strategy: Split by "## ["
        # This assumes the format "## [YYYY-MM-DD HH:MM - HH:MM]"
        # We will group by YYYY-MM-DD
        
        lines = content.split('\n')
        daily_contents = {} # { "YYYY-MM-DD": [list of lines] }
        current_date = None
        
        # Regex to find date in header
        import re
        header_pattern = re.compile(r"## \[(\d{4}-\d{2}-\d{2}) .*\]")
        
        # Buffer for lines that don't belong to a specific date header (e.g. old logs)
        # We'll assign them to "Today" or handle them separately. 
        # For now, let's assume if we can't find a date, it belongs to today.
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        for line in lines:
            match = header_pattern.search(line)
            if match:
                current_date = match.group(1)
            
            target_date = current_date if current_date else today_str
            
            if target_date not in daily_contents:
                daily_contents[target_date] = []
            daily_contents[target_date].append(line)

        # Now determine which dates to send
        now = datetime.now()
        remaining_content = []
        
        for date_str, lines in daily_contents.items():
            report_content = "\n".join(lines).strip()
            if not report_content:
                continue

            should_send = False
            
            if date_str < today_str:
                # Past date: Send immediately
                should_send = True
            elif date_str == today_str:
                # Today: Send if time >= 18:00
                if now.hour >= 18:
                    should_send = True
            
            if should_send:
                logger.info(f"Sending report for {date_str}...")
                self.send_report(date_str, report_content)
            else:
                # Keep for later
                remaining_content.append(report_content)

        # Rewrite daily_log.txt with remaining content
        new_log_content = "\n\n".join(remaining_content)
        with open(log_path, "w") as f:
            f.write(new_log_content)
            
        if not new_log_content:
            self.daily_log = []
        else:
            self.daily_log = [new_log_content]

    def send_report(self, date_str, report_content):
        """Generates diagram and sends email for a specific date."""
        # Create report directory
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        date_dir_str = date_obj.strftime("%Y%m%d")
        
        report_dir = os.path.join("data", "report", date_dir_str)
        if not os.path.exists(report_dir):
            os.makedirs(report_dir)

        # Archive text
        report_file_path = os.path.join(report_dir, "report.txt")
        with open(report_file_path, "w") as f:
            f.write(report_content)
            
        # Generate diagram
        diagram_data = self.diagram_client.generate_diagram(report_content)
        diagram_path = None
        
        if diagram_data:
             diagram_filename = f"diagram_{datetime.now().strftime('%H%M%S')}.png"
             diagram_path = os.path.join(report_dir, diagram_filename)
             with open(diagram_path, "wb") as f:
                 f.write(diagram_data)
        
        # Send email
        subject = f"Daily Screen Capture Report - {date_str}"
        self.notifier.send_report(subject, report_content, diagram_path)
        
        rumps.notification("Screen Capture", "Report Sent", f"Report for {date_str} sent.")

    def force_flush_reports(self):
        """Force sends all reports in the log regardless of time."""
        # Similar to flush_reports but without the time check for today
        logger.info("Force flushing all reports...")
        log_path = "data/daily_log.txt"
        if not os.path.exists(log_path): return
        
        with open(log_path, "r") as f: content = f.read()
        if not content.strip(): return
        
        # Reuse the parsing logic? Or just send the whole thing as one report?
        # Better to parse dates if possible.
        
        # ... (Reuse parsing logic, but set should_send = True for all) ...
        # For brevity in this edit, I'll implement a simplified version that calls flush but hacks the time check?
        # No, let's just copy-paste the parsing logic for now or refactor.
        # I'll implement the parsing logic inline here for the tool call.
        
        lines = content.split('\n')
        daily_contents = {}
        current_date = None
        import re
        header_pattern = re.compile(r"## \[(\d{4}-\d{2}-\d{2}) .*\]")
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        for line in lines:
            match = header_pattern.search(line)
            if match: current_date = match.group(1)
            target_date = current_date if current_date else today_str
            if target_date not in daily_contents: daily_contents[target_date] = []
            daily_contents[target_date].append(line)
            
        for date_str, lines in daily_contents.items():
            report_content = "\n".join(lines).strip()
            if report_content:
                self.send_report(date_str, report_content)
        
        # Clear log
        with open(log_path, "w") as f: f.write("")
        self.daily_log = []
        self.image_manager.cleanup_old_captures(days=1)

if __name__ == "__main__":
    ScreenCaptureApp().run()
