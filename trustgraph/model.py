"""Bipartite message passing + node GRUs, with learned sender-trust gating.

Dense tensors are deliberate for the small initial graphs; PyG is not required.
"""
import torch
from torch import nn


class TrustGraph(nn.Module):
    def __init__(self, hidden=32, trust_aware=True):
        super().__init__()
        self.hidden = hidden
        self.trust_aware = trust_aware
        self.vehicle_encoder = nn.Sequential(nn.Linear(7, hidden), nn.ReLU())
        self.cell_encoder = nn.Sequential(nn.Linear(2, hidden), nn.ReLU())
        self.edge_encoder = nn.Sequential(nn.Linear(3, hidden), nn.ReLU())
        self.local_gru = nn.GRUCell(hidden, hidden)
        self.attack_head = nn.Linear(hidden, 1)
        self.vehicle_gru = nn.GRUCell(hidden * 2, hidden)
        self.cell_gru = nn.GRUCell(hidden * 2, hidden)
        self.risk_head = nn.Linear(hidden, 1)
        self.load_head = nn.Sequential(nn.Linear(hidden, 1), nn.Softplus())

    def forward(self, graph):
        vehicle, cell, edge = graph['vehicle'], graph['cell'], graph['edge']
        batch, steps, vehicles, _ = vehicle.shape
        cells = cell.shape[2]
        hv = vehicle.new_zeros(batch * vehicles, self.hidden)
        hc = vehicle.new_zeros(batch * cells, self.hidden)
        local = torch.zeros_like(hv)
        for t in range(steps):
            v = self.vehicle_encoder(vehicle[:, t])
            c = self.cell_encoder(cell[:, t])
            e = self.edge_encoder(edge[:, t])
            local = self.local_gru(v.reshape(-1, self.hidden), local)
            attack = self.attack_head(local).reshape(batch, vehicles)
            trust = 1 - torch.sigmoid(attack) if self.trust_aware else torch.ones_like(attack)
            mask = graph['edge_mask'][:, t, :, :, None]
            # Denominator uses observed degree, preserving attenuation even for one sender.
            messages = (v[:, :, None, :] + e) * trust[:, :, None, None] * mask
            to_cell = messages.sum(1) / mask.sum(1).clamp_min(1)
            hc = self.cell_gru(torch.cat([c, to_cell], -1).reshape(-1, 2 * self.hidden), hc)
            context = hc.reshape(batch, cells, self.hidden)
            to_vehicle = ((context[:, None, :, :] + e) * mask).sum(2) / mask.sum(2).clamp_min(1)
            hv = self.vehicle_gru(torch.cat([v, to_vehicle], -1).reshape(-1, 2 * self.hidden), hv)
        return {'risk_logits': self.risk_head(hv).reshape(batch, vehicles),
                'load': self.load_head(hc).reshape(batch, cells), 'attack_logits': attack}


def multitask_loss(prediction, target, class_weights=None):
    class_weights = class_weights or {'risk': 1., 'attack': 1.}
    risk = nn.functional.binary_cross_entropy_with_logits(prediction['risk_logits'], target['risk'], reduction='none',
                                                         pos_weight=prediction['risk_logits'].new_tensor(class_weights['risk']))
    risk = (risk * target['risk_mask']).sum() / target['risk_mask'].sum().clamp_min(1)
    load = nn.functional.mse_loss(prediction['load'], target['load'])
    attack = nn.functional.binary_cross_entropy_with_logits(prediction['attack_logits'], target['attack'],
                                                           pos_weight=prediction['attack_logits'].new_tensor(class_weights['attack']))
    return risk + load + attack
