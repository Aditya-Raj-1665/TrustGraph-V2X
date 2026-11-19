"""The acceptance reader must not confuse LTE attachment with NR handover."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'nr_verifier', Path(__file__).resolve().parents[1] / 'scripts/verify_nr_handover.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def test_only_nr_serving_cell_evidence_is_read(tmp_path):
    vector = tmp_path / 'result.vec'
    vector.write_text('''version 2
vector 1 Network.ue[0].cellularNic.rrc.connectionControl servingCell:vector ETV
vector 2 Network.ue[0].cellularNic.rrc.nrConnectionControl servingCell:vector ETV
vector 3 Network.ue[1].cellularNic.rrc.nrConnectionControl servingCell:vector ETV
1 0 0 99
2 0 0 1
3 0 0 8
2 123 17.5 2
''')
    assert verifier.serving_cells(vector) == [(0., 1), (17.5, 2)]


def test_unrelated_vectors_do_not_count_as_handover(tmp_path):
    vector = tmp_path / 'result.vec'
    vector.write_text('''version 2
vector 1 Network.ue[0].mobility speed:vector ETV
1 0 0 1
1 100 10 2
''')
    assert verifier.serving_cells(vector) == []
