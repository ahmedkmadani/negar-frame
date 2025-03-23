import numpy as np

from localizing.logger import get_logger


LOGGER = get_logger(__name__)


def min_euclidean_squared_distance(global_msr_info, local_msr_info, global_ids, local_ids):
    ccost = np.zeros((len(global_ids), len(local_ids)))
    for i, g_id in enumerate(global_ids):
        for j, l_id in enumerate(local_ids):
            cam_ids = list(global_msr_info[g_id].keys())
            g_locations = np.array([global_msr_info[g_id][cam_id][0] for cam_id in cam_ids])
            l_location = local_msr_info[l_id][0]
            min_distance = np.min(np.linalg.norm(g_locations - l_location, axis=1))
            ccost[i, j] = min_distance
    return ccost


def greedy_threshold_match(cost, row_ids, col_ids, matched_thresh):
    cost_matrix = cost.copy()
    unmatched_rows = set(row_ids)
    unmatched_cols = set(col_ids)
    matches = []
    while True:
        min_value = np.min(cost_matrix)
        if min_value > matched_thresh:
            break
        row, col = np.unravel_index(np.argmin(cost_matrix), cost_matrix.shape)
        matches.append((row_ids[row], col_ids[col]))
        unmatched_rows.discard(row_ids[row])
        unmatched_cols.discard(col_ids[col])
        cost_matrix[row, :] = np.inf
        cost_matrix[:, col] = np.inf
    return matches, list(unmatched_rows), list(unmatched_cols)
