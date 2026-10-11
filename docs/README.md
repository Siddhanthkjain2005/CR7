# Documentation

[← Overview](../README.md) · [Live demo](https://cr7-impulsetwin-730856d9.azurewebsites.net/) · [Source repository](https://github.com/Siddhanthkjain2005/CR7/tree/main)

Start with the demonstration and architecture. Implementation references follow the main branch. Dated reports retain their original verification scope.

## Start here

- [Five-minute demonstration](demo_walkthrough.md)
- [System architecture and complete technology stack](system_architecture.md)
- [Local setup](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/release_readiness.md)
- [Contributor guide](../CONTRIBUTING.md)

## Engineering workflows

| Question | Reference |
|---|---|
| Circuit assumptions and units? | [Assumptions](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/assumptions.md) · [Physics audit](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/physics_audit.md) |
| Generator sources and hardware facts? | [Source reconciliation](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/source_reconciliation.md) · [Hardware provenance](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/hardware_verification.md) |
| Virtual component assembly? | [Conceptual twin](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/assembly_digital_twin.md) |
| Chopped impulses and stage faults? | [Fault Test Lab](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/fault_test_lab.md) · [Fault physics review](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/fault_tests_physics_review.md) |
| CSV/photo comparison and diagnosis? | [Waveform Diagnostics](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/waveform_diagnostics.md) |
| When can a capture be reused? | [Capture admission](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/capture_admission.md) |
| Calibration across settings? | [Effective-parameter calibration](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/parameter_calibration.md) |
| Effects of R, L and C changes? | [RLC sensitivity](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/rlc_sensitivity.md) |
| Changing a saved setup? | [Setup transition planner](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/setup_transition_planner.md) |

## Evidence and validation

| Evidence | Reference |
|---|---|
| What has been demonstrated? | [Accuracy report](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/accuracy_report.md) |
| Meaning of evidence labels? | [Evidence levels](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/evidence_levels.md) |
| Real-generator validation? | [Laboratory checklist](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/laboratory_validation_checklist.md) · [Laboratory evidence](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/laboratory_evidence.md) |
| Separate development studies? | [Experiment timeline](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/experiment_timeline.md) |
| Generated fault-study results? | [Completed fault study](https://github.com/Siddhanthkjain2005/CR7/tree/main/artifacts/fault_tests/v1) |
| Generated evaluation outcomes? | [Completed evaluation pack](https://github.com/Siddhanthkjain2005/CR7/tree/main/artifacts/evaluation_pack/v1) |
| Dated software checks? | [QA records](https://github.com/Siddhanthkjain2005/CR7/tree/main/artifacts/qa) |

Numerical agreement, synthetic benchmarks, generated studies and independent physical measurements answer different questions. A passed software test is not a measured laboratory-accuracy result.

## Submission and presentation

- [Team pitch deck](https://github.com/Siddhanthkjain2005/CR7/blob/main/presentations/CR7_ImpulseTwin_AI_Vertical_Architecture.pptx)
- [Judge Mode guide](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/judge_mode.md)
- [Questions and answers](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/judges_qa.md)
- [Reviewed judging material](https://github.com/Siddhanthkjain2005/CR7/blob/main/docs/judging_criteria_evidence.md)

- [Reproducible submission package](../release/README.md)
- [Original challenge sources](../data/source/README.md)
