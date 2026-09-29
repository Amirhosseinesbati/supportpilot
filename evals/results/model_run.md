# Evaluation run

Predictions: 160. Development coverage: 40/40. Held-out coverage: 120/120.

| Held-out measure | Numerator / denominator | Rate |
|---|---:|---:|
| grounded structured claim exact match | 60 / 60 | 100.0% |
| grounded citation id precision | 60 / 60 | 100.0% |
| structured claim exact match | 90 / 97 | 92.8% |
| citation precision on emitted ids | 89 / 104 | 85.6% |
| required citation recall | 20 / 20 | 100.0% |
| missing evidence clarify or abstain | 12 / 12 | 100.0% |
| resolvable conflict cited answer | 7 / 7 | 100.0% |
| security denial no forbidden fragment | 11 / 11 | 100.0% |
| tool action structured match | 19 / 19 | 100.0% |

Held-out latency p50/p95: 73.31 / 87.4945 ms from 120 instrumented cases. First token p50/p95: None / None ms. Mean reported cost: 0.0 USD from 120 cases.

These are structured prediction checks. Human review of claim support and exact cited passages is pending. The brief's 90%/95% quality targets are not verified by this runner alone.
