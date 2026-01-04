import argparse

from gensim import models
from gensim.models.callbacks import CallbackAny2Vec
from tqdm import tqdm

from .corpus import CollectionsCorpus


class Callback(CallbackAny2Vec):
    def __init__(self, epochs):
        self.pbar = tqdm(total=epochs)

    def on_epoch_end(self, model):
        self.pbar.update()

    def close(self):
        self.pbar.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("infile")
    parser.add_argument("--outfile", default="vectors.kv")
    parser.add_argument("--limit", default=None, type=int)
    parser.add_argument("--epochs", default=200)
    args = parser.parse_args()

    callback = Callback(args.epochs)
    corpus = CollectionsCorpus(args.infile, limit=args.limit)
    model = models.Word2Vec(
        sentences=corpus,
        vector_size=128,
        window=60,
        negative=100,
        min_count=1,
        workers=-1,
        epochs=args.epochs,
        shrink_windows=False,
        callbacks=[callback],
    )
    callback.close()
    model.wv.save(args.outfile)


if __name__ == "__main__":
    main()
