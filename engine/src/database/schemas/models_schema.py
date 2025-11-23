import mongoengine as db 
from mongoengine import Document, StringField, FloatField, ListField, IntField, BooleanField, DictField , ReferenceField
from datetime import datetime

class Models(db.Document):
    # device_name = db.StringField(required=True, unique=True) 
    model_type = db.StringField(required=True)
    model_name = db.stringField(requested=True)  
    model_path = db.StringField(required=True)  
    tracker_path = db.StringField()
    convert_engine = db.BooleanField(default=True)
    class_ids =  db.ListField(db.IntField())
    conf = db.IntField(default=0.6)  
    input_dims =  db.ListField(db.IntField())
    store = db.ReferenceField("Stores")
    services = db.ListField(db.ReferenceField("Services"))
    created_at = StringField(default=datetime.utcnow)
    updated_at = StringField(default=datetime.utcnow)


    meta = {
        'collection': 'models',
        'indexes': [
            'model_name'
            'model_type',
            'created_at'
        ]
    }
