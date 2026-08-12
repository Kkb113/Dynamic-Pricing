# Phase 1 Feature Policy

## Core features

`AppliedPrice`, `CurrentPrice`, stable product/store/region context, season/channel, and point-in-time aggregates whose timestamps do not exceed `DecisionTime`.

## Conditional features

ProductID, StoreID, non-PII customer commercial context, preferences, and pre-decision behavior require live coverage, sparsity, fairness, and synthetic-proxy review.

## Join-only columns

PricingDecisionID, SessionID, CustomerID, PromotionID, PricingRuleID, and other identifiers used only to derive context.

## Optimization-only inputs

Current inventory, cost, pricing rules, and commercial constraints.

## Prohibited features

All synthetic optimizer/model outputs, post-outcome fields, direct PII, historicalized snapshot inventory, future observations, and invented expiry/perishable fields.
