import queue
import threading
import time
import numpy as np
from src.database.schemas.metadata_schema import Metadata

class MetadataHandler:
    """
    A High-Performance Database Writer.
    It decouples the Engine's main loop from MongoDB by using a 
    background thread and batch inserts.
    """

    def __init__(self, config, logger):
        self.logger = logger
        self.batch_size = config.get('buffer_size', 100) # Default to 100 frames
        self.flush_interval = config.get('flush_interval', 5) # Seconds
        
        # Metadata needs to know which device this data belongs to.
        # The Engine injects 'deviceName' or IDs into the config at runtime.
        self.device_id = config.get('device_id') # If you store ObjectIds
        self.device_name = config.get('deviceName', 'unknown') 

        # Threading Setup
        self.data_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = threading.Thread(target=self._batch_worker, daemon=True)
        self.worker_thread.start()
        
        self.logger.info(f"Metadata Batch Writer started (Batch: {self.batch_size}, Interval: {self.flush_interval}s)")

    def process(self, payload):
        """
        Standard Interface for Dynamic Engine.
        Pushes data to the queue and returns payload immediately (Non-blocking).
        """
        # We only want to queue if there's actual data or if you want a record for every frame.
        # Usually, we check if detections exist to save space.
        track_info = payload['meta'].get('track_ids_info')
        
        if track_info:
            # Create a lightweight dict to send to the worker
            # We don't want to send the full 'frame' (numpy array) to the queue to save RAM
            item = {
                "frame_number": payload['frame_number'],
                "time_stamp": payload['timestamp'],
                "track_ids_info": track_info,
                # Retrieve paths if FrameHandler set them
                "raw_frame_path": payload['meta'].get('raw_frame_path', ""),
                "plotted_frame_path": payload['meta'].get('plotted_frame_path', ""),
                "inference_time": payload['meta'].get('inference_time', 0.0)
            }
            
            try:
                self.data_queue.put(item)
            except Exception as e:
                self.logger.error(f"Failed to queue metadata: {e}")

        return payload

    def _batch_worker(self):
        """
        Background thread loop.
        """
        buffer = []
        last_flush_time = time.time()

        while not self.stop_event.is_set():
            try:
                # Wait for data (1 sec timeout to allow checking stop_event)
                try:
                    item = self.data_queue.get(timeout=1)
                    
                    # Convert dict to Mongo Document Object
                    mongo_obj = self._format_metadata(item)
                    if mongo_obj:
                        buffer.append(mongo_obj)
                        
                except queue.Empty:
                    pass

                # Check flush conditions
                time_since_flush = time.time() - last_flush_time
                is_buffer_full = len(buffer) >= self.batch_size
                is_time_up = time_since_flush >= self.flush_interval

                if buffer and (is_buffer_full or is_time_up):
                    self._flush_to_db(buffer)
                    buffer = [] # Clear buffer
                    last_flush_time = time.time()

            except Exception as e:
                self.logger.error(f"Error in Metadata worker: {e}")

        # Final flush on exit
        if buffer:
            self._flush_to_db(buffer)

    def _flush_to_db(self, buffer):
        """
        Performs the Bulk Insert.
        """
        try:
            # Metadata.objects.insert is a MongoEngine method
            # load_bulk=False prevents it from trying to reload the objects back from DB
            Metadata.objects.insert(buffer, load_bulk=False)
            self.logger.debug(f"✅ Flushed {len(buffer)} records.")
        except Exception as e:
            self.logger.error(f"Database batch insert error: {e}")

    def _format_metadata(self, item):
        """
        Transforms the raw item dict into the Metadata Schema object.
        """
        try:
            # Sanitize track info (convert numpy types to python native)
            formatted_tracks = {}
            raw_tracks = item.get("track_ids_info", {})
            
            for track_key, details in raw_tracks.items():
                # Handle bbox (numpy array -> list)
                bbox = details.get("bbox", [])
                if isinstance(bbox, np.ndarray):
                    bbox = bbox.tolist()
                bbox = [int(x) for x in bbox]

                formatted_tracks[str(track_key)] = {
                    "track_id": str(details.get("track_id")),
                    "bbox": bbox,
                    "confidence": float(details.get("confidence", 0.0)),
                    "label": int(details.get("label_id", 0)), # Ensure keys match Predictor output
                    "label_name": details.get("label_name", "unknown"),
                    "instance_dict": details.get("instance_dict", {})
                }

            return Metadata(
                frame_number=item["frame_number"],
                time_stamp=item["time_stamp"],
                raw_frame_path=item["raw_frame_path"],
                plotted_frame_path=item["plotted_frame_path"],
                device=self.device_id if self.device_id else self.device_name, # Use ID if available, else Name
                inference_time=float(item["inference_time"]),
                track_ids_info=formatted_tracks
            )
        except Exception as e:
            self.logger.error(f"Metadata formatting error: {e}")
            return None

    def close(self):
        """
        Called by Engine.cleanup()
        """
        self.logger.info("Stopping Metadata Handler...")
        self.stop_event.set()
        self.worker_thread.join(timeout=5)
        self.logger.info("Metadata Handler stopped.")