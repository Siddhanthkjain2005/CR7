"use client";
import { Data, fmt } from "@/lib/api";
import { Badge } from "./ui";

export function NominalEvidence({ value }: { value: unknown }) {
  return typeof value === "boolean" ? (
    <Badge tone={value ? "green" : "red"}>{value ? "Within limits" : "Limit exceeded"}</Badge>
  ) : (
    <span className="evidence-unrecorded">Not recorded</span>
  );
}

export function AgreementEvidence({ agreement, solver }: { agreement?: Data | null; solver?: string }) {
  if (solver === "circuit")
    return (
      <div className="evidence-cell">
        <Badge>Circuit only</Badge>
        <small>No second model in this run</small>
      </div>
    );
  if (typeof agreement?.both_nominal_pass !== "boolean") return <span className="evidence-unrecorded">Not recorded</span>;
  return (
    <div className="evidence-cell">
      <Badge tone={agreement.both_nominal_pass ? "green" : "red"}>{agreement.both_nominal_pass ? "Both within limits" : "Agreement failed"}</Badge>
      <small>{agreement.required ? "Required in search" : "Independent cross-check"}</small>
    </div>
  );
}

export function VerificationEvidence({ verification }: { verification?: Data | null }) {
  if (!verification) return <span className="evidence-unrecorded">Not recorded</span>;
  return (
    <div className="evidence-cell">
      <strong className={verification.all_checks_pass ? "positive" : "negative"}>
        {fmt(verification.passed, 0)} / {fmt(verification.total, 0)} <span>scenarios</span>
      </strong>
      <small>
        {verification.all_checks_pass
          ? "All checked limits pass"
          : verification.passed === verification.total
            ? "Nominal limit exceeded"
            : "Scenario limit exceeded"}{" "}
        · {verification.models_checked?.length === 2 ? "both models" : "single model"}
      </small>
    </div>
  );
}

export function candidateEvidence(candidate: Data, inputs: Data): Data {
  const primary = candidate.compliance?.nominal_pass;
  const cross = candidate.circuit_crosscheck?.compliance?.nominal_pass;
  const agreement =
    candidate.model_agreement ??
    (typeof primary === "boolean" && typeof cross === "boolean"
      ? {
          both_nominal_pass: primary && cross,
          required: Boolean(inputs.require_model_agreement),
        }
      : null);
  return {
    primary_nominal_pass: typeof primary === "boolean" ? primary : null,
    agreement,
    verification: candidate.verification
      ? { ...candidate.verification, minimum_margin_fraction: candidate.verification.worst_case?.minimum_margin_fraction }
      : null,
  };
}
