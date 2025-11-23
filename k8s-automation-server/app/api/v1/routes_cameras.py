from fastapi import APIRouter, HTTPException
from kubernetes.client.rest import ApiException

# Import the model we just defined
from app.models.camera import CameraCreateRequest

# Import the functions from your Kubernetes manager
from app.core import k8s_manager

# Create a new router. This will be included in your main app.
router = APIRouter(
    prefix="/v1/cameras",  # All routes in this file start with /v1/cameras
    tags=["Cameras"]       # Groups these routes in the auto-docs
)


@router.post("/", status_code=201)
def create_new_camera(camera_request: CameraCreateRequest):
    """
    Adds a new camera to the system.
    
    This will create all necessary Kubernetes resources for it, such as:
    1. A real-time detection Deployment.
    2. A batch-processing CronJob.
    """
    try:
        # 1. Create the real-time Deployment
        deployment_result = k8s_manager.create_camera_deployment(
            camera_id=camera_request.camera_id,
            rtsp_url=camera_request.rtsp_url
        )

        # 2. Create the batch processing CronJob
        # We'll use a hardcoded service_id for this example
        service_id = "your-batch-service-id"  # You'd probably get this from the request
        
        cronjob_result = k8s_manager.create_camera_cronjob(
            camera_id=camera_request.camera_id,
            service_id=service_id
        )

        # 3. Return a success response
        return {
            "message": "Camera resources created successfully",
            "camera_id": camera_request.camera_id,
            "created_deployment": deployment_result.get("metadata", {}).get("name"),
            "created_cronjob": cronjob_result.get("metadata", {}).get("name")
        }

    except ApiException as e:
        # If the K8s API fails (e.g., resource already exists, bad auth)
        print(f"Kubernetes API Error: {e.status} - {e.reason}")
        raise HTTPException(
            status_code=e.status, 
            detail=f"Failed to create Kubernetes resource. Reason: {e.reason}"
        )
    except FileNotFoundError as e:
        # If the .yaml templates are missing
        print(f"Error: Missing template file: {e}")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: Missing Kubernetes template."
        )
    except Exception as e:
        # Catchall for other unexpected errors
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"An unexpected server error occurred: {e}"
        )


@router.delete("/{camera_id}", status_code=200)
def delete_camera(camera_id: str):
    """
    Deletes a camera and all its associated Kubernetes resources.
    """
    try:
        k8s_manager.delete_camera_resources(camera_id=camera_id)
        
        return {
            "message": f"Successfully deleted all resources for camera_id: {camera_id}"
        }
        
    except ApiException as e:
        print(f"Kubernetes API Error: {e.status} - {e.reason}")
        raise HTTPException(
            status_code=e.status, 
            detail=f"Failed to delete Kubernetes resource. Reason: {e.reason}"
        )
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"An unexpected server error occurred: {e}"
        )