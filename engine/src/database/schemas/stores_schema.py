import mongoengine as db
import datetime
from mongoengine import Document, IntField, DateTimeField, StringField, DictField, FloatField, ListField, ReferenceField, BooleanField, LongField, ObjectIdField

class Stores(db.Document):
    store_id = db.StringField()
    name = db.StringField()
    organization = db.StringField()
    format = db.StringField()
    port = db.IntField()
    category = db.StringField()
    state = db.StringField()
    city = db.StringField()
    district = db.StringField()
    location = db.DictField()
    layout = db.DictField()
    createdAt = db.DateTimeField(default=datetime.datetime.now(datetime.timezone.utc))
    updatedAt = db.DateTimeField(default=datetime.datetime.now(datetime.timezone.utc))
