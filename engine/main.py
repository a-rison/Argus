import os
import sys
import json
import time
import importlib
import threading
import signal
from datetime import datetime, timezone

from src.utils.logger import Logger
from src.database.database import Database
from src.core.sensors.ip_camera import IP_Camera
from src.database.schemas.cameras_schema import Cameras
from src.database.schemas.services_schema import Services
from src.database.schemas.camera_config_schema import CameraConfig

shutdown_event = threading.Event()

def signal_handler(sig, frame):
    print("🛑 Shutdown signal received!")
    shutdown_event.set()

class DynamicEngine:
    def __init__(self, camera_id, service_id, mongodb_uri):
        self.logger = Logger(category="DynamicEngine").get_logger()
        self.db = Database()
        self.db.connect_db(mongodb_uri)
        
        self.camera_id = camera_id
        self.service_id = service_id
        self.pipeline_modules = [] # List of instantiated objects
        self.camera = None

    def load_configuration(self):
        """
        Fetches config from DB and loads the JSON pipeline definition.
        """
        # 1. Fetch DB Documents (Same as before)
        self.cam_doc = Cameras.objects(id=self.camera_id).first()
        self.svc_doc = Services.objects(id=self.service_id).first()
        
        # 2. Load the JSON Pipeline Config
        try:
            with open(self.svc_doc.pipelinePath, 'r') as f:
                self.json_config = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load JSON config: {e}")
            sys.exit(1)

        # 3. Initialize Camera (The Source)
        # Get Zones from CameraConfig... (omitted for brevity, same as your old code)
        zone_ids = [] # Logic to get zones
        
        self.camera = IP_Camera(
            ip_address=self.cam_doc.cameraAddress,
            device_name=self.cam_doc.deviceName,
            zones=zone_ids,
            process_skip_frame=self.cam_doc.processSkipFrame,
            rotation=self.cam_doc.rotation
        )
        
        if not self.camera.connect():
            self.logger.error("Could not connect to camera.")
            sys.exit(1)

    def build_pipeline(self):
        """
        Dynamically imports and instantiates classes defined in the JSON.
        """
        modules_list = self.json_config.get("modules", [])
        
        for step in modules_list:
            name = step["name"]
            mod_path = step["module_path"]
            cls_name = step["class_name"]
            static_config = step.get("config", {})

            self.logger.info(f"🔌 Loading module: {name} ({cls_name})")
            
            try:
                # DYNAMIC IMPORT MAGIC
                module_ref = importlib.import_module(mod_path)
                class_ref = getattr(module_ref, cls_name)
                
                # Instantiate. We pass the config + a reference to the engine/camera if needed
                # Note: We merge the JSON config with runtime data
                runtime_config = static_config.copy()
                runtime_config['ip_camera'] = self.camera # Inject camera dependency
                runtime_config['deviceName'] = self.cam_doc.deviceName
                
                instance = class_ref(config=runtime_config, logger=self.logger)
                
                self.pipeline_modules.append(instance)
                
            except Exception as e:
                self.logger.error(f"❌ Failed to load module {name}: {e}")
                sys.exit(1)

    def run(self):
        """
        The Main Loop: Captures frame -> Passes through all modules -> Repeats
        """
        self.logger.info("🚀 Pipeline Started.")
        frame_count = 0
        
        try:
            while not shutdown_event.is_set() and self.camera.is_open:
                # 1. Capture
                ret, frame = self.camera.capture.read()
                if not ret:
                    self.logger.warning("Empty frame.")
                    time.sleep(0.1)
                    continue
                
                # 2. Create the Payload (The data packet for this frame)
                payload = {
                    "frame": frame,
                    "original_frame": frame.copy(),
                    "timestamp": datetime.now(timezone.utc),
                    "frame_number": frame_count,
                    "meta": {} # Store results here
                }

                # 3. Execute Pipeline Steps
                for module in self.pipeline_modules:
                    # Every module MUST return the payload (modified or not)
                    payload = module.process(payload)
                    
                    # If a module returns None, it means "abort this frame"
                    if payload is None:
                        break

                frame_count += 1

        except Exception as e:
            self.logger.error(f"Pipeline Runtime Error: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        self.logger.info("Cleaning up...")
        if self.camera:
            self.camera.disconnect()
        # Allow modules to cleanup too
        for mod in self.pipeline_modules:
            if hasattr(mod, 'close'):
                mod.close()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Grab Env Vars
    c_id = os.environ.get("CAMERA_ID")
    s_id = os.environ.get("SERVICE_ID")
    mongo_uri = os.environ.get("MONGODB_URI")

    engine = DynamicEngine(c_id, s_id, mongo_uri)
    engine.load_configuration()
    engine.build_pipeline()
    engine.run()