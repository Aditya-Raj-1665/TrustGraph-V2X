"""Serving-link risk plus observed candidate radio quality and predicted load."""
import numpy as np


def choose_targets(frame, config, prediction=None, load_aware=False, explain=False):
    serving = np.asarray(frame['serving'], dtype=int)
    sinr = np.asarray(frame['sinr'])
    load = np.asarray(frame['load']).copy()
    targets = serving.copy()
    reserved = np.bincount(serving, minlength=len(load)).astype(float)
    decisions = []
    for v, current in enumerate(serving):
        detail = {'vehicle': v, 'serving': int(current), 'target': int(current),
                  'mode': 'load_aware' if load_aware else 'reactive', 'reason': 'No eligible target improves the score enough',
                  'certainty': None}
        decisions.append(detail)
        if frame['since_handover'][v] < config.dwell_seconds:
            detail['reason'] = 'Minimum dwell time after previous handover'
            continue
        use_ai = prediction is not None
        if use_ai:
            risk = float(prediction['risk'][v])
            future_load = np.asarray(prediction['load'])
            confidence = abs(2 * risk - 1)  # Uncalibrated certainty heuristic, not calibrated confidence.
            use_ai = bool(np.isfinite(risk) and np.isfinite(future_load).all()
                          and confidence >= config.confidence_threshold)
            detail['certainty'] = float(confidence) if np.isfinite(confidence) else None
            detail['mode'] = 'model' if use_ai else 'reactive_fallback'
        if use_ai:
            score = sinr[v] - 6 * (future_load + reserved / config.cell_capacity - load)
        elif load_aware:
            score = sinr[v] - 6 * reserved / config.cell_capacity
        else:
            score = sinr[v].copy()
        # Candidate reachability comes from measured SINR, not a serving-only predictor.
        score = np.where(sinr[v] >= config.bad_sinr, score, -np.inf)
        # Avoid sending vehicles into a full target, but permit escape from a failed link.
        full = reserved + 1 > config.cell_capacity
        if sinr[v, current] >= config.bad_sinr:
            score[full & (np.arange(len(load)) != current)] = -np.inf
        best = int(np.argmax(score))
        if best == current or not np.isfinite(score[best]):
            continue
        current_score = (sinr[v, current] - 6 * (future_load[current] + reserved[current] / config.cell_capacity - load[current])
                         if use_ai else sinr[v, current] - (6 * reserved[current] / config.cell_capacity if load_aware else 0))
        margin = config.handover_margin
        if use_ai and risk >= config.risk_threshold:
            margin = 0.5
        if score[best] > current_score + margin:
            targets[v] = best
            reserved[current] -= 1
            reserved[best] += 1
            detail['target'] = best
            detail['reason'] = ('Predicted risk lowers the switching margin' if use_ai and risk >= config.risk_threshold
                                else 'Eligible target exceeds the switching margin')
        detail['required_margin'] = float(margin)
    return (targets, decisions) if explain else targets
