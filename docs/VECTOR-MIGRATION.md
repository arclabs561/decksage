# Vector artifact migration

DeckSage is moving its retrieval readers away from Gensim's Python-specific
`KeyedVectors` serialization. Gensim is in stable maintenance mode, not
announced as deprecated. This migration reduces runtime coupling while keeping
the existing models and their legacy artifacts available for rollback.

The portable v1 artifact is an uncompressed NumPy `.npz` containing ordered
Unicode names, a float matrix, and a format version. Loading disables pickle
and checks dimensions, unique names, finite vectors, and nonzero finite norms.
The reader implements exact cosine retrieval for named cards. Equal-score
ties use input order; that may differ from the legacy implementation. This
format is not an ANN index or a trainable Word2Vec model.

Convert a trusted legacy file into a **new** path:

```sh
uv run --extra embeddings python scripts/data/convert_legacy_vectors.py \
  data/embeddings/magic_v7_spectral_mu35.wv data/embeddings/magic_v7_spectral_mu35.npz
```

The converter uses Gensim and its pickle-based loader for the source; only
convert trusted artifacts. Keep the source and its possible sidecars. An
existing output is refused. Point `EMBEDDINGS_PATH_MAGIC` at the new `.npz`
to opt in; reverting to the old `.wv` path restores the previous reader. The
API and the two evaluation readers support explicit `.npz` paths. New
MetaPath2Vec training output uses `.npz` and refuses to overwrite an existing
run; use a distinct `--output-suffix` for each run. Other readers and writers
still require migration. Conversion does not retrain embeddings.

NumPy is already a project dependency and provides exact search at current
dataset sizes. [Faiss](https://faiss.ai/index.html) is an option if measured
retrieval needs justify an index; inner product equals cosine only after
normalization. [Safetensors](https://huggingface.co/docs/safetensors/en/index)
is a safe tensor format worth considering for larger models, but name mapping
and the reader contract remain necessary. Neither replaces Gensim's training
algorithms. [PyG Node2Vec](https://pytorch-geometric.readthedocs.io/en/latest/tutorial/shallow_node_embeddings.html)
can train graph embeddings, but its sampler and objective must be evaluated
as a new model, not assumed equivalent to prior Gensim runs.
