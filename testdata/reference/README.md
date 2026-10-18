# testdata/reference

Versioned, non-sensitive test fixtures (payload templates, device/browser lists,
reference records). Changes go through a normal PR, same as test scripts.

Lookup convention: scripts resolve a fixture by `(key, environment)` -- see
`sample_user.json` for the shape. No secrets or real credentials belong here;
those live in GitHub Environment Secrets, referenced by name only.

The stateful piece (a pool of test users that gets allocated/released per run
so parallel LambdaTest jobs don't collide) isn't built yet -- start with a
static pool sized to your actual parallelism once that's known.
