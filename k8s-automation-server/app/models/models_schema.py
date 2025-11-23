import mongoengine as db 
from datetime import datetime

class Models(db.Document):
    modelType = db.StringField(required=True)
    modelName = db.StringField(requested=True)  
    modelPath = db.StringField(required=True)  
    trackerPath = db.StringField()
    convertEngine = db.BooleanField(default=True)
    classIds =  db.ListField(db.IntField())
    conf = db.FloatField(default=0.6)  
    inputDims =  db.ListField(db.IntField())
    store = db.ReferenceField("Stores")
    createdAt = db.StringField(default=datetime.utcnow)
    updatedAt = db.StringField(default=datetime.utcnow)
    configYamlPath = db.StringField(requested=False, default="")


    meta = {
        'collection': 'models',
        'indexes': [
            'modelName',
            'modelType',
            'createdAt'
        ]
    }
