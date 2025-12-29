import mss
import mss.tools
import os
import subprocess
from datetime import datetime
from PIL import Image
from src.utils import setup_logger, get_config

logger = setup_logger(__name__)

class ScreenCapturer:
    def __init__(self, output_dir="data/captures"):
        self.output_dir = output_dir
        self.capture_count = 0
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def get_active_window_bounds(self):
        """
        Returns the bounds of the active window (left, top, width, height).
        Requires Accessibility permissions for the terminal/app.
        """
        script = '''
        tell application "System Events"
            set frontApp to first application process whose frontmost is true
            set frontAppName to name of frontApp
            
            tell frontApp
                set allWindows to every window
                set maxArea to 0
                set targetWindow to missing value
                
                repeat with w in allWindows
                    try
                        set {w_width, w_height} to size of w
                        set area to w_width * w_height
                        if area > maxArea then
                            set maxArea to area
                            set targetWindow to w
                        end if
                    end try
                end repeat
                
                if targetWindow is not missing value then
                    set windowTitle to name of targetWindow
                    set {x, y} to position of targetWindow
                    set {w, h} to size of targetWindow
                    return {frontAppName, windowTitle, x, y, w, h}
                else
                    return "No Window"
                end if
            end tell
        end tell
        '''
        try:
            p = subprocess.Popen(['osascript', '-e', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            output, error = p.communicate(timeout=2)
            
            if error:
                if "not allowed assistive access" in error or "-1719" in error or "-25211" in error:
                    logger.warning("Accessibility permission denied. Cannot get active window bounds. Falling back to full screen.")
                else:
                    logger.warning(f"AppleScript error: {error.strip()}")
                return None
            
            if output.strip():
                # Output format: "AppName, WindowTitle, x, y, w, h"
                parts = output.strip().split(', ')
                if len(parts) >= 6:
                    app_name = parts[0]
                    window_title = parts[1]
                    # Handle potential commas in titles by taking the last 4 elements as bounds
                    bounds_parts = parts[-4:]
                    x, y, w, h = [int(val) for val in bounds_parts]
                    
                    logger.info(f"Targeting Active Window: App='{app_name}', Title='{window_title}', Bounds=(x={x}, y={y}, w={w}, h={h})")
                    return {'left': x, 'top': y, 'width': w, 'height': h}
        except Exception as e:
            logger.error(f"Failed to get active window bounds: {e}")
        
        return None

    def capture(self):
        """Captures the screen based on configuration."""
        self.capture_count += 1
        capture_mode = get_config("CAPTURE_MODE", "all_screens")
        
        if capture_mode == "active_window":
            # Every 5th capture, force full screen capture for context
            if self.capture_count % 5 == 0:
                logger.info(f"Capture count {self.capture_count}: Forcing full screen capture for context.")
                return self._capture_all_monitors()

            bounds = self.get_active_window_bounds()
            if bounds:
                return self._capture_region(bounds)
            else:
                logger.warning("Could not get active window bounds. Capturing all monitors instead.")
        
        return self._capture_all_monitors()

    def _capture_region(self, monitor):
        """Captures a specific region defined by monitor dict {'left', 'top', 'width', 'height'}."""
        with mss.mss() as sct:
            try:
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"capture_window_{timestamp}.png"
                filepath = os.path.join(self.output_dir, filename)
                
                img.save(filepath)
                logger.info(f"Active window captured: {filepath}")
                return filepath
            except Exception as e:
                logger.error(f"Failed to capture region: {e}")
                return None

    def _capture_all_monitors(self):
        """Captures all monitors and stitches them into a single image."""
        with mss.mss() as sct:
            monitors = sct.monitors[1:] # Skip index 0 (combined) as it may be unreliable
            
            if not monitors:
                logger.error("No monitors detected.")
                return None

            # Calculate total bounds
            min_x = min(m['left'] for m in monitors)
            min_y = min(m['top'] for m in monitors)
            max_x = max(m['left'] + m['width'] for m in monitors)
            max_y = max(m['top'] + m['height'] for m in monitors)
            
            total_width = max_x - min_x
            total_height = max_y - min_y
            
            # Create a new blank image
            canvas = Image.new('RGB', (total_width, total_height), (0, 0, 0))
            
            for i, monitor in enumerate(monitors):
                # Capture monitor
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                
                # Calculate position on canvas
                x = monitor['left'] - min_x
                y = monitor['top'] - min_y
                
                canvas.paste(img, (x, y))
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"capture_{timestamp}.png"
            filepath = os.path.join(self.output_dir, filename)
            
            canvas.save(filepath)
            logger.info(f"Screen captured (Stitched {len(monitors)} monitors): {filepath}")
            return filepath

if __name__ == "__main__":
    capturer = ScreenCapturer()
    capturer.capture()
