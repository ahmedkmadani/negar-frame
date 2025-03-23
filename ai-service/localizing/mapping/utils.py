from localizing.logger import get_logger


LOGGER = get_logger(__name__)


def f_distortion(x, y, mtx, dist):
    cx, cy, fx, fy = mtx[0, 2], mtx[1, 2], mtx[0, 0], mtx[1, 1]
    k1, k2, p1, p2, k3 = dist[0]
    xn = (x - cx) / fx
    yn = (y - cy) / fy
    r2 = xn ** 2 + yn ** 2
    coeff = (1 + k1 * r2 + k2 * r2 ** 2 + k3 * r2 ** 3)
    xd = xn * coeff * fx + cx
    yd = yn * coeff * fy + cy
    return (xd, yd)


def f_undistortion(xd, yd, mtx, dist):
    cx, cy, fx, fy = mtx[0, 2], mtx[1, 2], mtx[0, 0], mtx[1, 1]
    k1, k2, p1, p2, k3 = dist[0]
    xn = (xd - cx) / fx
    yn = (yd - cy) / fy
    r2 = xn ** 2 + yn ** 2
    coeff = (1 + k1 * r2 + k2 * r2 ** 2 + k3 * r2 ** 3)
    x = xn / coeff * fx + cx
    y = yn / coeff * fy + cy
    return (x, y)

def f_dist_undist(x, y, mtx, dist):
    xd, yd = f_distortion(x, y, mtx, dist)
    x, y = f_undistortion(xd, yd, mtx, dist)
    return (x, y)
