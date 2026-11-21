import argparse
from dataclasses import replace
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='TrustGraph-V2X research prototype')
    sub = parser.add_subparsers(dest='command', required=True)
    demo = sub.add_parser('demo', help='Generate toy data, train both models, and compare closed-loop policies')
    demo.add_argument('--output', default='outputs/demo')
    demo.add_argument('--config')
    demo.add_argument('--runs', type=int, default=12)
    demo.add_argument('--epochs', type=int)
    generate = sub.add_parser('generate', help='Generate explicitly synthetic radio data')
    generate.add_argument('--output', required=True)
    generate.add_argument('--config')
    generate.add_argument('--runs', type=int, default=12)
    train = sub.add_parser('train')
    train.add_argument('--data', required=True)
    train.add_argument('--output', required=True)
    train.add_argument('--baseline', action='store_true')
    train.add_argument('--epochs', type=int)
    compare = sub.add_parser('evaluate')
    compare.add_argument('--config', required=True)
    compare.add_argument('--baseline', required=True)
    compare.add_argument('--trust', required=True)
    compare.add_argument('--output', required=True)
    sumo = sub.add_parser('sumo', help='Build and run a real SUMO intersection, exporting mobility CSV')
    sumo.add_argument('--output', default='outputs/sumo')
    sumo.add_argument('--vehicles', type=int, default=20)
    sumo.add_argument('--duration', type=float, default=180)
    sumo.add_argument('--gui', action='store_true')
    predict = sub.add_parser('predict', help='Predict from the end of an observed NPZ run')
    predict.add_argument('--checkpoint', required=True)
    predict.add_argument('--observations', required=True)
    predict.add_argument('--output', required=True)
    service = sub.add_parser('serve', help='Serve the local inference API for a simulator adapter')
    service.add_argument('--checkpoint', required=True)
    service.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    from .config import Config
    if args.command == 'serve':
        from .service import serve
        serve(args.checkpoint, args.port)
        return
    if args.command == 'sumo':
        from .sumo import create_scenario, collect
        path = Path(args.output)
        config = create_scenario(path / 'scenario', args.vehicles)
        result = collect(config, path / 'mobility.csv', args.duration, args.gui)
    elif args.command == 'generate':
        from .simulation import generate_dataset
        result = generate_dataset(args.output, Config.load(args.config), args.runs)
    elif args.command == 'train':
        from .learning import train
        result = train(args.data, args.output, not args.baseline, args.epochs)
    elif args.command == 'evaluate':
        from .evaluation import compare
        result = compare(Config.load(args.config), args.output, args.baseline, args.trust)
    elif args.command == 'predict':
        import numpy as np
        from .learning import Predictor
        from .controller import choose_targets
        predictor = Predictor(args.checkpoint)
        with np.load(args.observations, allow_pickle=False) as file:
            data = dict(file)
        frames = [{k: v[t] for k, v in data.items() if k != 'vehicle_ids'} for t in range(len(data['time']))]
        p = predictor(frames)
        if p is None:
            raise ValueError('Not enough history')
        result = {k: v.tolist() for k, v in p.items()}
        result['targets'] = choose_targets(frames[-1], predictor.config, p).tolist()
        result['time'] = float(frames[-1]['time'])
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    else:
        from .simulation import generate_dataset
        from .learning import train
        from .evaluation import compare
        output = Path(args.output)
        config = Config.load(args.config)
        if args.epochs:
            config = replace(config, epochs=args.epochs)
        generate_dataset(output / 'dataset', config, args.runs)
        train(output / 'dataset', output / 'baseline', False)
        train(output / 'dataset', output / 'trustgraph', True)
        result = compare(config, output / 'evaluation', output / 'baseline/model.pt', output / 'trustgraph/model.pt')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
