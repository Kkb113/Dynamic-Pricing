# Phase 7 Pricing Rule Report

Pricing_Rules are loaded read-only. NULL scope values are wildcards, effective windows use `[EffectiveFrom, EffectiveTo)`, and priority/specificity semantics are selected from TRAIN reconciliation only.

Selected precedence: `P5_MAX_ABSOLUTE_CONSTRAINT_ADJUSTMENT_PRIORITY_DESC`. Percentage convention: `PERCENT_POINTS`.

The selected source-backed policy is the maximum absolute constraint adjustment from the frozen pre-rule recommendation, tied by higher numeric priority, specificity, and ascending rule ID; no-change rows use the deterministic P2 fallback. The complete P2 mismatch diagnostic is `artifacts/phase7/rule_precedence_mismatch_forensics.parquet`.

Precedence forensics: {
  "policy": "P2_PRIORITY_ASC_SPECIFICITY_DESC",
  "rows_evaluated": 24500,
  "mismatch_rows": 1609,
  "mismatch_rate": 0.0656734693877551,
  "status": "MISMATCHES_REPORTED"
}

Constraints use independent MinPrice, MaxPrice, minimum-margin, maximum-discount, and maximum-price-change bounds. Conflicting intervals never receive an automatic price.

Rule replay: {
  "validation": {
    "split": "validation",
    "status": "PASS",
    "blocker": null,
    "policy_used_for_diagnostic_replay": "P5_MAX_ABSOLUTE_CONSTRAINT_ADJUSTMENT_PRIORITY_DESC",
    "semantics_status": "PASS",
    "acceptance_threshold": 0.995,
    "historical_rule_id_replay": {
      "status": "PASS",
      "blocker": null,
      "metrics": {
        "rows": 5250,
        "exact_cent_match_rate": 0.9998095238095238,
        "absolute_delta_mean": 1.9047619047601723e-06,
        "absolute_delta_median": 0.0,
        "absolute_delta_p95": 0.0,
        "absolute_delta_max": 0.009999999999990905,
        "constrained_decision_count": 896,
        "constrained_decision_rate": 0.17066666666666666,
        "rule_violation_count": 0,
        "historical_rule_missing_count": 0
      },
      "policy": "HISTORICAL_PRICING_RULE_ID_DIRECT"
    },
    "resolver_replay": {
      "status": "PASS",
      "blocker": null,
      "policy": "P5_MAX_ABSOLUTE_CONSTRAINT_ADJUSTMENT_PRIORITY_DESC",
      "metrics": {
        "rows": 5250,
        "exact_cent_match_rate": 0.9998095238095238,
        "absolute_delta_mean": 1.9047619047601723e-06,
        "absolute_delta_median": 0.0,
        "absolute_delta_p95": 0.0,
        "absolute_delta_max": 0.009999999999990905,
        "constrained_decision_count": 896,
        "constrained_decision_rate": 0.17066666666666666,
        "rule_violation_count": 0,
        "historical_rule_missing_count": 0
      }
    },
    "metrics": {
      "rows": 5250,
      "exact_cent_match_rate": 0.9998095238095238,
      "absolute_delta_mean": 1.9047619047601723e-06,
      "absolute_delta_median": 0.0,
      "absolute_delta_p95": 0.0,
      "absolute_delta_max": 0.009999999999990905,
      "constrained_decision_count": 896,
      "constrained_decision_rate": 0.17066666666666666,
      "rule_violation_count": 0,
      "historical_rule_missing_count": 0
    },
    "reference_full_historical_constrained_rate": 0.173,
    "reference_historical_rule_violations": 0
  },
  "test": {
    "split": "test",
    "status": "PASS",
    "blocker": null,
    "policy_used_for_diagnostic_replay": "P5_MAX_ABSOLUTE_CONSTRAINT_ADJUSTMENT_PRIORITY_DESC",
    "semantics_status": "PASS",
    "acceptance_threshold": 0.995,
    "historical_rule_id_replay": {
      "status": "PASS",
      "blocker": null,
      "metrics": {
        "rows": 5250,
        "exact_cent_match_rate": 1.0,
        "absolute_delta_mean": 0.0,
        "absolute_delta_median": 0.0,
        "absolute_delta_p95": 0.0,
        "absolute_delta_max": 0.0,
        "constrained_decision_count": 886,
        "constrained_decision_rate": 0.16876190476190475,
        "rule_violation_count": 0,
        "historical_rule_missing_count": 0
      },
      "policy": "HISTORICAL_PRICING_RULE_ID_DIRECT"
    },
    "resolver_replay": {
      "status": "PASS",
      "blocker": null,
      "policy": "P5_MAX_ABSOLUTE_CONSTRAINT_ADJUSTMENT_PRIORITY_DESC",
      "metrics": {
        "rows": 5250,
        "exact_cent_match_rate": 1.0,
        "absolute_delta_mean": 0.0,
        "absolute_delta_median": 0.0,
        "absolute_delta_p95": 0.0,
        "absolute_delta_max": 0.0,
        "constrained_decision_count": 886,
        "constrained_decision_rate": 0.16876190476190475,
        "rule_violation_count": 0,
        "historical_rule_missing_count": 0
      }
    },
    "metrics": {
      "rows": 5250,
      "exact_cent_match_rate": 1.0,
      "absolute_delta_mean": 0.0,
      "absolute_delta_median": 0.0,
      "absolute_delta_p95": 0.0,
      "absolute_delta_max": 0.0,
      "constrained_decision_count": 886,
      "constrained_decision_rate": 0.16876190476190475,
      "rule_violation_count": 0,
      "historical_rule_missing_count": 0
    },
    "reference_full_historical_constrained_rate": 0.173,
    "reference_historical_rule_violations": 0
  },
  "train": {
    "split": "train",
    "status": "PASS",
    "blocker": null,
    "policy_used_for_diagnostic_replay": "P5_MAX_ABSOLUTE_CONSTRAINT_ADJUSTMENT_PRIORITY_DESC",
    "semantics_status": "PASS",
    "acceptance_threshold": 0.995,
    "historical_rule_id_replay": {
      "status": "PASS",
      "blocker": null,
      "metrics": {
        "rows": 24500,
        "exact_cent_match_rate": 1.0,
        "absolute_delta_mean": 0.0,
        "absolute_delta_median": 0.0,
        "absolute_delta_p95": 0.0,
        "absolute_delta_max": 0.0,
        "constrained_decision_count": 4373,
        "constrained_decision_rate": 0.17848979591836733,
        "rule_violation_count": 0,
        "historical_rule_missing_count": 0
      },
      "policy": "HISTORICAL_PRICING_RULE_ID_DIRECT"
    },
    "resolver_replay": {
      "status": "PASS",
      "blocker": null,
      "policy": "P5_MAX_ABSOLUTE_CONSTRAINT_ADJUSTMENT_PRIORITY_DESC",
      "metrics": {
        "rows": 24500,
        "exact_cent_match_rate": 1.0,
        "absolute_delta_mean": 0.0,
        "absolute_delta_median": 0.0,
        "absolute_delta_p95": 0.0,
        "absolute_delta_max": 0.0,
        "constrained_decision_count": 4373,
        "constrained_decision_rate": 0.17848979591836733,
        "rule_violation_count": 0,
        "historical_rule_missing_count": 0
      }
    },
    "metrics": {
      "rows": 24500,
      "exact_cent_match_rate": 1.0,
      "absolute_delta_mean": 0.0,
      "absolute_delta_median": 0.0,
      "absolute_delta_p95": 0.0,
      "absolute_delta_max": 0.0,
      "constrained_decision_count": 4373,
      "constrained_decision_rate": 0.17848979591836733,
      "rule_violation_count": 0,
      "historical_rule_missing_count": 0
    },
    "reference_full_historical_constrained_rate": 0.173,
    "reference_historical_rule_violations": 0
  }
}

Constraint impact: {}
