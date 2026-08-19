# Phase 8 Business Economics Report

## Scenario framing

`S0_HISTORICAL_APPLIED` is the factual prediction at the observed historical
price. `S1` through `S4` are model-implied expected units, revenue, and gross
profit; they are scenario estimates, not observed outcomes.

## Scenario summaries

{
  "S0_HISTORICAL_APPLIED": {
    "scenario": "S0_HISTORICAL_APPLIED",
    "label": "historical factual prediction at observed price",
    "rows": 5250,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1225.461176694419,
    "aggregate_expected_revenue": 184788.02956532539,
    "aggregate_expected_gross_profit": 79250.104728012,
    "gross_margin_rate": 0.4288703381622232,
    "mean_price": 150.7057180952381,
    "median_price": 132.675,
    "price_increase_rate": 0.0,
    "price_decrease_rate": 0.0,
    "hold_rate": 1.0,
    "mean_price_change_pct": 0.0,
    "median_price_change_pct": 0.0,
    "factual_or_counterfactual": "factual_prediction"
  },
  "S1_CURRENT_PRICE": {
    "scenario": "S1_CURRENT_PRICE",
    "label": "model-implied scenario estimate",
    "rows": 5250,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1209.293336386254,
    "aggregate_expected_revenue": 178069.79657353478,
    "aggregate_expected_gross_profit": 73956.0129525392,
    "gross_margin_rate": 0.41532036524789706,
    "mean_price": 148.11187619047618,
    "median_price": 129.18,
    "price_increase_rate": 0.304952380952381,
    "price_decrease_rate": 0.5481904761904762,
    "hold_rate": 0.14685714285714285,
    "mean_price_change_pct": -0.01817860193346408,
    "median_price_change_pct": -0.01700511380499054,
    "factual_or_counterfactual": "counterfactual_model_implied"
  },
  "S2_PHASE6_MODEL_OPTIMAL": {
    "scenario": "S2_PHASE6_MODEL_OPTIMAL",
    "label": "model-implied scenario estimate",
    "rows": 5250,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1158.8265285696234,
    "aggregate_expected_revenue": 186997.14279058683,
    "aggregate_expected_gross_profit": 87601.06025970248,
    "gross_margin_rate": 0.46846202542145043,
    "mean_price": 162.6966457142857,
    "median_price": 142.1,
    "price_increase_rate": 0.8636190476190476,
    "price_decrease_rate": 0.13428571428571429,
    "hold_rate": 0.0020952380952380953,
    "mean_price_change_pct": 0.07892394713202426,
    "median_price_change_pct": 0.07467536721626919,
    "factual_or_counterfactual": "counterfactual_model_implied"
  },
  "S3_PHASE7_FINAL_AUTOMATIC": {
    "scenario": "S3_PHASE7_FINAL_AUTOMATIC",
    "label": "model-implied scenario estimate",
    "rows": 5175,
    "missing_price_rows": 75,
    "aggregate_expected_units": 1145.2622360745602,
    "aggregate_expected_revenue": 183014.3161701461,
    "aggregate_expected_gross_profit": 84966.10135086284,
    "gross_margin_rate": 0.4642593165874025,
    "mean_price": 161.21689661835748,
    "median_price": 140.32,
    "price_increase_rate": 0.7694685990338165,
    "price_decrease_rate": 0.22743961352657005,
    "hold_rate": 0.0030917874396135265,
    "mean_price_change_pct": 0.07101919974198002,
    "median_price_change_pct": 0.06679519165343599,
    "factual_or_counterfactual": "counterfactual_model_implied"
  },
  "S4_PHASE7_WITH_HISTORICAL_FALLBACK": {
    "scenario": "S4_PHASE7_WITH_HISTORICAL_FALLBACK",
    "label": "model-implied scenario estimate",
    "rows": 5250,
    "missing_price_rows": 0,
    "aggregate_expected_units": 1163.7939080018582,
    "aggregate_expected_revenue": 186263.71929527677,
    "aggregate_expected_gross_profit": 86400.47319711858,
    "gross_margin_rate": 0.46386098980527285,
    "mean_price": 161.3194304761905,
    "median_price": 140.58,
    "price_increase_rate": 0.7584761904761905,
    "price_decrease_rate": 0.2241904761904762,
    "hold_rate": 0.017333333333333333,
    "mean_price_change_pct": 0.07000463974566602,
    "median_price_change_pct": 0.06366339195255057,
    "factual_or_counterfactual": "counterfactual_model_implied"
  }
}

## Model-implied opportunity

