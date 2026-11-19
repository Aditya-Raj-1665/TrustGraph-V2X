from dataclasses import asdict
import json
from pathlib import Path
import random
import numpy as np
import torch
from torch.utils.data import DataLoader
from .config import Config
from .graphs import GraphSequences, build_graphs
from .model import TrustGraph, multitask_loss


def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)


def binary_metrics(y, p):
    y, p = np.asarray(y).reshape(-1).astype(bool), np.asarray(p).reshape(-1)
    if not len(y):
        return {'count': 0, 'precision': None, 'recall': None, 'f1': None, 'auroc': None}
    predicted = p >= .5
    tp, fp, fn = (predicted & y).sum(), (predicted & ~y).sum(), (~predicted & y).sum()
    precision, recall = float(tp / max(1, tp + fp)), float(tp / max(1, tp + fn))
    auc = None
    if y.any() and (~y).any():
        # Average ranks handle tied probabilities correctly.
        order = np.argsort(p)
        _, starts, counts = np.unique(p[order], return_index=True, return_counts=True)
        sorted_ranks = np.repeat(starts + (counts + 1) / 2, counts)
        ranks = np.empty(len(p), dtype=float)
        ranks[order] = sorted_ranks
        positives, negatives = int(y.sum()), int((~y).sum())
        auc = float((ranks[y].sum() - positives * (positives + 1) / 2) / (positives * negatives))
    return {'count': len(y), 'positive_count': int(y.sum()), 'precision': precision,
            'recall': recall, 'f1': 2 * precision * recall / max(1e-12, precision + recall), 'auroc': auc}


@torch.no_grad()
def evaluate(model, loader, class_weights=None):
    model.eval()
    collected = {k: [] for k in ['risk', 'risk_p', 'attack', 'attack_p', 'load', 'load_p']}
    total, n = 0., 0
    for graph, target in loader:
        prediction = model(graph)
        total += float(multitask_loss(prediction, target, class_weights)) * len(target['load'])
        n += len(target['load'])
        mask = target['risk_mask'].bool()
        for key in ['risk', 'attack']:
            metric_mask = mask if key == 'risk' else target.get('vehicle_mask')
            values = target[key] if metric_mask is None else target[key][metric_mask.bool()]
            p = torch.sigmoid(prediction[key + '_logits'])
            p = p if metric_mask is None else p[metric_mask.bool()]
            collected[key].append(values.numpy().ravel())
            collected[key + '_p'].append(p.numpy().ravel())
        collected['load'].append(target['load'].numpy().ravel())
        collected['load_p'].append(prediction['load'].numpy().ravel())
    data = {k: np.concatenate(v) for k, v in collected.items()}
    error = data['load_p'] - data['load']
    return {'loss': total / n, 'link': binary_metrics(data['risk'], data['risk_p']),
            'attack': binary_metrics(data['attack'], data['attack_p']),
            'load': {'mae': float(np.abs(error).mean()), 'rmse': float(np.sqrt(np.square(error).mean()))}}


def train(dataset, output, trust_aware=True, epochs=None):
    dataset, output = Path(dataset), Path(output)
    config = Config.load(dataset / 'config.json')
    if epochs is not None and epochs < 1:
        raise ValueError('epochs must be positive')
    seed_everything(config.seed)
    sets = {name: GraphSequences(dataset, name) for name in ['train', 'validation', 'test']}
    assert not (sets['train'].run_ids & sets['test'].run_ids or sets['train'].run_ids & sets['validation'].run_ids or sets['validation'].run_ids & sets['test'].run_ids)
    class_weights = {}
    for key in ['risk', 'attack']:
        labels = torch.cat([target[key][target['risk_mask'].bool()] if key == 'risk' else target[key]
                            for _, target in sets['train']])
        positives = float(labels.sum())
        class_weights[key] = min(20., max(1., (len(labels) - positives) / positives)) if positives else 1.
    loaders = {name: DataLoader(value, batch_size=config.batch_size, shuffle=name == 'train') for name, value in sets.items()}
    model = TrustGraph(config.hidden, trust_aware)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    output.mkdir(parents=True, exist_ok=True)
    best, history = float('inf'), []
    for epoch in range(epochs or config.epochs):
        model.train()
        loss_total = 0.
        for graph, target in loaders['train']:
            optimizer.zero_grad()
            loss = multitask_loss(model(graph), target, class_weights)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.)
            optimizer.step()
            loss_total += float(loss.detach()) * len(target['load'])
        validation = evaluate(model, loaders['validation'], class_weights)
        row = {'epoch': epoch + 1, 'train_loss': loss_total / len(sets['train']), 'validation_loss': validation['loss']}
        history.append(row)
        print(json.dumps(row), flush=True)
        if validation['loss'] < best:
            best = validation['loss']
            torch.save({'state_dict': model.state_dict(), 'config': asdict(config),
                        'trust_aware': trust_aware, 'schema_version': 1, 'class_weights': class_weights,
                        'source': 'toy-radio-NOT-Simu5G'}, output / 'model.pt')
    checkpoint = torch.load(output / 'model.pt', map_location='cpu', weights_only=True)
    model.load_state_dict(checkpoint['state_dict'])
    report = {'source': 'toy-radio-NOT-Simu5G', 'trust_aware': trust_aware,
              'history': history, 'test': evaluate(model, loaders['test'], class_weights), 'class_weights': class_weights,
              'splits': {k: sorted(v.run_ids) for k, v in sets.items()},
              'sequences': {k: len(v) for k, v in sets.items()}}
    (output / 'metrics.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


class Predictor:
    def __init__(self, checkpoint):
        seed_everything(0)
        saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
        if saved.get('schema_version') != 1:
            raise ValueError('Unsupported checkpoint schema')
        self.config = Config(**saved['config'])
        self.model = TrustGraph(self.config.hidden, saved['trust_aware'])
        self.model.load_state_dict(saved['state_dict'])
        self.model.eval()

    @torch.no_grad()
    def __call__(self, frames):
        if len(frames) < self.config.history:
            return None
        frames = frames[-self.config.history:]
        observed = {k: np.stack([f[k] for f in frames]) for k in frames[0] if k != 'vehicle_ids'}
        graph = {k: torch.from_numpy(v).unsqueeze(0) for k, v in build_graphs(observed, self.config.dt).items()}
        p = self.model(graph)
        return {'risk': torch.sigmoid(p['risk_logits'])[0].numpy(), 'load': p['load'][0].numpy(),
                'attack_probability': torch.sigmoid(p['attack_logits'])[0].numpy()}
