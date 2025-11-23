from mongoengine import Document, IntField, DateTimeField, StringField, DictField, FloatField, ListField  

class Metadata(Document):
    # Basic Video and Frame Info
    frame_number = IntField(required=True)
    time_stamp = DateTimeField(required=True)
    raw_frame_path = StringField(required=True)
    plotted_frame_path = StringField(required=False)
    device_name = StringField(required=True)
    inference_time = FloatField()
    track_ids_info = DictField(
        field=DictField(
            fields={
                "track_id": StringField(required=True),
                "track_id_path_list": StringField(required=False),
                "bbox": ListField(IntField(), required=True),
                "confidence": FloatField(required=True),
                "label": IntField(required=True),
                "label_name": StringField(required=True),
                "instance_dict": DictField()
            }
        )
    )
    meta = {
        'collection': 'metadata',
        'indexes': ['time_stamp']
    }

    