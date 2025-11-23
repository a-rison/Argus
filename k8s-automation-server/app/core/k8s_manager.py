import os
import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# --- Setup: Find Template Directory ---
# This line finds the root directory of your project (k8s-automation-server)
# It assumes k8s_manager.py is in k8s-automation-server/app/core/
try:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    TEMPLATE_DIR = os.path.join(BASE_DIR, "kubernetes_templates")
    if not os.path.exists(TEMPLATE_DIR):
        raise FileNotFoundError("Template directory not found")
except Exception:
    # Fallback for different execution environments
    TEMPLATE_DIR = os.path.join(os.getcwd(), "kubernetes_templates")


# --- Setup: Kubernetes API Connection ---
try:
    # 1. Try to load config from *inside* the cluster
    # This is for when your server is a pod in Kubernetes
    config.load_incluster_config()
    print("Loaded in-cluster Kubernetes config.")
except config.ConfigException:
    try:
        # 2. Load config from your local kubeconfig file
        # This is for running the server locally for development
        config.load_kube_config()
        print("Loaded local kubeconfig.")
    except config.ConfigException:
        raise Exception("Could not configure Kubernetes client. Make sure you have a valid kubeconfig or are running in-cluster.")

# 3. Create API client instances
# We need AppsV1Api for Deployments
apps_v1_api = client.AppsV1Api()
# We need BatchV1Api for CronJobs
batch_v1_api = client.BatchV1Api()
# We need CoreV1Api for Services, ConfigMaps, etc.
core_v1_api = client.CoreV1Api()


# --- Private Helper Function ---
def _load_yaml_template(template_name: str) -> dict:
    """Loads a YAML template from the kubernetes_templates directory."""
    template_path = os.path.join(TEMPLATE_DIR, template_name)
    if not os.path.exists(template_path):
        print(f"Template directory searched: {TEMPLATE_DIR}")
        raise FileNotFoundError(f"Template file not found: {template_path}")
    
    with open(template_path, 'r') as f:
        # Use safe_load to avoid security risks
        return yaml.safe_load(f)

# --- Public Functions (to be called by your API routes) ---

def create_camera_deployment(camera_id: str, rtsp_url: str, namespace: str = "default") -> dict:
    """
    Creates a new Deployment for a camera's real-time detection pod.
    """
    print(f"Attempting to create deployment for camera: {camera_id}")
    try:
        # 1. Load the template from file
        deployment_body = _load_yaml_template("detection_deployment.yaml")

        # 2. Modify the template with camera-specific data
        resource_name = f"camera-detection-{camera_id}"

        # Set the main name and label for the Deployment
        deployment_body["metadata"]["name"] = resource_name
        deployment_body["metadata"]["labels"]["app"] = resource_name
        deployment_body["metadata"]["labels"]["camera_id"] = camera_id

        # Set the pod's label (so a Service can find it)
        deployment_body["spec"]["template"]["metadata"]["labels"]["app"] = resource_name

        # Find the container and set its environment variables
        # This assumes the first container is the one we want to modify
        container = deployment_body["spec"]["template"]["spec"]["containers"][0]
        
        # Add env vars to a new list or extend existing one
        env_vars = container.get("env", [])
        env_vars.append({"name": "RTSP_URL", "value": rtsp_url})
        env_vars.append({"name": "CAMERA_ID", "value": camera_id})
        container["env"] = env_vars

        # 3. Create the resource in Kubernetes
        api_response = apps_v1_api.create_namespaced_deployment(
            body=deployment_body,
            namespace=namespace
        )
        print(f"Deployment '{api_response.metadata.name}' created successfully.")
        return api_response.to_dict()

    except ApiException as e:
        print(f"K8s API Error creating deployment {resource_name}: {e.status} - {e.reason}")
        # Re-raise or return a specific error message
        raise e
    except Exception as e:
        print(f"An unexpected error occurred in create_camera_deployment: {e}")
        raise e


def create_camera_cronjob(camera_id: str, service_id: str, namespace: str = "default") -> dict:
    """
    Creates a new CronJob for a camera's batch processing service.
    """
    print(f"Attempting to create cronjob for camera: {camera_id}, service: {service_id}")
    try:
        # 1. Load the template
        cronjob_body = _load_yaml_template("batch_cronjob.yaml")

        # 2. Modify the template
        resource_name = f"batch-service-{service_id}-cam-{camera_id}"
        
        cronjob_body["metadata"]["name"] = resource_name
        cronjob_body["metadata"]["labels"]["camera_id"] = camera_id
        cronjob_body["metadata"]["labels"]["service_id"] = service_id

        # Get the container to modify
        container = cronjob_body["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
        
        # Add camera/service IDs as environment variables (often cleaner than args)
        env_vars = container.get("env", [])
        env_vars.append({"name": "CAMERA_ID", "value": camera_id})
        env_vars.append({"name": "SERVICE_ID", "value": service_id})
        container["env"] = env_vars

        # 3. Create the resource
        api_response = batch_v1_api.create_namespaced_cron_job(
            body=cronjob_body,
            namespace=namespace
        )
        print(f"CronJob '{api_response.metadata.name}' created successfully.")
        return api_response.to_dict()

    except ApiException as e:
        print(f"K8s API Error creating cronjob {resource_name}: {e.status} - {e.reason}")
        raise e
    except Exception as e:
        print(f"An unexpected error occurred in create_camera_cronjob: {e}")
        raise e


def delete_camera_resources(camera_id: str, namespace: str = "default"):
    """
    Deletes all resources (Deployments, CronJobs) associated with a camera_id.
    
    This is a simplified version. A robust way uses 'label selectors'.
    """
    print(f"Attempting to delete all resources for camera: {camera_id}")
    
    # This uses a label selector to find all resources tagged with this camera_id
    label_selector = f"camera_id={camera_id}"
    
    try:
        # Delete Deployments
        apps_v1_api.delete_collection_namespaced_deployment(
            namespace=namespace,
            label_selector=label_selector
        )
        print(f"Deleted Deployments with label: {label_selector}")
    except ApiException as e:
        print(f"Error deleting deployments: {e}")

    try:
        # Delete CronJobs
        batch_v1_api.delete_collection_namespaced_cron_job(
            namespace=namespace,
            label_selector=label_selector
        )
        print(f"Deleted CronJobs with label: {label_selector}")
    except ApiException as e:
        print(f"Error deleting cronjobs: {e}")
        
    # You would also delete Services, ConfigMaps, etc. here
    
    return True