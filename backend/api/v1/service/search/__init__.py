"""search service package.

intentionally empty: importing the package must NOT eagerly pull in the
aggregator (or any resource service), so that the leaf `primitives` module
stays independently importable and free of circular dependencies. import the
aggregator directly via `api.v1.service.search.aggregator`.
"""
