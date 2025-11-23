import pika
import json
import sys
import os
import time
from pymongo import MongoClient
from bson.objectid import ObjectId

# --- Constants ---
DB_NAME = "sentinel_warehouse"
NEXUS_COLLECTION = "nexus_test"
METADATA_COLLECTION = "metadata"
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
EVIDENCE_QUEUE = "evidence_jobs"

# --- MongoDB Connection ---
# Create a persistent client
client = MongoClient("mongodb://...")
db = client[DB_NAME]
nexus_collection = db[NEXUS_COLLECTION]
metadata_collection = db[METADATA_COLLECTION]


def create_video_evidence(nexus_id):
    """
    This is where your ffmpeg logic from Script 2 goes.
    """
    print(f"🎬 [Worker] Starting evidence creation for: {nexus_id}")
    try:
        # 1. Get the KPI record from Nexus DB
        evidence_doc = nexus_collection.find_one({"_id": ObjectId(nexus_id)})
        if not evidence_doc:
            print(f"❌ [Worker] Error: No document found for {nexus_id}")
            return False

        # --- (Your entire 'evidence_pipeline' logic from script 2 goes here) ---
        # 2. Find all frames from 'metadata'
        # 3. Copy frames locally to a temp dir
        # 4. Run ffmpeg
        # 5. ...
        
        # Simulating work
        time.sleep(5) 
        
        # 6. Update the Nexus DB with the path
        output_filename = f"evidence_{nexus_id}.mp4"
        nexus_collection.update_one(
            {"_id": ObjectId(nexus_id)},
            {"$set": {
                "evidencePath": output_filename,
                "processingStatus": "complete"
            }}
        )
        print(f"✅ [Worker] Successfully created evidence: {output_filename}")
        return True

    except Exception as e:
        print(f"❌ [Worker] FAILED to create evidence for {nexus_id}: {e}")
        # Mark as failed in DB so it can be retried
        nexus_collection.update_one(
            {"_id": ObjectId(nexus_id)},
            {"$set": {"processingStatus": "failed", "error": str(e)}}
        )
        return False


def on_message_callback(ch, method, properties, body):
    """
    This function is called by pika every time a message is received.
    """
    try:
        # 1. Parse the message
        data = json.loads(body)
        nexus_id = data.get("nexus_id")
        
        if not nexus_id:
            print("❌ [Worker] Received empty message. Discarding.")
            # Acknowledge the message so it's removed from the queue
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        print(f"▶️ [Worker] Received job, ID: {nexus_id}")
        
        # 2. Do the heavy work (ffmpeg)
        success = create_video_evidence(nexus_id)

        # 3. Acknowledge the message
        if success:
            print(f"👍 [Worker] Job {nexus_id} complete.")
            # Tell RabbitMQ the job is done and can be removed
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            print(f"👎 [Worker] Job {nexus_id} failed. Will not retry.")
            # 'Acknowledge' a failed job to remove it
            # (Or you could 'nack' it to send it to a dead-letter queue)
            ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"🚨 [Worker] Error in callback: {e}")
        # Acknowledge anyway to prevent crash-loop
        ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    print("🚀 [Worker] Starting evidence-creator worker...")
    print(f"Connecting to RabbitMQ at {RABBITMQ_HOST}...")

    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST)
            )
            channel = connection.channel()

            # Declare the queue again to be safe
            channel.queue_declare(queue=EVIDENCE_QUEUE, durable=True)

            # Set Quality of Service (QoS)
            # This tells RabbitMQ to only send 1 message at a time to this worker.
            # Don't send a new job until this worker has 'acked' the current one.
            # This is CRITICAL for a slow, CPU-bound task like ffmpeg.
            channel.basic_qos(prefetch_count=1)

            # 4. Tell the channel to use our callback function
            channel.basic_consume(
                queue=EVIDENCE_QUEUE,
                on_message_callback=on_message_callback
                # auto_ack=False is default, which is what we want
            )

            print("...Connection successful.")
            print(" [*] Waiting for evidence jobs. To exit press CTRL+C")
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            print(f"⚠️ [Worker] Connection lost. Retrying in 5 seconds... Error: {e}")
            time.sleep(5)
        except KeyboardInterrupt:
            print("🛑 [Worker] Shutting down...")
            if connection:
                connection.close()
            break
        except Exception as e:
            print(f"🚨 [Worker] Unhandled error: {e}. Restarting...")
            time.sleep(5)


if __name__ == "__main__":
    main()