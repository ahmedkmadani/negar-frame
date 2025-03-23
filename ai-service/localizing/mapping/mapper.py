from os.path import isfile
import numpy as np
import yaml
import cv2

from .utils import f_dist_undist, f_undistortion
from localizing.logger import get_logger


LOGGER = get_logger(__name__)


class PointMapper(object):
    def __init__(self, cfg):
        self.mapping_data = {}

        for cam_id in cfg.keys():
            config = cfg.get(cam_id, None)
            cam_id = f"camera{cam_id}"

            if config:
                self.mapping_data[cam_id] = {}
                rtcd_file_path = config.get('rtcd_file', "")
                calib_file_path = config.get('calibration_file', "")

                if isfile(rtcd_file_path):
                    with open(rtcd_file_path) as f:
                        rtcd_data = yaml.safe_load(f)
                    mtx = np.array(rtcd_data.get('camera_matrix'))
                    dist = np.array(rtcd_data.get('dist_coeff'))
                    rvec = np.array(rtcd_data.get('rvec'))
                    tvec = np.array(rtcd_data.get('tvec'))
                    self.mapping_data[cam_id]["measurements"] = [mtx, dist, rvec, tvec, None, None]

                elif isfile(calib_file_path):
                    with open(config['calibration_file']) as f:
                        calib_data = yaml.safe_load(f)
                    mtx = np.array(calib_data.get('camera_matrix'))
                    dist = np.array(calib_data.get('dist_coeff'))
                    imagePoints = np.load(config['image_points']).astype('float32')
                    physicalPoints = np.load(config['physical_points']).astype('float32')
                    length = min(len(imagePoints), len(physicalPoints))
                    imagePoints, physicalPoints = imagePoints[:length], physicalPoints[:length]
                    self.mapping_data[cam_id]["measurements"] = [mtx, dist, None, None, imagePoints, physicalPoints]

                else:
                    LOGGER.error(f"rtcd_file or calibration_file not found for {cam_id}", exc_info=True)

                self.calibrate(cam_id)
                # self.refine(cam_id)
            else:
                self.mapping_data[cam_id] = None

        LOGGER.info(f"PointMapper Initialized Successfully with {len(self.mapping_data.keys())} cameras")

    def calibrate(self, cam_id):
        mtx, dist, rvec, tvec, imagePoints, physicalPoints = self.mapping_data[cam_id]["measurements"]
        if tvec is None or rvec is None:
            ret, rvec, tvec = cv2.solvePnP(physicalPoints, imagePoints, mtx, dist)
            assert ret, "error in calculating tvec and rvec"
        R, _ = cv2.Rodrigues(rvec)
        P = mtx @ np.hstack((R, tvec))
        P1 = np.concatenate((P[:, 0:1], P[:, 2:]), axis=1)
        self.mapping_data[cam_id]['I'] = [mtx, dist, rvec, tvec]
        self.mapping_data[cam_id]['P'] = P
        self.mapping_data[cam_id]['P1'] = P1
        self.mapping_data[cam_id]['P2'] = P[:, 1:2]
        self.mapping_data[cam_id]['Q'] = np.linalg.inv(P1)

    def refine(self, cam_id, num_iters=20, max_error=2, beta=0.9):
        for itr in range(num_iters):
            ret = True
            print(itr)
            new_pp = []
            for idx, pp in enumerate(self.mapping_data[cam_id]["measurements"][3]):
                point = self.mapping_data[cam_id]["measurements"][2][idx]
                ppp = self.imap2(cam_id, point, Y=pp[1])
                error = np.linalg.norm(pp - ppp)
                if error > max_error:
                    new_pp.append(beta * pp + (1.0 - beta) * np.array(ppp))
                    ret = False
                else:
                    new_pp.append(pp)
            self.mapping_data[cam_id]["measurements"][3] = np.array(new_pp)
            self.calibrate(cam_id)
            if ret:
                return

    def map(self, cam_id, physical_point):
        mtx, dist, rvec, tvec = self.mapping_data[cam_id]['I']
        center = cv2.projectPoints(np.array([[physical_point]], dtype="float32"), rvec, tvec, mtx, dist)
        center = center[0].reshape(2,).astype("int32")
        return center

    def imap(self, cam_id, point):
        mtx, dist = self.mapping_data[cam_id]['I'][:2]
        # to remove distortion
        xd, yd = point[0], point[1]
        xdu, ydu = f_undistortion(xd, yd, mtx, dist)
        x, y = xdu, ydu
        for _ in range(5):
            xdudu, ydudu = f_dist_undist(x, y, mtx, dist)
            x, y = xdu + x - xdudu, ydu + y - ydudu
        pixelPoint = (x, y)
        # to calculate the location
        physicalPoint = self.mapping_data[cam_id]['Q'] @ np.append(pixelPoint, 1).reshape(3, 1)
        x, z = (physicalPoint[:2] / physicalPoint[2]).reshape(-1).astype("int32")
        return (x, z)

    def height(self, cam_id, loc, point):
        mtx, dist = self.mapping_data[cam_id]['I'][:2]
        # to remove distortion
        xd, yd = point[0], point[1]
        xdu, ydu = f_undistortion(xd, yd, mtx, dist)
        x, y = xdu, ydu
        for _ in range(5):
            xdudu, ydudu = f_dist_undist(x, y, mtx, dist)
            x, y = xdu + x - xdudu, ydu + y - ydudu
        point = (x, y)
        # to calculate the height
        P3 = np.array([[point[0], point[1], 1]]).T
        L = np.array([loc[0], loc[1], 1])
        b = -1 * self.mapping_data[cam_id]['P1'] @ L
        A = np.concatenate((self.mapping_data[cam_id]['P2'], P3), axis=1)
        x = np.linalg.inv(A.T @ A) @ (A.T @ b)
        height = x[0]
        return height

    def imap2(self, cam_id, point, X=None, Y=None, Z=None):
        mtx, dist = self.mapping_data[cam_id]['I'][:2]
        assert X == None or Y == None or Z == None, "problem can't be solved!!!"
        if X and Y and Z:
            return [X, Y, Z]

        result = [None, None, None]

        # to remove distortion
        xd, yd = point[0], point[1]
        xdu, ydu = f_undistortion(xd, yd, mtx, dist)
        x, y = xdu, ydu
        for _ in range(5):
            xdudu, ydudu = f_dist_undist(x, y, mtx, dist)
            x, y = xdu + x - xdudu, ydu + y - ydudu
        point = (x, y)

        P = self.mapping_data[cam_id]['P']
        P1 = np.array([[point[0], point[1], 1]]).T
        P2 = P[:, 3:4]
        b = np.array([1.0])

        idxs = []
        if Z != None:
            result[2] = Z
            P2 = np.concatenate((P[:, 2:3], P2), axis=1)
            b = np. concatenate(([Z], b))
        else:
            idxs.append(2)
            P1 = np.concatenate((P[:, 2:3], P1), axis=1)
        if Y != None:
            result[1] = Y
            P2 = np.concatenate((P[:, 1:2], P2), axis=1)
            b = np. concatenate(([Y], b))
        else:
            idxs.append(1)
            P1 = np.concatenate((P[:, 1:2], P1), axis=1)
        if X != None:
            result[0] = X
            P2 = np.concatenate((P[:, 0:1], P2), axis=1)
            b = np. concatenate(([X], b))
        else:
            idxs.append(0)
            P1 = np.concatenate((P[:, 0:1], P1), axis=1)

        if P1.shape[0] == P1.shape[1]:
            x = -1 * np.linalg.inv(P1) @ P2 @ b
        else:
            x = -1 * np.linalg.inv(P1.T @ P1) @ P1.T @ P2 @ b
        
        x = x.astype("int32")
        idxs.reverse()
        for i, idx in enumerate(idxs):
            result[idx] = x[i]
        return result
