import type { ReactElement, ReactNode } from "react";
import type { PricingChatResponse, Scenario } from "../types/contracts";
import { JsonViewer } from "./JsonViewer";
import { MarkdownAnswer } from "./MarkdownAnswer";

const money = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const decimal = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

function currency(value: number | null | undefined): string {
  return value == null ? "—" : `${money.format(value)} source units`;
}

function number(value: number | null | undefined): string {
  return value == null ? "—" : decimal.format(value);
}

function percentage(value: number | null | undefined): string {
  if (value == null) return "—";
  const normalized = Math.abs(value) <= 1 ? value * 100 : value;
  return `${decimal.format(normalized)}%`;
}

function words(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .replace(/phase\s*[0-9]+/gi, "")
    .replace(/guardrail/gi, "rule")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
    .replace(/^./, (letter) => letter.toUpperCase());
}

function businessRule(value: string | null | undefined): string {
  if (!value) return "Standard pricing rule";
  const channelRule = value.match(/^channel\s*\|\s*(.+)$/i);
  return channelRule ? `${words(channelRule[1])} channel pricing rule` : words(value);
}

function scenarioName(scenario: Scenario): string {
  const compact = scenario.scenario.replace(/[\s_-]/g, "").toLowerCase();
  if (compact.includes("historical") || compact.includes("appliedprice")) return "Previous price";
  if (compact === "currentprice" || compact.includes("currentprice")) return "Current price";
  if (compact.includes("finalrecommended") || compact.includes("phase7")) return "Final recommendation";
  if (compact.includes("modeloptimal") || compact.includes("phase6")) return "Model recommendation";
  return words(scenario.scenario);
}

function Section({ title, children }: { title: string; children: ReactNode }): ReactElement {
  return <section className="business-section"><h4>{title}</h4>{children}</section>;
}

