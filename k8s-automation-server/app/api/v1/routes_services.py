from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core import k8s_manager  # Import your manager

router = APIRouter()

class ServiceSubscription(BaseModel):
    service_name: str
    image_name: str # e.g., "my-repo/warehouse-aggregator:v1"
    service_id: str   # e.g., the ObjectId of the service in your DB
    schedule: str = "*/1 * * * *"

@router.post("/subscribe")
def subscribe_service(sub: ServiceSubscription):
    """
    Subscribes a new service, which creates its
    necessary CronJobs on the cluster.
    """
    print(f"Received subscription request for: {sub.service_name}")
    
    # Call your manager to do the real work
    cronjob_name = k8s_manager.create_cronjob(
        service_name=sub.service_name,
        image_name=sub.image_name,
        service_id=sub.service_id,
        schedule=sub.schedule
    )
    
    if cronjob_name:
        return {"status": "success", "cronjob_created": cronjob_name}
    else:
        raise HTTPException(status_code=500, detail="Failed to create Kubernetes CronJob.")