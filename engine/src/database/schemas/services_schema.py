import mongoengine as db
import datetime
from mongoengine import Document, IntField, DateTimeField, StringField, DictField, FloatField, ListField, ReferenceField, BooleanField, LongField, ObjectIdField


class Services(db.Document):
    service_name = db.StringField(required=True, unique=True)
    descriptions= db.StringField()
    pipeline_path = db.StringField(required=True)
    fixed_zones = db.BooleanField(default=False)
    # default = db.ListField(db.StringField()) 
    created_at = db.DateTimeField(default=datetime.datetime.now(datetime.timezone.utc))
    
    
class DefaultServices(db.Document):
    name = db.StringField(required=True, unique=True)
    descriptions= db.StringField()
    pipeline_path = db.StringField(required=True)
    fixed_zones = db.BooleanField(default=False)
    zones = db.ListField(db.ReferenceField('Zones'))   
    created_at = db.DateTimeField(default=datetime.datetime.now(datetime.timezone.utc))

  