export function BusinessResponse({ response, question = "" }: { response: PricingChatResponse; question?: string }): ReactElement {
  const data = response.authoritative;
  const recommendation = data.recommendations.length === 1 ? data.recommendations[0] : undefined;
  const recommendationPortfolio = data.recommendations.length > 1 ? data.recommendations : [];
  const performance = data.model_performance;
  const bestRevenue = data.scenario_comparisons.reduce<Scenario | null>((best, item) => item.expected_revenue != null && (best?.expected_revenue == null || item.expected_revenue > best.expected_revenue) ? item : best, null);
  const bestProfit = data.scenario_comparisons.reduce<Scenario | null>((best, item) => item.expected_gross_profit != null && (best?.expected_gross_profit == null || item.expected_gross_profit > best.expected_gross_profit) ? item : best, null);
  const hasBusinessData = Boolean(data.recommendations.length || data.scenario_comparisons.length || data.inventory_insights.length || performance || data.business_rule || data.capabilities);
  const narrative = response.answer;

  return (
    <div className="business-response">
      <section className="narrative-card" aria-label="Pricing assistant narrative">
        <MarkdownAnswer content={narrative} />
      </section>

      {recommendation && (
        <>
          <p className="evidence-heading"><strong>Pricing evidence</strong><span>Model results supporting this recommendation</span></p>
          <div className="metric-grid" aria-label="Recommendation summary">
            <div><span>Current price</span><strong>{currency(recommendation.current_price)}</strong></div>
            <div><span>Recommended price</span><strong>{currency(recommendation.final_recommended_price)}</strong></div>
            <div><span>Expected revenue</span><strong>{currency(recommendation.expected_revenue)}</strong></div>
            <div><span>Expected gross profit</span><strong>{currency(recommendation.expected_gross_profit)}</strong></div>
          </div>

          <Section title="Decision details">
            <dl className="detail-grid">
              {recommendation.channel && <><dt>Channel</dt><dd>{words(recommendation.channel)}</dd></>}
              <dt>Business rule</dt><dd>{businessRule(recommendation.rule_name ?? recommendation.pricing_rule_id)}</dd>
              <dt>Review status</dt><dd>{recommendation.manual_review_required ? "Manual review required" : "No manual review required"}</dd>
            </dl>
          </Section>
        </>
      )}

      {recommendationPortfolio.length > 0 && (
        <details className="evidence-disclosure">
          <summary><span><strong>Supporting recommendation sample</strong><small>View five representative recommendations; identifiers remain in technical details only</small></span><span aria-hidden="true">⌄</span></summary>
          <div className="evidence-disclosure-body"><div className="table-scroll"><table className="business-table portfolio-table">
            <thead><tr><th>Channel</th><th>Current price</th><th>Recommended price</th><th>Expected revenue</th><th>Expected gross profit</th><th>Action</th><th>Review</th></tr></thead>
            <tbody>{recommendationPortfolio.slice(0, 5).map((item, index) => <tr key={`${item.decision_id}-${index}`}><td>{words(item.channel)}</td><td>{currency(item.current_price)}</td><td>{currency(item.final_recommended_price)}</td><td>{currency(item.expected_revenue)}</td><td>{currency(item.expected_gross_profit)}</td><td>{words(item.final_action)}</td><td>{item.manual_review_required ? "Required" : "Not required"}</td></tr>)}</tbody>
          </table></div></div>
        </details>
      )}

      {data.scenario_comparisons.length > 0 && (
        <Section title={recommendation ? "Scenario comparison" : "Price scenario comparison"}>
          {!recommendation && <p className="section-summary">{bestRevenue && bestProfit && bestRevenue.scenario === bestProfit.scenario ? `${scenarioName(bestRevenue)} produces the strongest expected revenue and gross profit among the available options.` : "The strongest revenue and gross-profit outcomes occur under different pricing options; compare the trade-offs below."}</p>}
          <div className="table-scroll">
            <table className="business-table">
              <thead><tr><th>Scenario</th><th>Price</th><th>Expected demand</th><th>Revenue</th><th>Gross profit</th><th>Margin</th><th>Status</th></tr></thead>
              <tbody>{data.scenario_comparisons.map((scenario, index) => (
                <tr key={`${scenario.scenario}-${index}`}>
                  <td><strong>{scenarioName(scenario)}</strong></td>
                  <td>{currency(scenario.candidate_price)}</td>
                  <td>{number(scenario.expected_units)}</td>
                  <td>{currency(scenario.expected_revenue)}</td>
                  <td>{currency(scenario.expected_gross_profit)}</td>
                  <td>{percentage(scenario.candidate_margin_pct)}</td>
                  <td><span className={`decision-status ${scenario.business_rule_compliance === false ? "review" : "ready"}`}>{scenario.business_rule_compliance === false ? "Review" : "Eligible"}</span></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </Section>
      )}

      {data.inventory_insights.length > 0 && (
        <details className="evidence-disclosure">
          <summary><span><strong>Supporting inventory records</strong><small>View five representative records from {data.inventory_insights.length} returned opportunities</small></span><span aria-hidden="true">⌄</span></summary>
          <div className="evidence-disclosure-body"><div className="table-scroll"><table className="business-table">
            <thead><tr><th>Decision</th><th>Product</th><th>Store</th><th>Available</th><th>Stock status</th><th>Recommended price</th><th>Action</th></tr></thead>
            <tbody>{data.inventory_insights.slice(0, 5).map((item) => <tr key={item.decision_id}><td><strong>{item.decision_id}</strong></td><td>{item.product_id ?? "—"}</td><td>{item.store_id ?? "—"}</td><td>{number(item.available_qty)}</td><td>{words(item.stock_status)}</td><td>{currency(item.final_recommended_price)}</td><td>{words(item.final_action)}</td></tr>)}</tbody>
          </table></div></div>
        </details>
      )}

      {performance && (
        <Section title="Model performance">
          <div className="metric-grid performance-metrics">
            <div><span>ROC AUC</span><strong>{number(performance.metrics.roc_auc)}</strong></div>
            <div><span>Average precision</span><strong>{number(performance.metrics.average_precision)}</strong></div>
            <div><span>Demand error</span><strong>{percentage(performance.metrics.demand_aggregate_error_pct)}</strong></div>
            <div><span>Revenue error</span><strong>{percentage(performance.metrics.revenue_aggregate_error_pct)}</strong></div>
          </div>
          {performance.business_interpretation.length > 0 && <ul className="business-points">{performance.business_interpretation.map((item) => <li key={item}>{item}</li>)}</ul>}
        </Section>
      )}

      {data.business_rule && (
        <Section title="Pricing rule">
          <dl className="detail-grid">
            <dt>Rule</dt><dd>{businessRule(data.business_rule.rule_name ?? data.business_rule.pricing_rule_id)}</dd>
            <dt>Allowed price</dt><dd>{currency(data.business_rule.min_price)} to {currency(data.business_rule.max_price)}</dd>
            <dt>Maximum price change</dt><dd>{percentage(data.business_rule.max_price_change_pct)}</dd>
            <dt>Decision status</dt><dd>{data.business_rule.final_price_compliant ? "Compliant" : "Manual review required"}</dd>
          </dl>
        </Section>
      )}

      {data.capabilities && (
        <Section title="Questions I can help with">
          <ul className="business-points">{data.capabilities.supported_questions.map((question) => <li key={question}>{question}</li>)}</ul>
        </Section>
      )}

      {hasBusinessData && <JsonViewer value={{
        question,
        answer: narrative,
        sources: response.tools_used.map((toolName) => ({
          name: words(toolName),
          status: response.tool_trace.find((entry) => entry.tool_name === toolName)?.status ?? "called",
          records: response.tool_trace.find((entry) => entry.tool_name === toolName)?.record_count ?? 0,
        })),
      }} />}
    </div>
  );
}
