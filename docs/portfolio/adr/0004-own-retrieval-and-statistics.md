# 0004: Our Own BM25, Embedder and Statistics

*Status: accepted.*

## Context

The knowledge bases are small (tens of sections). The platform must run without a GPU and without a network. Each number in a report must have a method that the author can explain.

## Decision

- Retrieval: our own BM25, a hashing embedder and a fusion of the two. A freshness filter removes superseded sections.
- Statistics: our own Wilson intervals, case-level intervals, the paired bootstrap, the exact sign test and the Holm correction.
- More statistics: pass^k, the rule of three, power calculations, the Newcombe interval and a Bernoulli CUSUM. SciPy gives only the Gaussian distribution.
- Each method has a docstring that tells when it applies.

## Alternatives

- **A vector database and a hosted embedding model.** This adds a service and a cost. On a small knowledge base, it does not change the results.
- **A statistics library with many functions.** The methods are short. With our own code, a reviewer can see each assumption.

## Results

- The full test suite runs in less than one minute on a laptop.
- A real deployment with a large knowledge base can add a different retriever. The retriever interface is small.
