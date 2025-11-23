import mongoengine as db
import datetime
from mongoengine import Document, IntField, DateTimeField, StringField, DictField, FloatField, ListField, ReferenceField, BooleanField, LongField, ObjectIdField


class Cameras(db.Document):
    # device_name = db.StringField(required=True, unique=True) 
    device_name = db.StringField(required=True)  # Format: Camera-001
    store = db.ReferenceField("Stores")  # Store associated with this camera
    camera_address = db.StringField(required=True)  # Video feed URL or location
    services = db.ReferenceField("Services")
    zones = db.ListField(db.ReferenceField('Zones'))  # References multiple zone mappings
    process_skip_frame = db.IntField(default=5)  # Skip frame interval for processing
    active = db.BooleanField(default=True)
    save_plotted_video = db.BooleanField(default=False)
    save_raw_video = db.BooleanField(default=False)
    rotation = db.IntField(default=0)  # Camera rotation in degrees
    status = db.StringField()
    department = db.StringField()
    frame = db.StringField()

    created_at = db.DateTimeField(default=datetime.datetime.now(datetime.timezone.utc))
    updated_at = db.DateTimeField(default=datetime.datetime.now(datetime.timezone.utc))
    meta = {
        'collection': 'cameras'
    }
    def __str__(self):
        return f"Camera {self.device_name}"
      
    