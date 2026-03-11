import argparse

from gensim import models
from gensim.models.callbacks import CallbackAny2Vec
from tqdm import tqdm

from ..training.corpus import CollectionsCorpus


class Callback(CallbackAny2Vec):
    def __init__(self, epochs):
        self.pbar = tqdm(total=epochs)

    def on_epoch_end(self, model):
        self.pbar.update()

    def close(self):
        self.pbar.close()


def main():
    """Train Word2Vec on a card co-occurrence corpus.

    Hyperparameter rationale:
        ns_exponent: Controls the negative sampling distribution. Default 0.75
            is the NLP standard (Mikolov et al.). For recommendation and
            co-occurrence domains, values like -0.5 may perform better by
            up-sampling rare items (Caselles-Dupre et al. 2018).
        window=60: Large window because deck card order is arbitrary -- the
            entire deck is effectively the context for each card.
        negative=100: High negative sample count to compensate for large
            vocabularies (10K-25K cards per game).
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("infile")
    parser.add_argument("--outfile", default="vectors.kv")
    parser.add_argument("--limit", default=None, type=int)
    parser.add_argument("--epochs", default=200)
    parser.add_argument(
        "--ns-exponent",
        type=float,
        default=0.75,
        help="Negative sampling exponent (default: 0.75). Try -0.5 for recommendation domains.",
    )
    args = parser.parse_args()

    callback = Callback(args.epochs)
    corpus = CollectionsCorpus(args.infile, limit=args.limit)
    model = models.Word2Vec(
        sentences=corpus,
        vector_size=128,
        window=60,
        negative=100,
        ns_exponent=args.ns_exponent,
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