{
  "S1_CURRENT_PRICE": {
    "expected_units_delta": -16.16784030816507,
    "expected_units_delta_pct": -0.013193270105689102,
    "expected_revenue_delta": -6718.232991790603,
    "expected_revenue_delta_pct": -0.03635642962151726,
    "expected_gross_profit_delta": -5294.0917754728,
    "expected_gross_profit_delta_pct": -0.0668023316012292
  },
  "S2_PHASE6_MODEL_OPTIMAL": {
    "expected_units_delta": -66.6346481247956,
    "expected_units_delta_pct": -0.05437516046370159,
    "expected_revenue_delta": 2209.113225261448,
    "expected_revenue_delta_pct": 0.011954850270647497,
    "expected_gross_profit_delta": 8350.955531690488,
    "expected_gross_profit_delta_pct": 0.10537469395594039
  },
  "S3_PHASE7_FINAL_AUTOMATIC": {
    "expected_units_delta": -80.19894061985883,
    "expected_units_delta_pct": -0.06544388524505435,
    "expected_revenue_delta": -1773.7133951792785,
    "expected_revenue_delta_pct": -0.00959863796021616,
    "expected_gross_profit_delta": 5715.996622850842,
    "expected_gross_profit_delta_pct": 0.0721260450376471
  },
  "S4_PHASE7_WITH_HISTORICAL_FALLBACK": {
    "expected_units_delta": -61.66726869256081,
    "expected_units_delta_pct": -0.05032168286138873,
    "expected_revenue_delta": 1475.6897299513803,
    "expected_revenue_delta_pct": 0.007985851320686882,
    "expected_gross_profit_delta": 7150.368469106586,
    "expected_gross_profit_delta_pct": 0.09022535040990544
  }
}

The primary opportunity metric is the Phase 7 model-implied expected gross
profit delta versus the historical-price model-implied scenario.

## Pricing behavior and robustness

{
  "price_distribution": {
    "rows": 5175,
    "price_increase_rate": 0.9943961352657005,
    "price_decrease_rate": 0.00463768115942029,
    "hold_rate": 0.000966183574879227,
    "mean_price_change_pct": 0.09100111515245198,
    "median_price_change_pct": 0.09998472738380078,
    "p05_price_change_pct": 0.07495324413753407,
    "p25_price_change_pct": 0.07502145922746789,
    "p75_price_change_pct": 0.10001068136339919,
    "p95_price_change_pct": 0.10005108013975597
  },
  "boundary_rates": {
    "tolerance": 0.005,
    "rows": 5250,
    "phase6_upper_grid_boundary_rate": 0.9756190476190476,
    "phase6_lower_grid_boundary_rate": 0.00019047619047619048,
    "phase7_upper_grid_boundary_rate": 0.6892753623188406,
    "phase7_lower_grid_boundary_rate": 0.0001932367149758454,
    "phase7_any_grid_boundary_rate": 0.6894685990338164,
    "phase7_automatic_rows": 5175
  },
  "neighbor_fragility": {
    "rows": 3567,
    "mean_gp_advantage": 0.6271238134445573,
    "median_gp_advantage": 0.5082451471843683,
    "p05_gp_advantage": 0.08480222776073763,
    "p25_gp_advantage": 0.25452628938152255,
    "p75_gp_advantage": 0.8433037191674373,
    "p95_gp_advantage": 1.6590832121460246,
    "mean_relative_gp_advantage": 0.04017070047615495,
    "median_relative_gp_advantage": 0.04036603503149194,
    "share_relative_below_0_1pct": 0.0,
    "share_relative_below_0_5pct": 0.005326604990187833,
    "share_relative_at_least_1pct": 0.9823380992430614,
    "warning_codes": []
  },
  "boundary_augmentation": {
    "in_support_unsimulated_boundaries": 3195,
    "boundaries_scored": 3195,
    "decision_rows_with_scored_boundaries": 1711,
    "decisions_where_augmented_optimum_differs": 1490,
    "change_rate": 0.8708357685563998,
    "aggregate_model_implied_gp_delta": 974.9540889714186,
    "relative_aggregate_gp_delta": 0.035584990155558174,
    "mean_price_delta": 3.532817066043249,
    "warning_codes": [
      "COARSE_GRID_VALUE_WARNING"
    ],
    "blockers": [
      "MATERIAL_GRID_GRANULARITY_GAP"
    ]
  }
}

Aggressive price movement, upper-grid concentration, and near-tied neighbors
are warnings that describe the frozen policy; no price or model was retuned.

## Governance cost and current inventory

Phase 6 versus Phase 7 economics quantify the model-implied expected profit
change associated with business constraints. Current inventory metrics are
reported separately from historical outcomes.
