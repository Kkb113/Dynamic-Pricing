# Phase 1 Feature Policy

## Core features

`AppliedPrice`, `CurrentPrice`, stable product/store/region context, season/channel, and point-in-time aggregates whose timestamps do not exceed `DecisionTime`.

Feature admission is deny-by-default. Phase 2 must use the explicit allowlist in `audit.leakage_analysis`; a column is not permitted merely because it is absent from a prohibited list.

## Conditional features

ProductID, StoreID, non-PII customer commercial context, preferences, and pre-decision behavior require live coverage, sparsity, fairness, and synthetic-proxy review.

## Join-only columns

PricingDecisionID, SessionID, CustomerID, PromotionID, PricingRuleID, and other identifiers used only to derive context.

## Derivation-only sources

Raw sales quantities/amounts, recommendation responses, browsing/cart/search events, price history, competitor observations, promotions, ratings, wishlists, holidays, and weather may only contribute through point-in-time derived features. Date-only sales orders require `OrderDate < CAST(DecisionTime AS date)`, excluding the entire decision day.

## Optimization-only inputs

Current inventory, cost, pricing rules, and commercial constraints.

## Prohibited features

All synthetic optimizer/model outputs, post-outcome fields, direct PII, historicalized snapshot inventory, future observations, and invented expiry/perishable fields.
