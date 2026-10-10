# Independent generated circuit fixtures

All 240cases are **independent_generated_simulation**, not laboratory measurements. CSV columns are time_us and voltage_kv. Complete assumptions/settings/split IDs are in parameter_manifest.json; continuous reference metrics, solver convergence and every failure are in reference_labels.json. These references use a separately implemented charge/flux integrator of the same assumed lumped topology as the production circuit.

The registered numerical comparison is complete; evaluation labels are now exposed. Do not reuse them as untouched outcomes for tuning or claim they repaired V1’s saved 5/6-versus-kNN benchmark. No workbook residual model was trained on these records. See docs/independent_simulation_results.md and artifacts/independent_simulation/v1/.
