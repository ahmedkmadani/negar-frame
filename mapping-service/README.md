# PersonLocalizer Module

The `PersonLocalizer` module is designed to process pose detection outputs (e.g., from YOLOv8-pose) and localize persons in a 3D scene across multiple cameras. It maps 2D image keypoints to 3D world coordinates on the x-z floor plane and merges detections from different cameras to track unique individuals.

This README guides you through integrating this module with your detection pipeline, including input requirements, configuration, and expected outputs.

## Features
- Localizes persons using ankle, hip, or neck keypoints with a fallback hierarchy
- Maps 2D image coordinates to 3D world coordinates (x-z plane)
- Merges multi-camera detections based on a minimum distance threshold
- Returns a structured dictionary with person IDs and per-camera detection data

## Prerequisites
- Python 3.8+
- NumPy
- PyYAML
- A detection module (e.g., YOLOv8-pose) providing keypoints, confidence scores, and bounding boxes
- Camera calibration data (for `PointMapper`)

## Installation
1. Unzip and copy this module into your project:
```bash
unzip person_localizer.zip -d <your-project-directory>
cd person_localizer
```
2. Install dependencies:
```bash
pip install requirements.txt
```

## Usage
### 1. Prepare Your Detection Output
Your detection module should provide a list of dictionaries, one per camera, with processed YOLOv8-pose outputs. Here's how to process them:
```python
import numpy as np

def yolov8pose_post_process(detections, threshold=0.75):
 result = []
 for res in detections:
     bconfs = res.boxes.conf
     boxes = res.boxes.xyxy.reshape(-1, 4)[bconfs > threshold]
     boxes = boxes.cpu().numpy().astype("int32")
     keypoints = res.keypoints.xy.reshape(-1, 17, 2)[bconfs > threshold]
     keypoints = keypoints.cpu().numpy().astype("int32")
     confs = res.keypoints.conf[bconfs > threshold] if res.keypoints.conf is not None else np.array([])
     confs = confs.cpu().numpy().reshape(-1, 17) if confs.size > 0 else np.array([]).reshape(-1, 17)
     result.append({"boxes": boxes, "keypoints": keypoints, "confs": confs})
 return result

# Example: Process detections from 3 cameras
cam_ids = [1, 2, 3]
raw_detections = [...]  # Your YOLOv8-pose outputs
processed_detections = yolov8pose_post_process(raw_detections)
```
### 2. Configure the Module
Create a `config.yaml` file with the following structure:
```yaml
localizing:
  logging:
    file: localizer.log
    debug: False

  mapping:
    0:
      rtcd_file: ./calibrations/home-mostafa/calibration/1_rtcd.yaml
      calibration_file: ./calibrations/IR-opencv/calibration.yaml
      image_points: ./calibrations/home-mostafa/calibration/1_img_pnts.npy
      physical_points: ./calibrations/home-mostafa/calibration/1_phys_pnts.npy
    1:
      rtcd_file: ./calibrations/home-mostafa/calibration/2_rtcd.yaml
      calibration_file: ./calibrations/IR-opencv/calibration.yaml
      image_points: ./calibrations/home-mostafa/calibration/2_img_pnts.npy
      physical_points: ./calibrations/home-mostafa/calibration/2_phys_pnts.npy

  merging:
    thresh: 200
```
- `logging`: Configures logging level and output file
- `mapping`: Defines camera calibration parameters for PointMapper (adjust based on your setup)
- `merging`: Sets the threshold for merging detections across cameras
### 3. Integrate PersonLocalizer
Use the module in your code:
```python
import yaml
from person_localizer import PersonLocalizer  # Adjust import path

# Load configuration
with open("config.yaml", 'r') as f:
    cfg = yaml.safe_load(f)

# Initialize localizer
localizer = PersonLocalizer(cfg.get("localizing", {}))

# Process detections
cam_ids = ["camera1", "camera2"]
detections = processed_detections  # From your detection module
persons_info = localizer(cam_ids, detections)

# Use the results
print(persons_info)
```

## Input Format
- **`cam_ids`**: List of camera identifiers (e.g., `["camera1", "camera2"]`)
- **`detections`**: List of dictionaries, one per camera, with:
  - `"boxes"`: NumPy array of shape `(N, 4)` with bounding box coordinates `[x_min, y_min, x_max, y_max]` (int32)
  - `"keypoints"`: NumPy array of shape `(N, 17, 2)` with 17 keypoints in `[x, y]` format (int32)
  - `"confs"`: NumPy array of shape `(N, 17)` with confidence scores for each keypoint (float32)
  - `N` is the number of detected persons in that camera's frame

Example:
```python
detections = [
    {"boxes": np.array([[100, 200, 150, 300]]), "keypoints": np.array([[[x1, y1], ..., [x17, y17]]]), "confs": np.array([[c1, ..., c17]])},
    {"boxes": np.array([[50, 60, 80, 90]]), "keypoints": np.array([[[x1, y1], ..., [x17, y17]]]), "confs": np.array([[c1, ..., c17]])}
]
```

## Output Format
The `persons_info` dictionary maps person IDs to their data across cameras:
- **Keys**: Unique person IDs (e.g., `1`, `2`)
- **Values**: Dictionary with:
  - Keys: Camera IDs (e.g., `"camera1"`, `"camera2"`)
  - Values: List `[msr_location, keypoints, confs, boxes]` where:
    - `msr_location`: Tuple `(x, z)` of floor plane coordinates (in mm) or `None`
    - `keypoints`: Original keypoints array for that person
    - `confs`: Original confidence array
    - `boxes`: Original bounding box array

Example:
```python
{
    1: {
        1: [(100, 200), array([...]), array([...]), array([[100, 200, 150, 300]])],
        2: [(102, 198), array([...]), array([...]), array([[50, 60, 80, 90]])]
    },
    2: {
        3: [(500, 300), array([...]), array([...]), array([[50, 60, 80, 90]])]
    }
}
```
