# -*- coding: utf-8 -*-
import os
import time
import threading
import signal
import subprocess
import datetime as dt
import numpy as np
import cv2

# Custom Imports
from src.monitoring_stack.mongodb_logger import initialize_logger
from src.utils.health import FrameHealthValidator  # Your new util module

class IP_Camera:
    """
    Production-grade IP Camera interface.
    Features:
    - GStreamer Low-Latency Pipeline (hardware accelerated where available)
    - Threaded Reader (Producer-Consumer) to prevent buffer lag
    - Automatic Reconnection Logic
    - Integrated Health Monitoring (Signal loss, Glitches, Blur)
    """

    def __init__(
        self,
        ip_address: str,
        device_name: str = "camera-unknown",
        rotation: int = 0,
        logger=None,
        zones=None,
        process_skip_frame: int = 0,
        reconnect_interval: int = 5
    ):
        self.ip_address = ip_address
        self.device_name = device_name
        self.rotation = rotation % 360
        self.zones = zones if zones is not None else []
        self.process_skip_frames = max(0, process_skip_frame)
        self.reconnect_interval = reconnect_interval
        
        # Logging
        self.logger = logger if logger else initialize_logger(category=f"Cam-{device_name}")

        # State
        self.capture = None
        self.is_open = False
        self.is_video_file = os.path.isfile(ip_address)
        self.fps = 0.0
        self.frame_width = 0
        self.frame_height = 0
        
        # Threading & Buffers
        self._lock = threading.Lock()
        self._last_frame = None
        self._last_frame_time = 0.0
        
        # Reader Thread
        self.reader_thread = None
        self.reader_stop_event = threading.Event()
        
        # Health Monitor
        self.health_validator = FrameHealthValidator()
        self.health_thread = None
        self.health_stop_event = threading.Event()
        self.is_connected = False
        self.is_corrupted = False
        self.health_issues = []

        # Signal Handling
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except ValueError:
            pass # Handles case where signal is not in main thread

    # =========================================================================
    # Connection Logic
    # =========================================================================
    
    def connect(self, rtsp_codec: str = "auto"):
        """Establishes connection to the camera/file."""
        self.logger.info(f"Connecting to {self.device_name}...")

        if self.is_video_file:
            self._connect_file()
        else:
            self._connect_stream(rtsp_codec)

        if self.capture and self.capture.isOpened():
            # Warmup read
            ok, frame = self.capture.read()
            if ok and frame is not None:
                self.is_open = True
                self._update_frame_buffer(frame)
                self._extract_metadata(frame)
                self.logger.info(f"✅ Connected to {self.device_name} | FPS: {self.fps:.2f} | {self.frame_width}x{self.frame_height}")
                return True
        
        self.logger.error(f"❌ Failed to connect to {self.device_name}")
        return False

    def _connect_file(self):
        self.logger.info(f"Opening video file: {self.ip_address}")
        self.capture = cv2.VideoCapture(self.ip_address)

    def _connect_stream(self, preferred_codec):
        # 1. Auto-detect codec if requested
        if preferred_codec == "auto":
            preferred_codec = self._detect_stream_codec()
            self.logger.debug(f"Auto-detected codec: {preferred_codec}")

        # 2. Try GStreamer (Best for Latency)
        pipeline = self._gst_pipeline(self.ip_address, codec=preferred_codec)
        self.capture = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

        # 3. Fallback: Try Alternate Codec with GStreamer
        if not self.capture.isOpened():
            alt_codec = "h264" if preferred_codec == "h265" else "h265"
            self.logger.warning(f"GStreamer {preferred_codec} failed. Trying {alt_codec}...")
            pipeline = self._gst_pipeline(self.ip_address, codec=alt_codec)
            self.capture = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

        # 4. Fallback: FFmpeg (Best for Compatibility)
        if not self.capture.isOpened():
            self.logger.warning("GStreamer failed. Falling back to FFmpeg.")
            self.capture = cv2.VideoCapture(self.ip_address, cv2.CAP_FFMPEG)
            # Set buffer size small to reduce latency in FFmpeg
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def _reconnect(self):
        """Internal method to handle reconnection attempts."""
        self.logger.warning(f"🔄 Attempting to reconnect {self.device_name}...")
        if self.capture:
            self.capture.release()
        
        # Simple backoff
        time.sleep(self.reconnect_interval)
        
        try:
            self.connect(rtsp_codec="auto")
        except Exception as e:
            self.logger.error(f"Reconnection failed: {e}")

    # =========================================================================
    # Data Retrieval (Public API)
    # =========================================================================

    def read(self):
        """
        Thread-safe read. Returns the most recent frame from the buffer.
        Returns: (bool, frame)
        """
        if not self.is_open:
            return False, None

        with self._lock:
            if self._last_frame is None:
                return False, None
            # Return a copy to prevent processing threads from modifying the buffer
            return True, self._last_frame.copy()

    # =========================================================================
    # Thread: Frame Reader (Producer)
    # =========================================================================

    def start_reader_loop(self):
        if self.reader_thread and self.reader_thread.is_alive():
            return
        
        self.reader_stop_event.clear()
        self.reader_thread = threading.Thread(
            target=self._reader_loop,
            name=f"{self.device_name}_Reader",
            daemon=True
        )
        self.reader_thread.start()
        self.logger.info("Started Background Reader Thread")

    def _reader_loop(self):
        """
        Continuously grabs frames.
        If the stream dies, it triggers reconnection logic.
        """
        read_errors = 0
        
        while not self.reader_stop_event.is_set():
            if not self.is_open:
                self._reconnect()
                continue

            ok, frame = False, None
            try:
                ok, frame = self.capture.read()
            except Exception as e:
                self.logger.error(f"Read exception: {e}")
                ok = False

            if ok and frame is not None:
                self._update_frame_buffer(frame)
                read_errors = 0 # Reset error counter
            else:
                read_errors += 1
                # If we get consecutive read errors, assume connection is dead
                if read_errors > 10:
                    self.logger.warning(f"Connection lost for {self.device_name} (Read Errors).")
                    self.is_open = False # Trigger reconnect in next loop
                    continue
            
            # Small sleep to prevent CPU spinning if camera FPS is low
            # If it's a file, we might want to respect FPS, but for RTSP we pull as fast as possible
            # to keep the buffer empty.
            if self.is_video_file:
                time.sleep(1.0 / max(self.fps, 1.0))
            else:
                time.sleep(0.005) # 5ms tiny sleep

    def _update_frame_buffer(self, frame):
        processed_frame = self._apply_rotation(frame)
        with self._lock:
            self._last_frame = processed_frame
            self._last_frame_time = time.time()

    # =========================================================================
    # Thread: Health Monitor
    # =========================================================================

    def start_health_monitor(self, interval=30):
        if self.health_thread and self.health_thread.is_alive():
            return

        self.health_stop_event.clear()
        self.health_thread = threading.Thread(
            target=self._health_loop,
            args=(interval,),
            name=f"{self.device_name}_Health",
            daemon=True
        )
        self.health_thread.start()
        self.logger.info("Started Health Monitor Thread")

    def _health_loop(self, interval):
        while not self.health_stop_event.is_set():
            time.sleep(interval)
            
            try:
                # Check 1: Signal Freshness
                time_since_last_frame = time.time() - self._last_frame_time
                
                # If no frame for 5 seconds (or 5x expected frame duration), signal is lost
                threshold = max(5.0, (1.0 / max(1.0, self.fps)) * 10)
                self.is_connected = time_since_last_frame < threshold

                # Check 2: Image Integrity
                frame_sample = None
                with self._lock:
                    if self._last_frame is not None:
                        frame_sample = self._last_frame.copy()

                if self.is_connected and frame_sample is not None:
                    is_healthy, reasons = self.health_validator.validate(frame_sample)
                    self.is_corrupted = not is_healthy
                    self.health_issues = reasons
                else:
                    self.is_corrupted = False # Can't be corrupted if not connected
                    self.health_issues = ["Disconnected"]

                self._log_health_status()

            except Exception as e:
                self.logger.error(f"Health check failed: {e}")

    def _log_health_status(self):
        # Only log warnings if something is wrong
        if not self.is_connected:
             self.logger.warning(f"⚠️ HEALTH ALERT: Camera Disconnected. Last frame: {time.time() - self._last_frame_time:.1f}s ago.")
        elif self.is_corrupted:
             self.logger.warning(f"⚠️ HEALTH ALERT: Image Issues: {self.health_issues}")
        
        # Here you would normally call `self.push_camera_status_to_db(...)`
        # self.push_camera_status_to_db(self.is_connected, self.is_corrupted)

    # =========================================================================
    # Utilities
    # =========================================================================

    def close(self):
        """Stops all threads and releases resources."""
        self.logger.info(f"Closing {self.device_name}...")
        self.is_open = False
        self.reader_stop_event.set()
        self.health_stop_event.set()
        
        if self.reader_thread:
            self.reader_thread.join(timeout=2)
        if self.health_thread:
            self.health_thread.join(timeout=2)
            
        if self.capture:
            self.capture.release()
        
        self.logger.info(f"Closed {self.device_name}.")

    def _apply_rotation(self, frame):
        if self.rotation == 0: return frame
        elif self.rotation == 90: return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif self.rotation == 180: return cv2.rotate(frame, cv2.ROTATE_180)
        elif self.rotation == 270: return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame

    def _extract_metadata(self, frame):
        self.fps = self.capture.get(cv2.CAP_PROP_FPS) or 30.0
        h, w = frame.shape[:2]
        if self.rotation in (90, 270):
            self.frame_width, self.frame_height = h, w
        else:
            self.frame_width, self.frame_height = w, h

    def _detect_stream_codec(self) -> str:
        """Uses ffprobe to peek at the stream and guess the codec."""
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name", "-of", "csv=p=0",
                self.ip_address
            ]
            # Timeout is important here so we don't hang on startup
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                codec = result.stdout.strip().lower()
                if "hevc" in codec or "265" in codec: return "h265"
            return "h264" # Default
        except Exception:
            return "h264"

    def _gst_pipeline(self, uri: str, codec: str = "h264", latency_ms: int = 200) -> str:
        """
        Constructs a low-latency GStreamer pipeline.
        appsink drop=true max-buffers=1 is CRITICAL for low latency AI.
        """
        c = codec.lower()
        depay = "rtph264depay" if c == "h264" else "rtph265depay"
        parse = "h264parse" if c == "h264" else "h265parse"
        decoder = "avdec_h264" if c == "h264" else "avdec_h265"
        
        # Notes:
        # protocols=tcp: More stable than UDP for AI, prevents grey artifacts from packet loss.
        # drop=true: If the AI is slow, drop old frames. Don't queue them.
        return (
            f"rtspsrc location={uri} protocols=tcp latency={latency_ms} ! "
            f"{depay} ! {parse} ! {decoder} ! videoconvert ! "
            f"video/x-raw,format=BGR ! "
            f"appsink drop=true max-buffers=1 sync=false"
        )

    def _signal_handler(self, signum, frame):
        self.close()l