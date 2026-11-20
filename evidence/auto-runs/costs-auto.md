# Receipts API costs (USD)

| Scenario | With segment cache | Without segment cache |
|---|---:|---:|
| This run (actual API usage) | $2.8196 | $2.8196 |
| Full dataset (1,740 articles, one day, three profile versions) | $26.5087 | $26.5087 |
| 10x (17,400 articles, one day, three profile versions) | $251.9624 | $251.9624 |
| Per listener per month at 10,000 listeners | $0.8273 | $7.6153 |
| 10,000 listeners per month | $8,273.0173 | $76,152.6473 |

Rates come from prices.yaml. Dataset preparation scales from 145 observed articles; three profile drafts are generated daily. The monthly model assumes 30 days, one briefing per listener per day, and an equal profile mix.
Segment reuse is a projection. Each voice and settings combination synthesizes its story segments once daily. Greetings and sign-offs are charged per listener; without reuse every listener incurs the full audio cost. The actual run uses the existing whole-briefing cache and is shown as observed in both columns.
