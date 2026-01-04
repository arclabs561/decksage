similar card prediction

- API: `GET /v1/cards/{name}/similar` or `POST /v1/similar` (use_case: substitute|synergy|meta)
- Methods: `embedding`, `jaccard`, `jaccard_faceted` (if attributes loaded), `fusion` (auto or tuned weights)
- See: `src/ml/fusion.py`, `src/ml/similarity_methods.py`, `src/ml/api.py`

- Graph view (synergy/meta): build co-occurrence graph \(G=(V,E)\) from tournament decks. Let \(N(u)\) be neighbors of \(u\). Jaccard similarity:
  \[ J(u,v) = \frac{|N(u) \cap N(v)|}{|N(u) \cup N(v)|} \] with land filtering and optional facet restriction.
- Embedding view (substitutes): learn \(\phi: V \to \mathbb{R}^d\) (Node2Vec). Score \(s_e(u,v)=\cos(\phi(u),\phi(v))\), mapped to \([0,1]\) via \((s+1)/2\).
- Functional facet (roles): tag map \(T: V \to 2^{\mathcal{R}}\). Tag similarity \(J_{tag}(u,v)=\frac{|T(u)\cap T(v)|}{|T(u)\cup T(v)|}\).
- Faceted Jaccard: restrict candidate set by a facet \(f\) (e.g., type overlap, equal CMC). Compute \(J(u,v)\) only for \(v\in C_f(u)\).
- Late fusion (default): with weights \(w_e,w_j,w_f\) (normalized), candidate pool \(C=\bigcup\) top-\(n\) from each modality, final score:
  \[ s(u,v)=w_e\,s_e(u,v)+w_j\,J(u,v)+w_f\,J_{tag}(u,v). \]
- Motivation: co-occurrence captures meta-specific synergy; embeddings generalize substitutes beyond immediate neighbors; tags enforce role consistency. Fusion improves P@10 vs any single signal.

deck completion action space

- Suggest additions: `POST /v1/deck/suggest_actions` (supports `budget_max`, `coverage_weight`)
- Complete deck: `POST /v1/deck/complete` (greedy; optional price/tags hooks)
- Apply patch: `POST /v1/deck/apply_patch` (atomic; validated against game rules)
- See: `src/ml/deck_completion.py`, `src/ml/deck_patch.py`, `src/ml/validators/models.py`

- State: a deck is a vector \(x\in \mathbb{N}^{|V|}\) over cards with game constraints (size, partitions, copy limits). Optional budget: prices \(p\), \(p^\top x \le B\).
- Objective (informal): maximize a monotone submodular-style utility \(F(x)\) combining (i) similarity-based quality, (ii) functional coverage, (iii) optional curve/price heuristics, subject to constraints.
- Greedy step used: pick \(c\in C\) maximizing marginal gain \(\Delta F(c\mid x)\); apply atomic patch if still valid. Coverage term uses tag set gain \(\Delta_{cov}(c)=|T(x\cup\{c\})|-|T(x)|\), giving diminishing returns and good greedy behavior.
- Action space (atomic): add/remove/replace/move/set_format/set_archetype, applied transactionally and validated per game rules.

More detail: `README.md` (Quick Start, architecture) and `ENRICHMENT_GUIDE.md`.
