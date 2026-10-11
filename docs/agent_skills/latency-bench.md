name: latency-bench
triggers: latency, p50, p95, threads, affinity, soak, load, rss, memory, concurrency, throughput
- Fresh process per run; `intra_op_num_threads` 1 and 2; limit CPU affinity to 2 cores and state how.
- Exclude warm-up, report cold start separately; at least 100 runs; p50/p95/p99 and peak RSS.
- End-to-end per document type, not only detectors. Say what machine it ran on; a laptop is not the deployment server.
- Soak 30 min as a background job (no polling); fail on memory growth over 10% after warm-up or any 5xx at 4 concurrent clients.
