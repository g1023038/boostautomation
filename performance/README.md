# performance

JMeter `.jmx` test plans live here, run in non-GUI mode on a dedicated runner
(not every PR -- triggered separately, since perf runs are heavier and noisier
than functional tests).

Pending: no workflow wired up yet. Plan is `.jtl` results -> converted to
JUnit XML -> `scripts/publish_results.py` (same path functional results take)
to import into Xray as a Performance Test Execution, plus a summary pushed to
Confluence directly (no native JMeter-to-Jira integration exists, confirmed).
