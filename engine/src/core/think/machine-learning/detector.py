import cv2
from ultralytics import YOLO
import queue
import threading
import torch
import datetime
import time
import os
import glob
import numpy as np
from collections import deque
from src.utils import plot
from src.database.database import Database
from src.database.metadata_handler import MetadataHandler
from src.database.schemas.zones_schema import Zones
from src.database.schemas.cameras_schema import Cameras
from src.database.schemas.models_schema import Models
from src.core.actuators.frame_handler import FrameHandler
from src.core.think.manager.zone_manager import ZoneManager
from shapely.geometry import Point, Polygon, LineString, box
from src.core.think.manager.universal_predictor import UniversalPredictor
from src.core.think.machine_learning.computer_vision.safety_tracker import SecurityModule


class Detector:
    """
    Universal Detector that uses UniversalPredictor to detect objects with different models,
    track them, and handle zone/line-based logic.
    """

    def __init__(self, config, logger=None, shutdown_event=None):
        self.device = config.get('device', 'cuda:0')
        self.plot = config.get('plot', False)
        self.logger = logger
        self.shutdown_event = shutdown_event

        self.database = Database()
        self.database.connect_db()

        self.conf_threshold = config.get('conf_threshold', 0.4)

        # Get model configuration
        self.model_config = self._get_model_config(config)
        
        # Initialize Universal Predictor
        self.predictor = UniversalPredictor(
            model_config=self.model_config,
            device=self.device,
            logger=self.logger,
            plot_overlays=config.get("plot_overlays", True),
        )
        self.logger.info(f"Universal Predictor initialized with {self.model_config['model_type']} model.")

        self.ip_camera = config.get('ip_camera')
        if not self.ip_camera:
            self.logger.error("No 'ip_camera' instance provided in config.")
            raise ValueError("IP Camera configuration is missing.")
        
        self.device_name = self.ip_camera.device_name
        self.is_video_file = self.ip_camera.is_video_file
        self.fps = self.ip_camera.fps

        # Initialize Security Module if enabled
        self.security_module = None
        if config.get("security_enabled", False):
            _, frame = self.ip_camera.capture.read()
            template_frame = frame
            self.security_module = SecurityModule(self.device_name, template_frame)
            self.logger.info("Security Module Initialized.")

        # Initialize zone management
        self.zones = getattr(self.ip_camera, "zones", [])  
        self.zone_manager = ZoneManager(logger=self.logger, camera={"device_name": self.device_name})
        self.zone_manager.zones = list(self.zones or [])  
        self.zone_manager.set_zones()
        
        if self.is_video_file:
            self.video_path = self.ip_camera.ip_address
        else:
            self.video_path = None

        self.rotation = self.ip_camera.rotation
        if self.rotation in [90, 270]:
            rotated_frame_size = (int(self.ip_camera.frame_height), int(self.ip_camera.frame_width))
        else:
            rotated_frame_size = (int(self.ip_camera.frame_width), int(self.ip_camera.frame_height))

        self.save_video = True
        self.save_raw_video = True
        self.target_fps = 5

        self.raw_video_writer = None
        self.video_writer = None

        current_datetime = datetime.datetime.now(datetime.timezone.utc)
        self.run_time_str = current_datetime.strftime("%d%m%Y%H%M%S%f")
        date = current_datetime.date()
        
        self.store_crops_flag = False
        if self.store_crops_flag:
            self.crop_dir = "./results/track_ids/"
            
        self.frame_handler = FrameHandler(
            device_name=self.device_name,
            base_dir="./results/frames",
            default_kind="raw",
            image_format="jpg",
            jpeg_quality=90,
            enc_workers=5,   # try 2–3 if CPU headroom exists
            io_workers=5,    # try 2 if NVMe SSD; 1 if HDD
            logger=self.logger,
        )

        self.metadata_handler = MetadataHandler(
            self.ip_camera.ip_address, 
            self.ip_camera.device_name, 
            logger=self.logger
        )

    def _get_model_config(self, config):
        """
        Get model configuration from config or database.
        Priority: direct config > database lookup > default
        """
        # Option 1: Model config directly in pipeline config
        if 'model_config' in config:
            return config['model_config']
        
        # Option 2: Model type and name specified, load from database
        model_type = config.get('model_type', 'YOLO')
        model_name = config.get('model_name')
        
        if model_name:
            model_config = self._load_model_config_from_db(model_name)
            if model_config:
                return model_config
        
        # Option 3: Default configuration with fallback values
        return self._get_default_config(model_type)
    
    def _load_model_config_from_db(self, model_name):
        """Load model configuration from MongoDB collection"""
        try:
            model_doc = Model.objects(model_name=model_name).first()
            if model_doc:
                config = model_doc.to_mongo().to_dict()
                # Convert to expected format
                return {
                    'model_type': config.get('model_type', 'YOLO'),
                    'model_path': config.get('model_path'),
                    'tracker_path': config.get('tracker_path'),
                    'convert_engine': config.get('convert_engine', False),
                    'conf': config.get('conf', 0.6),
                    'class_ids': config.get('class_ids', [0])
                }
            else:
                self.logger.warning(f"Model '{model_name}' not found in database")
        except Exception as e:
            self.logger.warning(f"Could not load model config from database: {e}")
        
        return None
    
    def _get_default_config(self, model_type):
        """Get default configuration for testing"""
        self.logger.info("Using default model configuration for testing")
        
        if model_type.upper() == 'YOLO':
            return {
                'model_type': 'YOLO',
                'model_path': "src/models/Iskcon_head_detection_yolov8m_15_aug.pt",
                'tracker_path': "src/configs/machine_learning/computer_vision/tracker/botsort_with_reid.yaml",
                'convert_engine': False,  # Set to True if you want TensorRT conversion
                'conf': 0.6,
                'class_ids': [0, 1]
            }
        else:
            raise ValueError(f"Unsupported model_type: {model_type}")

    def _get_center(self, bbox):
        """Calculate center point of bounding box"""
        x_center = (bbox[0] + bbox[2]) / 2
        y_center = (bbox[3])
        return (x_center, y_center)
    
    def predict(self, frame, current_time, frame_number):
        """Updated predict method using UniversalPredictor"""
        # Rotate frame if needed
        if self.rotation != 0:
            frame = self.rotate_frame(frame, self.rotation)

        start_time = time.time()
        
        raw_path = self.frame_handler.submit(
            frame, ts_utc=current_time, frame_number=int(frame_number), kind="raw"
        )
        # Use UniversalPredictor for model-agnostic prediction
        track_ids_dict, frame = self.predictor.predict(
            frame=frame,
            current_time=current_time,
            run_time_str=self.run_time_str
        )

        

        # Plot zones if available
        if getattr(self.zone_manager, "zone_dict", None):
            frame = plot.plot_shapes(frame, self.zone_manager.zone_dict)
            
        plotted_path = self.frame_handler.submit(
            frame, ts_utc=current_time, frame_number=int(frame_number), kind="plotted"
        )
        
        end_time = time.time()
        inference_time = end_time - start_time

        # Process detection results in thread
        _ = self.process_detection_results_thread(
            track_ids_dict, frame, current_time, frame_number, inference_time, raw_path, plotted_path
        )

        # Update zonal relationships
        if getattr(self, "zone_manager", None) and track_ids_dict:
            track_ids_dict = self.zone_manager.update_track_ids_status(track_ids_dict)
    

        # Save crops
        if self.store_crops_flag and track_ids_dict:
            track_ids_dict = self.store_crops(frame, track_ids_dict)

        return frame
    
    def rotate_frame(self, frame, angle):
        """Rotate frame by specified angle"""
        if angle == 90:
            return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            return cv2.rotate(frame, cv2.ROTATE_180)
        elif angle == 270:
            return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else:
            return frame

    def process_detection_results(self, arg_queue):
        """Process detection results in separate thread"""
        track_ids_dict, frame, current_time, frame_number, inference_time, raw_path, plotted_path = arg_queue.get()
        arg_queue.task_done()

        if not track_ids_dict:
            track_ids_dict = {}  

        if self.zone_manager:
            track_ids_dict = self.zone_manager.update_track_ids_status(track_ids_dict)
            if self.zone_manager.zone_dict:
                frame = plot.plot_shapes(frame, self.zone_manager.zone_dict)

        if self.store_crops_flag and track_ids_dict:
            track_ids_dict = self.store_crops(frame, track_ids_dict)

        if self.metadata_handler:
            processed_data = {
                "time_stamp": current_time,
                "raw_frame_path": raw_path, 
                "plotted_frame_path": plotted_path,
                "frame_number": frame_number,
                "track_ids_info": track_ids_dict, 
                "inference_time": float(inference_time)
            }
            self.metadata_handler.process(processed_data)

    def store_crops(self, frame, track_ids_dict):
        """Store cropped images of detected objects"""
        track_id_path_list = []
        for track_id, obj_info in track_ids_dict.items():
            bbox = obj_info["bbox"]
            label = obj_info["label_name"]

            x1, y1, x2, y2 = map(int, bbox)
            P = 10
            h, w = frame.shape[:2]
            x1p, y1p = max(0, x1 - P), max(0, y1 - P)
            x2p, y2p = min(w, x2 + P), min(h, y2 + P)
            if x2p <= x1p or y2p <= y1p:
                continue

            crop = frame[y1p:y2p, x1p:x2p]
            if crop.size == 0:
                continue

            current_datetime = datetime.datetime.now(datetime.timezone.utc)
            date = str(current_datetime.date())
            current_time = current_datetime.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            # Check if instance_dict exists (zone information)
            instance_dict = obj_info.get("instance_dict", {})

            if len(instance_dict) > 0:
                not_saved = True
                for zone_name_index in instance_dict:
                    if instance_dict[zone_name_index]['location'] == "inside":
                        zone_name = zone_name_index.replace(" ", "_")
                        file_name = f"{current_time}-{label}-{instance_dict[zone_name_index]['location']}-{zone_name}.jpg"
                        track_id_dir = os.path.join(self.crop_dir, date, self.device_name, zone_name, track_id)

                        if not os.path.exists(track_id_dir):
                            os.makedirs(track_id_dir, exist_ok=True)

                        out_fp = os.path.join(track_id_dir, file_name)
                        if cv2.imwrite(str(out_fp), crop):
                            track_id_path_list.append(out_fp)
                            not_saved = False

                if not_saved:
                    zone_name = "no-zone"
                    file_name = f"{current_time}-{label}-_-{zone_name}.jpg"
                    track_id_dir = os.path.join(self.crop_dir, date, self.device_name, zone_name, track_id)

                    if not os.path.exists(track_id_dir):
                        os.makedirs(track_id_dir, exist_ok=True)

                    out_fp = os.path.join(track_id_dir, file_name)
                    if cv2.imwrite(str(out_fp), crop):
                        track_id_path_list.append(out_fp)
            else:
                # No zone information, save in no-zone folder
                zone_name = "no-zone"
                file_name = f"{current_time}-{label}-_-{zone_name}.jpg"
                track_id_dir = os.path.join(self.crop_dir, date, self.device_name, zone_name, track_id)

                if not os.path.exists(track_id_dir):
                    os.makedirs(track_id_dir, exist_ok=True)

                out_fp = os.path.join(track_id_dir, file_name)
                if cv2.imwrite(str(out_fp), crop):
                    track_id_path_list.append(out_fp)

            track_ids_dict[track_id]["track_id_path_list"] = track_id_path_list

        return track_ids_dict

    def process_detection_results_thread(self, results, frame, current_time, frame_number, inference_time, raw_path, plotted_path):
        """Create thread for processing detection results"""
        arg_queue = queue.Queue(maxsize=1)
        arg_queue.put((results, frame, current_time, frame_number, inference_time, raw_path, plotted_path))

        thread = threading.Thread(target=self.process_detection_results, args=(arg_queue,))
        thread.daemon = True
        thread.start()
        return thread
    
    def process(self):
        """
        Main loop for live camera processing with universal model detection.
        """
        self.logger.info(f"Entering live loop: is_open={self.ip_camera.is_open}, fps={self.ip_camera.fps}, rotation={self.rotation}")
        if not self.ip_camera.is_open:
            self.logger.error("IP camera is not open after connect(); exiting Detector.process()")
            return

        descriptor = f"Processing {self.device_name} Live Stream with {self.model_config['model_type']} Detection"
        self.logger.info(descriptor)

        interval = datetime.timedelta(seconds=1 / self.target_fps)
        last_proc_time = None
        
        frame_number = 0
        initial_time_stamp = datetime.datetime.now(datetime.timezone.utc)
        video_doc = Cameras.objects(camera_address=self.video_path).first()
        
        self.no_frame_count = 0
        self.cam_result = True
        
        try:
            while self.ip_camera.is_open and self.cam_result:
                current_time = datetime.datetime.now(datetime.timezone.utc)

                if last_proc_time is not None and (current_time - last_proc_time) < interval:
                    continue
                last_proc_time = current_time

                self.cam_result, frame = self.ip_camera.capture.read()

                if frame is None:
                    self.no_frame_count += 1
                    if self.no_frame_count >= 10:
                        break
                    else:
                        continue

                frame_number = self.ip_camera.capture.get(cv2.CAP_PROP_POS_FRAMES)

                if frame is not None and self.cam_result:
                    raw_frame = frame.copy()
                    processed_frame = self.predict(raw_frame, current_time, frame_number)
                    
                    # If Security Module is enabled, process security features
                    if self.security_module:
                        self.security_module.process_frame(raw_frame)

                    if frame_number % 100 == 0 and video_doc:
                        video_doc.status = f"processing ({frame_number} frames done)"
                        video_doc.save()

        except Exception as e:
            self.logger.error(f"Error in Detector: {e}")
            status = f"Error in Detector: {e}"
        finally:
            self.logger.info(f"🧹 Cleaning up resources for {self.device_name}")
            
            # Stop RTSP streaming if exists
            if hasattr(self, 'rtsp_streamer'):
                self.logger.info(f"🛑 Stopping RTSP stream for {self.device_name}")
                self.rtsp_streamer.stop_device_stream(self.device_name)

            # Clean up predictor
            if hasattr(self, 'predictor'):
                self.predictor.finish()

            if self.ip_camera.capture:
                self.ip_camera.capture.release()

            status = "Finally"
            if hasattr(self, "frame_handler") and self.frame_handler:
                self.frame_handler.close()

            if hasattr(self, 'metadata_handler'):
                self.metadata_handler.close()
            
            self.ip_camera.capture.release()
            self.logger.info("Released VideoCapture object.")
            self.logger.info("Cleaned up all resources.")
            print("************************* Completed *************************\n")