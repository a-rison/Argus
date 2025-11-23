import mongoengine as db
import datetime
from mongoengine import Document, IntField, DateTimeField, StringField, DictField, FloatField, ListField, ReferenceField, BooleanField, LongField, ObjectIdField


class CameraStatus(Document):
    device_name = StringField(required=True)
    timestamp = DateTimeField(default=datetime.datetime.now(datetime.timezone.utc))
    connection = BooleanField(required=True)  # True = Connected, False = Disconnected
    frame_corruption = BooleanField(required=True)  # True = Corrupted, False = OK

    meta = {
        'collection': 'camera_status',  # Optional: sets the collection name in MongoDB
        'indexes': ['device_name', 'timestamp']
    }