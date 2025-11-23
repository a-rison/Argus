import mongoengine as db
import datetime
from mongoengine import Document, IntField, DateTimeField, StringField, DictField, FloatField, ListField, ReferenceField, BooleanField, LongField, ObjectIdField

class Zones(db.Document):
    zone_id = db.StringField(required=True, unique=True) 
    name = db.StringField(required=True)  
    zone_type = db.StringField(required=True)  
    store = db.ReferenceField('Stores')  
    colourHex = db.StringField(default="#09467c")  
    roi = db.ListField(db.ListField(db.FloatField())) 
    createdAt = db.DateTimeField(default=datetime.datetime.now(datetime.timezone.utc))
    updatedAt = db.DateTimeField(default=datetime.datetime.now(datetime.timezone.utc))

    meta = {
        'indexes': [
            {'fields': ['zone_id'], 'unique': True}
        ]
    }