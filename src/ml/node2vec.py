from fastnode2vec import Graph, Node2Vec
import csv
from itertools import islice
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('infile')
    parser.add_argument('-o', '--outfile', default='vectors.kv')
    parser.add_argument('-l', '--limit', default=None, type=int)
    parser.add_argument('-e', '--epochs', default=100)
    args = parser.parse_args()

    edges = iter_edges(args.infile, limit=args.limit)
    graph = Graph(edges, False, True)
    model = Node2Vec(
        graph,
        dim=128,
        walk_length=100,
        context=4,
        workers=-1,
        p=1.0,
        q=1.0,
    )
    model.train(epochs=args.epochs)
    model.wv.save(args.outfile)

def iter_edges(infile, limit=None):
    with open(infile) as f:
        r = csv.reader(f)
        for row in islice(r, 1, limit):
            n, m, count_set, count_multiset = row
            _, _ = count_set, count_multiset
            yield (n, m, int(count_set))


if __name__ == '__main__':
    main()
