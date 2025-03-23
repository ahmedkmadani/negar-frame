from .logger import get_logger


LOGGER = get_logger(__name__)


def simplify_pose(pose, conf, conf_thresh=0.65):
    """
    This method extracts neck, hip, and ankle points
    """
    neck = ((pose[5] + pose[6]) / 2).tolist() if (conf[5] > conf_thresh and conf[6] > conf_thresh) else None
    hip = ((pose[11] + pose[12]) / 2).tolist() if (conf[11] > conf_thresh and conf[12] > conf_thresh) else None

    if (conf[15] > conf_thresh) and (conf[16] > conf_thresh):
        ankle = ((pose[15] + pose[16]) / 2).tolist()
    elif conf[15] > conf_thresh:
        ankle = pose[15].tolist()
    elif conf[16] > conf_thresh:
        ankle = pose[16].tolist()
    else:
        ankle = None

    return (neck, hip, ankle)
