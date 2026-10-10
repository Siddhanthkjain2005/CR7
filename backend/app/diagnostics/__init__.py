"""Waveform Diagnostics: compare a recorded waveform with the circuit prediction and
look for physically meaningful explanations of any mismatch.

The feature is additive. It reads saved runs, uses the existing equivalent-circuit
solver, metric definitions, ratings and admission rules, and writes its own
versioned records. Nothing here changes a saved run, a trial, a model or a
calibration. Image-derived samples never enter calibration or accuracy workflows.
"""
VERSION = 'waveform-diagnostics-v1'
