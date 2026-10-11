name: pytest-hardening
triggers: pytest, conftest, flaky, fixture, coverage, hypothesis, matrix, fail-safe, invariant, regression test
- Verify tools with `pip show`. Dev-only deps go in `requirements-dev.txt`.
- Invariant FS matrix: parametrise failure x input x flag; assert outcome in {REVIEW, REJECT-with-reason, explicit error}, never CLEAR.
- Property tests: parsers never raise on arbitrary text; checksum repair false-accept rate on 10,000 random strings is measured and reported.
- Every bug fix ships with a test that fails before the fix (run it on the old code first).
- Run the full suite three times; a test that flips is a finding. Never skip, xfail or loosen assertions.
- Coverage: no exclusions added to reach a number.
