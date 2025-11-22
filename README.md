# 👁️ Argus: Distributed Computer Vision Orchestrator

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg) ![Kubernetes](https://img.shields.io/badge/Kubernetes-Native-326ce5.svg) ![FastAPI](https://img.shields.io/badge/FastAPI-High%20Performance-009688.svg) ![License](https://img.shields.io/badge/license-MIT-green)

**Argus** is a cloud-native orchestration platform designed to manage, scale, and deploy Computer Vision (CV) pipelines at the edge. 

Unlike traditional static deployments, Argus treats cameras as dynamic resources. It leverages the **Kubernetes API** to programmatically spin up real-time detection pods and batch processing jobs on demand, allowing for infinite horizontal scaling across edge nodes.

## 🏗️ System Architecture

Argus operates on a **Manager-Worker** architecture. The Manager (API) talks to the Kubernetes Control Plane to schedule Workers (Detection Pods) that bind to specific RTSP streams.

```mermaid
graph TD
    Client["Web/Mobile Client"] -->|REST API| Manager["Argus Manager (FastAPI)"]
    
    subgraph K8s_Cluster ["Kubernetes Cluster"]
        Manager -->|"K8s Client"| ControlPlane["K8s Control Plane"]
        
        ControlPlane -->|Spawns| PodA["📷 Detection Worker A"]
        ControlPlane -->|Spawns| PodB["📷 Detection Worker B"]
        ControlPlane -->|Spawns| JobC["⚙️ Batch CronJob"]
        
        PodA -->|RTSP| Cam1(("Camera 1"))
        PodB -->|RTSP| Cam2(("Camera 2"))
        
        PodA -->|"Inference Data"| DB[("MongoDB / Timescale")]
    end
