import pika
import json
import sys
from pymongo import MongoClient

# --- Constants ---
# (Your DB constants)
DB_NAME = "sentinel_warehouse"
NEXUS_COLLECTION = "nexus_test"

# RabbitMQ Constants
RABBITMQ_HOST = "rabbitmq"  # Use the Kubernetes Service name
EVIDENCE_QUEUE = "evidence_jobs" # The name of our "todo" list


def get_pipeline(start_day, end_day, device_id):
    """
    Returns the main aggregation pipeline.
    This is YOUR aggregation pipeline, but I've modified the
    very last stage.
    """
    pipeline = [
        # ... (all your $match, $group, $project stages)...
        # ...
        # THIS IS THE FINAL STAGE:
        {
            "$merge": {
                "into": NEXUS_COLLECTION,
                "on": ["trackID", "startTime", "device", "service"],
                "whenMatched": "merge",
                "whenNotMatched": "insert"
            }
        }
    ]
    return pipeline

def publish_job_to_queue(nexus_id):
    """
    Sends a new job to the evidence creator queue.
    """
    connection = None
    try:
        # 1. Connect to RabbitMQ
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST)
        )
        channel = connection.channel()

        # 2. Declare the queue (this is idempotent, safe to run)
        #    durable=True means the queue will survive a RabbitMQ restart
        channel.queue_declare(queue=EVIDENCE_QUEUE, durable=True)

        # 3. Create the message body
        message_body = json.dumps({"nexus_id": str(nexus_id)})

        # 4. Publish the message
        channel.basic_publish(
            exchange='',              # Default exchange
            routing_key=EVIDENCE_QUEUE, # The name of the queue
            body=message_body,
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent # Make message persistent
            )
        )
        print(f"✅ [Aggregator] Sent job to queue: {nexus_id}")

    except Exception as e:
        print(f"❌ [Aggregator] Failed to publish job: {e}")
    finally:
        if connection:
            connection.close()

def run_aggregation():
    # 1. Connect to MongoDB
    client = MongoClient("mongodb://...")
    db = client[DB_NAME]
    
    # --- YOUR AGGREGATION LOGIC ---
    # This is a placeholder for your camera fetching and aggregation logic
    # ...
    
    # WHEN YOUR AGGREGATION RUNS AND INSERTS/MERGES DATA:
    # The $merge stage doesn't easily return the IDs of what it wrote.
    # A common pattern is to query for what *was* written
    # immediately after.
    
    # FOR THIS EXAMPLE, let's pretend one aggregation just ran
    # and we got a result.
    
    # A better way is to modify your pipeline to not $merge,
    # but to output to a temp collection, read the IDs,
    # then publish, then merge.
    
    # A SIMPLER way: Run your $merge as planned.
    # Then, run a *second* query to find unprocessed jobs.
    
    # Find all entries from today that haven't been queued yet
    unprocessed_jobs = db[NEXUS_COLLECTION].find({
        "evidenceQueued": {"$exists": False} 
    })
    
    ids_to_queue = []
    for job in unprocessed_jobs:
        ids_to_queue.append(job["_id"])

    if not ids_to_queue:
        print("ℹ️ [Aggregator] No new jobs to queue.")
        return

    print(f"Found {len(ids_to_queue)} new jobs to queue...")

    for job_id in ids_to_queue:
        # 2. Publish a job for each new entry
        publish_job_to_queue(job_id)
        
        # 3. Mark the job as "queued" in the DB
        db[NEXUS_COLLECTION].update_one(
            {"_id": job_id},
            {"$set": {"evidenceQueued": True}}
        )

# --- Main Execution ---
if __name__ == "__main__":
    try:
        run_aggregation()
    except Exception as e:
        print(f"🚨 Aggregation job failed: {e}")
        sys.exit(1)