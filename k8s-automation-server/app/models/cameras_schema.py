import mongoengine as db
import datetime
from .stores_schema import Stores
from src.database.schemas.models_schema import Models

class Cameras(db.Document):
    deviceName = db.StringField(required=True)  
    store = db.ReferenceField("Stores") 
    cameraAddress = db.StringField(required=True)  
    baseModel = db.ReferenceField("Models")
    processSkipFrame = db.IntField(default=5) 
    active = db.BooleanField(default=True)
    savePlottedFrame = db.BooleanField(default=False)
    saveRawFrame = db.BooleanField(default=False)
    rotation = db.IntField(default=0)  
    status = db.StringField()
    department = db.StringField()
    frame = db.StringField()
    ipAddress = db.StringField()
    fowardedAddress = db.StringField()

    createdAt = db.DateTimeField(default=datetime.datetime.now(datetime.timezone.utc))
    updatedAt = db.DateTimeField(default=datetime.datetime.now(datetime.timezone.utc))
    meta = {
        'collection': 'cameras'
    }
    def __str__(self):
        return f"Camera {self.device_name}"
      
    