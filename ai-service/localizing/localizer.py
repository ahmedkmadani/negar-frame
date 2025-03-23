from .logger import setup_logging, get_logger
from .merging import CamInfoMerger
from .mapping import PointMapper
from .utils import simplify_pose


LOGGER = get_logger(__name__)


class PersonLocalizer(object):
    def __init__(self, cfg):
        self.cfg = cfg
        setup_logging(self.cfg.get("logging", {}))
        self.mapper = PointMapper(self.cfg.get("mapping", {}))
        self.merger = CamInfoMerger(self.cfg.get("merging", {}))

        LOGGER.info("PersonLocalizer initialized with configuration: %s", self.cfg)

    def __call__(self, cam_ids, detections):
        locations = self.localize(cam_ids, detections)
        local_measures = [cam_ids, detections, locations]
        persons_info = self.merger.merge(local_measures)
        return persons_info

    def localize(self, cam_ids, detections):
        locations = []
        for idx in range(len(detections)):
            cam_id = cam_ids[idx]
            cam_locations = []
            cam_persons_detection = detections[idx]
            poses = cam_persons_detection["keypoints"]
            confs = cam_persons_detection['confs']
            for _id, pose in enumerate(poses):
                conf = confs[_id]
                neck, hip, ankle = simplify_pose(pose, conf)
                if ankle:
                    msr_location = self.mapper.imap2(cam_id, ankle, Y=0)
                elif hip:
                    msr_location = self.mapper.imap2(cam_id, hip, Y=1000)
                elif neck:
                    msr_location = self.mapper.imap2(cam_id, neck, Y=1500)
                else:
                    msr_location = None
                msr_location = (msr_location[0], msr_location[2]) if msr_location else None
                cam_locations.append(msr_location)
            locations.append(cam_locations)
        return locations
