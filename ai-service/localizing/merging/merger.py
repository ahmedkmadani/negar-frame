from .utils import min_euclidean_squared_distance, greedy_threshold_match
from localizing.logger import get_logger


LOGGER = get_logger(__name__)


class CamInfoMerger():
    def __init__(self, cfg):
        """
        Initialize the GLocalizer with configuration.
        :param cfg: Configuration dictionary containing mapping and other settings.
        """
        self.cfg = cfg
        self.loc_merge_thresh = self.cfg.get("thresh", 200)

        LOGGER.info("CamInfoMerger Initialized Successfully")

    def merge(self, local_measures):
        cam_ids, detections, locations = local_measures

        cam_indexes = sorted(range(len(detections)), key=lambda index: len(detections[index]["boxes"]), reverse=True)

        global_msr_info = {}
        current_global_id = 0

        for cam_idx in cam_indexes:

            local_msr_info = {}

            # Extract camera measurements
            cam_id = cam_ids[cam_idx]
            cam_persons_detection = detections[cam_idx]
            cam_persons_location = locations[cam_idx]

            poses = cam_persons_detection["keypoints"]
            confs = cam_persons_detection['confs']
            boxes = cam_persons_detection['boxes']

            # Create Local Measure Information
            for _id, pose in enumerate(poses):
                conf = confs[_id]
                box = boxes[_id]
                msr_location = cam_persons_location[_id]
                if msr_location:
                    local_msr_info[_id] = [msr_location, pose, conf, box]

            # Step 3: Compare measurements from different cameras and merge detections
            global_ids = list(global_msr_info.keys())
            local_ids = list(local_msr_info.keys())

            # Location Matching (use a threshold to merge close detections from different cameras)
            if global_ids and local_ids:
                ccost = min_euclidean_squared_distance(global_msr_info, local_msr_info, global_ids, local_ids)
                matches, _, u_l_ids = greedy_threshold_match(ccost, global_ids, local_ids, self.loc_merge_thresh)
            else:
                matches, u_l_ids = [], local_ids

            # Update existing global measrures with matched detections
            for g_id, l_id in matches:
                global_msr_info[g_id][cam_id] = local_msr_info[l_id]

            # Create new global measrures for unmatched detections
            for l_id in u_l_ids:
                g_id = current_global_id
                global_msr_info[g_id] = {cam_id: local_msr_info[l_id]}
                current_global_id += 1
        
        return global_msr_info
