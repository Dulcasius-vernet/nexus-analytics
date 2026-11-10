"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  BarChart, Bar, PieChart, Pie, Cell, Legend,
} from "recharts";

type PageName = "overview" | "data" | "analysis" | "models" | "reports" | "workspace";
type User = { user_id: number; full_name: string; email: string; business_id: number; role: string };
type Overview = { transaction_count: number; transaction_value: number; average_transaction_value: number; labelled_fraud_count: number; labelled_fraud_rate_pct: number; customer_count: number; agent_count: number };
type Transaction = { transaction_id: number; transaction_ts: string; transaction_type: string; amount: number | string; channel: string | null; is_fraud: boolean };
type Quality = { total_records: number; missing_customer_id: number; missing_agent_id: number; duplicate_transaction_ids: number; invalid_amount: number; invalid_timestamp: number; invalid_hour: number; missing_channel: number; inconsistent_channel_format: number; inconsistent_customer_references: number; inconsistent_agent_references: number };
type TypeSummary = { transaction_type: string; transaction_count: number; total_value: number | string; average_value: number | string };
type ChannelSummary = { channel: string; transaction_count: number; transaction_value: number | string; fraud_count: number };
type Trend = { period_start: string; transaction_count: number; fraud_count: number; fraud_rate_pct: number | string };
type ModelMetrics = { roc_auc: number; average_precision: number; baseline_roc_auc: number; baseline_average_precision: number; threshold: number; threshold_metrics?: { precision: number; recall: number; f1: number; predicted_positive_rate_pct: number }; note: string; top_feature_importances: [string, number][] };
type Workspace = { workspace_id: number; workspace_name: string; description: string | null; created_at: string };
type Report = { title: string; generated_at: string; summary: { transactions: number; transaction_value: number | string; average_transaction: number | string; labelled_fraud: number; high_failed_attempts: number }; notes: string[] };
type AIReport = { title: string; generated_at: string; narrative: string; disclaimer: string };

const emptyOverview: Overview = { transaction_count: 0, transaction_value: 0, average_transaction_value: 0, labelled_fraud_count: 0, labelled_fraud_rate_pct: 0, customer_count: 0, agent_count: 0 };
const nav: [PageName, string][] = [["overview", "Overview"], ["data", "Data management"], ["analysis", "SQL analytics"], ["models", "Machine learning"], ["reports", "AI reports"], ["workspace", "Workspace"]];
const palette = ["#70a5ff", "#5bd6ad", "#eab76b", "#b49aff", "#f28d9b", "#7dd3e8"];

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend${path}`, { ...init, credentials: "same-origin", headers: { ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(init?.headers || {}) } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body as T;
}
function money(value: number | string) { return new Intl.NumberFormat("en-GH", { style: "currency", currency: "GHS", maximumFractionDigits: 0 }).format(Number(value || 0)); }
function readable(value: string) { return value.replace(/\\n/g, "\n").replace(/\\"/g, '"').trim(); }

function AuthScreen({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
  const [mode, setMode] = useState<"register" | "login">("register");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ full_name: "", email: "", password: "", business_name: "", industry: "Financial Services", workspace_name: "Transaction Risk Workspace", objective_type: "fraud-risk" });
  const update = (key: keyof typeof form, value: string) => setForm((old) => ({ ...old, [key]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const user = await api<User>(mode === "register" ? "/auth/register" : "/auth/login", { method: "POST", body: JSON.stringify(mode === "register" ? form : { email: form.email, password: form.password }) });
      onAuthenticated(user);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to authenticate"); }
    finally { setBusy(false); }
  }
  return <main className="auth-shell"><section className="auth-card"><div className="brand auth-brand"><span className="brand-mark">N</span><div><strong>NEXUS</strong><small>ANALYTICS</small></div></div><p className="eyebrow">AI-AUGMENTED BUSINESS INTELLIGENCE</p><h1>{mode === "register" ? "Create your workspace" : "Welcome back"}</h1><p className="subhead">Connect business data, evaluate predictive models and turn analytical results into decisions.</p><div className="auth-tabs"><button className={mode === "register" ? "selected" : ""} onClick={() => { setMode("register"); setError(""); }}>Create account</button><button className={mode === "login" ? "selected" : ""} onClick={() => { setMode("login"); setError(""); }}>Sign in</button></div><form className="auth-form" onSubmit={submit}>
    {mode === "register" && <><label>Full name<input required minLength={2} value={form.full_name} onChange={(e) => update("full_name", e.target.value)} placeholder="Your full name" /></label><label>Business name<input required minLength={2} value={form.business_name} onChange={(e) => update("business_name", e.target.value)} placeholder="Organisation name" /></label><label>Industry<select value={form.industry} onChange={(e) => update("industry", e.target.value)}><option>Financial Services</option><option>Retail</option><option>Telecommunications</option><option>Healthcare</option><option>Logistics</option><option>Other</option></select></label><label>Workspace name<input required value={form.workspace_name} onChange={(e) => update("workspace_name", e.target.value)} /></label><label>Initial business objective<select value={form.objective_type} onChange={(e) => update("objective_type", e.target.value)}><option value="fraud-risk">Fraud and risk prediction</option><option value="sales-forecasting">Sales forecasting</option><option value="lead-scoring">Lead scoring</option><option value="demand-forecasting">Demand forecasting</option><option value="customer-segmentation">Customer segmentation</option><option value="anomaly-detection">Anomaly detection</option><option value="other">Other analytical objective</option></select></label></>}
    <label>Email address<input type="email" required autoComplete="email" value={form.email} onChange={(e) => update("email", e.target.value)} placeholder="name@company.com" /></label><label>Password<input type="password" required minLength={mode === "register" ? 10 : 1} autoComplete={mode === "register" ? "new-password" : "current-password"} value={form.password} onChange={(e) => update("password", e.target.value)} placeholder={mode === "register" ? "At least 10 characters" : "Your password"} /></label>
    {error && <div className="notice">{error}</div>}<button className="button primary wide" disabled={busy}>{busy ? "Please wait…" : mode === "register" ? "Create business workspace" : "Sign in securely"}</button></form><p className="auth-foot">Your workspace is private to your account. Use synthetic or authorised business data only.</p></section></main>;
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [page, setPage] = useState<PageName>("overview");
  const [overview, setOverview] = useState<Overview>(emptyOverview);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [types, setTypes] = useState<TypeSummary[]>([]);
  const [channels, setChannels] = useState<ChannelSummary[]>([]);
  const [trends, setTrends] = useState<Trend[]>([]);
  const [metrics, setMetrics] = useState<ModelMetrics | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [aiReport, setAiReport] = useState<AIReport | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [uploadMessage, setUploadMessage] = useState("");
  const [question, setQuestion] = useState("Prepare an executive summary of transaction activity and risk patterns.");
  const [asking, setAsking] = useState(false);
  const [prediction, setPrediction] = useState({ amount: "250", hour_of_day: "22", device_age_days: "3", failed_attempts_24h: "2", customer_tenure_days: "12", transaction_type: "transfer", channel: "APP" });
  const [predictionResult, setPredictionResult] = useState<any>(null);
  const [newWorkspace, setNewWorkspace] = useState("");
  const [workspaceMessage, setWorkspaceMessage] = useState("");

  useEffect(() => { api<User>("/auth/me").then(setUser).catch(() => setUser(null)).finally(() => setAuthLoading(false)); }, []);

  const loadOverview = useCallback(async () => {
    if (!user) return;
    const [o, t, c, tr] = await Promise.all([
      api<Overview>("/analytics/overview"), api<TypeSummary[]>("/analytics/transaction-types"),
      api<ChannelSummary[]>("/analytics/channels"), api<Trend[]>("/analytics/fraud-trends"),
    ]);
    setOverview({ transaction_count: Number(o.transaction_count), transaction_value: Number(o.transaction_value), average_transaction_value: Number(o.average_transaction_value), labelled_fraud_count: Number(o.labelled_fraud_count), labelled_fraud_rate_pct: Number(o.labelled_fraud_rate_pct), customer_count: Number(o.customer_count), agent_count: Number(o.agent_count) });
    setTypes(t); setChannels(c); setTrends(tr);
  }, [user]);

  const loadPage = useCallback(async (target: PageName) => {
    if (!user) return;
    setPage(target); setLoading(true); setError("");
    try {
      if (target === "overview" || target === "analysis") await loadOverview();
      if (target === "data") {
        const [tx, q] = await Promise.all([api<{ items: Transaction[] }>("/analytics/transactions?page=1&page_size=30"), api<Quality>("/data-quality")]);
        setTransactions(tx.items); setQuality(q);
      }
      if (target === "models") setMetrics(await api<ModelMetrics>("/models/metrics"));
      if (target === "reports") setReport(await api<Report>("/reports/latest"));
      if (target === "workspace") setWorkspaces(await api<Workspace[]>("/workspaces"));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load this section"); }
    finally { setLoading(false); }
  }, [user, loadOverview]);

  useEffect(() => { if (user) loadPage("overview"); }, [user, loadPage]);

  async function uploadFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; if (!file) return;
    const form = new FormData(); form.append("file", file); setUploadMessage("Uploading and validating CSV…");
    try { const result = await api<{ row_count: number; dataset_name: string }>("/datasets/upload", { method: "POST", body: form }); setUploadMessage(`Loaded ${result.row_count.toLocaleString()} rows from ${result.dataset_name}.`); await loadPage("data"); await loadOverview(); }
    catch (reason) { setUploadMessage(reason instanceof Error ? reason.message : "Upload failed"); }
    event.target.value = "";
  }

  async function loadDemo() {
    setUploadMessage("Loading 30,000 synthetic transactions…");
    try { const result = await api<{ row_count: number; message: string }>("/datasets/demo", { method: "POST", body: JSON.stringify({}) }); setUploadMessage(`${result.message} (${result.row_count.toLocaleString()} records).`); await loadPage("data"); await loadOverview(); }
    catch (reason) { setUploadMessage(reason instanceof Error ? reason.message : "Could not load sample data"); }
  }

  async function runPrediction(event: FormEvent) {
    event.preventDefault(); setPredictionResult(null); setAsking(true);
    try {
      const row = { amount: Number(prediction.amount), hour_of_day: Number(prediction.hour_of_day), device_age_days: prediction.device_age_days === "" ? null : Number(prediction.device_age_days), failed_attempts_24h: Number(prediction.failed_attempts_24h), customer_tenure_days: prediction.customer_tenure_days === "" ? null : Number(prediction.customer_tenure_days), transaction_type: prediction.transaction_type, channel: prediction.channel || null };
      const result = await api<any>("/models/predict", { method: "POST", body: JSON.stringify({ transactions: [row] }) }); setPredictionResult(result.results[0]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Prediction failed"); }
    finally { setAsking(false); }
  }

  async function generateAIReport(event: FormEvent) {
    event.preventDefault(); setAsking(true); setAiReport(null); setError("");
    try { setAiReport(await api<AIReport>("/reports/ai", { method: "POST", body: JSON.stringify({ question }) })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "AI report failed"); }
    finally { setAsking(false); }
  }

  async function downloadPDF() {
    setAsking(true); setError("");
    try {
      const response = await fetch("/api/backend/reports/ai.pdf", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
      if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || "PDF generation failed"); }
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = "nexus-analytics-ai-report.pdf"; link.click(); URL.revokeObjectURL(url);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "PDF generation failed"); }
    finally { setAsking(false); }
  }

  async function createWorkspace(event: FormEvent) {
    event.preventDefault(); setWorkspaceMessage("");
    try { await api<Workspace>("/workspaces", { method: "POST", body: JSON.stringify({ workspace_name: newWorkspace, description: "Created from the Nexus Analytics workspace" }) }); setNewWorkspace(""); setWorkspaceMessage("Workspace created."); setWorkspaces(await api<Workspace[]>("/workspaces")); }
    catch (reason) { setWorkspaceMessage(reason instanceof Error ? reason.message : "Could not create workspace"); }
  }

  async function signOut() { await api("/auth/logout", { method: "POST", body: JSON.stringify({}) }).catch(() => undefined); setUser(null); setPage("overview"); }

  const trendData = useMemo(() => trends.map((item) => ({ ...item, period: new Date(item.period_start).toLocaleDateString("en-GH", { day: "numeric", month: "short" }), fraud_rate_pct: Number(item.fraud_rate_pct) })), [trends]);
  const typeData = useMemo(() => types.map((item) => ({ name: item.transaction_type.replaceAll("_", " "), transactions: item.transaction_count, value: Number(item.total_value) })), [types]);
  const metricsCards = [
    ["Transactions", overview.transaction_count.toLocaleString(), "Records in this workspace"],
    ["Transaction value", money(overview.transaction_value), "Aggregate value · GHS"],
    ["Labelled fraud", overview.labelled_fraud_count.toLocaleString(), `${overview.labelled_fraud_rate_pct.toFixed(2)}% of labelled records`],
    ["Customers", overview.customer_count.toLocaleString(), `${overview.agent_count.toLocaleString()} associated agents`],
  ];

  if (authLoading) return <main className="auth-shell"><div className="auth-loading">Loading secure workspace…</div></main>;
  if (!user) return <AuthScreen onAuthenticated={(value) => setUser(value)} />;

  return <main className="app-shell"><aside className="sidebar"><div className="brand"><span className="brand-mark">N</span><div><strong>NEXUS</strong><small>ANALYTICS</small></div></div><div className="workspace-label">BUSINESS WORKSPACE</div><nav>{nav.map(([name, label]) => <button key={name} className={page === name ? "active" : ""} onClick={() => loadPage(name)}>{label}</button>)}</nav><div className="sidebar-foot"><span className="status-dot" /> Signed in<br/><small>{user.email}</small><button className="signout" onClick={signOut}>Sign out</button></div></aside>
    <section className="content"><header><div><p className="eyebrow">{user.business_id ? `BUSINESS ID ${user.business_id}` : "BUSINESS WORKSPACE"}</p><h1>{nav.find(([key]) => key === page)?.[1]}</h1><p className="subhead">Operational analytics, predictive risk and AI-assisted decision support.</p></div><div className="user-chip">{user.full_name}<span>{user.role}</span></div></header>
    <div className="context-banner"><div><strong>Workspace overview</strong><p>{user.business_id} · {user.email} · Synthetic mobile-money demonstration available</p></div><button className="button small" onClick={() => loadPage(page)}>Refresh</button></div>
    {error && <div className="notice">{error}</div>}
    {page === "overview" && <>
      <div className="metric-grid">{metricsCards.map(([label, value, note]) => <article className="metric" key={label}><p>{label}</p><strong>{value}</strong><small>{note}</small></article>)}</div>
      {overview.transaction_count === 0 && <div className="empty-banner"><div><strong>Your workspace is ready. No dataset has been loaded yet.</strong><p>Load the bundled synthetic dataset to explore the full analytics and model workflow, or upload your own compatible transaction CSV.</p></div><button className="button primary" onClick={loadDemo}>Load 30,000 sample records</button></div>}
      <div className="chart-grid"><section className="page-panel"><h2>Weekly transaction and labelled-fraud trend</h2><p className="subhead">Weekly volume from PostgreSQL aggregates.</p><div className="chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={trendData}><CartesianGrid strokeDasharray="3 3" stroke="#26334c"/><XAxis dataKey="period" stroke="#91a0b8"/><YAxis stroke="#91a0b8"/><Tooltip contentStyle={{ background: "#111a2e", border: "1px solid #26334c", color: "#e8edf7" }}/><Legend/><Line type="monotone" dataKey="transaction_count" name="Transactions" stroke="#70a5ff" strokeWidth={2} dot={false}/><Line type="monotone" dataKey="fraud_count" name="Labelled fraud" stroke="#eab76b" strokeWidth={2} dot={false}/></LineChart></ResponsiveContainer></div></section><section className="page-panel"><h2>Transaction types</h2><p className="subhead">Transaction volume by type.</p><div className="chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={typeData} layout="vertical" margin={{ left: 12, right: 12 }}><CartesianGrid strokeDasharray="3 3" stroke="#26334c"/><XAxis type="number" stroke="#91a0b8"/><YAxis type="category" dataKey="name" width={100} stroke="#91a0b8"/><Tooltip contentStyle={{ background: "#111a2e", border: "1px solid #26334c", color: "#e8edf7" }}/><Bar dataKey="transactions" fill="#70a5ff" radius={[0, 4, 4, 0]}/></BarChart></ResponsiveContainer></div></section></div>
      <div className="section-heading"><div><h2>Analytics workflow</h2><p>Move from source data to business decisions.</p></div></div><div className="module-grid">{nav.slice(1).map(([key, label], index) => <button className="module" key={key} onClick={() => loadPage(key)}><span className="module-index">0{index + 1}</span><h3>{label}</h3><p>{["Inspect source records and data quality.", "Explore SQL aggregations and patterns.", "Evaluate and run predictive models.", "Generate management insights and reports.", "Manage workspaces and objectives."][index]}</p><span className="module-state">Open module</span></button>)}</div>
    </>}
    {page === "data" && <section className="page-panel"><h2>Dataset management</h2><p className="subhead">Upload a CSV matching the transaction schema or load the bundled reproducible sample dataset.</p><div className="action-row"><label className="upload-button">Upload transaction CSV<input type="file" accept=".csv,text/csv" onChange={uploadFile}/></label><button className="button" onClick={loadDemo}>Load synthetic demo dataset</button></div>{uploadMessage && <p className="upload-message">{uploadMessage}</p>}{quality && <div className="quality-grid"><strong>{quality.total_records.toLocaleString()}<small>records</small></strong><strong>{quality.missing_customer_id}<small>missing customer IDs</small></strong><strong>{quality.duplicate_transaction_ids}<small>duplicate IDs</small></strong><strong>{quality.invalid_amount}<small>invalid amounts</small></strong><strong>{quality.inconsistent_channel_format}<small>channel format issues</small></strong><strong>{quality.inconsistent_customer_references + quality.inconsistent_agent_references}<small>reference issues</small></strong></div>}<div className="table-wrap">{loading ? "Loading data…" : <table><thead><tr><th>Transaction ID</th><th>Timestamp</th><th>Type</th><th>Amount</th><th>Channel</th><th>Label</th></tr></thead><tbody>{transactions.map((item) => <tr key={item.transaction_id}><td>{item.transaction_id}</td><td>{new Date(item.transaction_ts).toLocaleString()}</td><td>{item.transaction_type.replaceAll("_", " ")}</td><td>{money(item.amount)}</td><td>{item.channel || "—"}</td><td><span className={item.is_fraud ? "pill risk" : "pill"}>{item.is_fraud ? "Labelled fraud" : "Normal"}</span></td></tr>)}</tbody></table>}</div></section>}
    {page === "analysis" && <><div className="chart-grid"><section className="page-panel"><h2>Transaction type analysis</h2><p className="subhead">SQL aggregation of transaction volume and value.</p><div className="chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={typeData}><CartesianGrid strokeDasharray="3 3" stroke="#26334c"/><XAxis dataKey="name" stroke="#91a0b8"/><YAxis stroke="#91a0b8"/><Tooltip contentStyle={{ background: "#111a2e", border: "1px solid #26334c", color: "#e8edf7" }}/><Bar dataKey="value" name="Transaction value (GHS)" fill="#5bd6ad" radius={[5, 5, 0, 0]}/></BarChart></ResponsiveContainer></div></section><section className="page-panel"><h2>Channel distribution</h2><p className="subhead">Transaction count by channel.</p><div className="chart"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={channels.map((c) => ({ name: c.channel, value: c.transaction_count }))} dataKey="value" nameKey="name" outerRadius={95} label>{channels.map((entry, index) => <Cell key={entry.channel} fill={palette[index % palette.length]}/>)}</Pie><Tooltip/><Legend/></PieChart></ResponsiveContainer></div></section></div><section className="page-panel"><h2>SQL result summary</h2><div className="table-wrap"><table><thead><tr><th>Transaction type</th><th>Count</th><th>Total value</th><th>Average value</th></tr></thead><tbody>{types.map((item) => <tr key={item.transaction_type}><td>{item.transaction_type}</td><td>{item.transaction_count.toLocaleString()}</td><td>{money(item.total_value)}</td><td>{money(item.average_value)}</td></tr>)}</tbody></table></div></section></>}
    {page === "models" && <><section className="page-panel"><h2>Fraud-risk model evaluation</h2><p className="subhead">Metrics are loaded from the reproducible Scikit-learn training run.</p>{metrics ? <><div className="metric-grid"><article className="metric"><p>ROC AUC</p><strong>{metrics.roc_auc.toFixed(3)}</strong><small>Dummy baseline: {metrics.baseline_roc_auc.toFixed(3)}</small></article><article className="metric"><p>Average precision</p><strong>{metrics.average_precision.toFixed(3)}</strong><small>Dummy baseline: {metrics.baseline_average_precision.toFixed(3)}</small></article><article className="metric"><p>Selected threshold</p><strong>{metrics.threshold.toFixed(3)}</strong><small>Holdout F1 optimisation</small></article><article className="metric"><p>Holdout recall</p><strong>{((metrics.threshold_metrics?.recall || 0) * 100).toFixed(1)}%</strong><small>Precision {(100 * (metrics.threshold_metrics?.precision || 0)).toFixed(1)}%</small></article></div><h3>Most influential features</h3><div className="table-wrap"><table><thead><tr><th>Feature</th><th>Importance</th></tr></thead><tbody>{metrics.top_feature_importances.slice(0, 8).map(([feature, value]) => <tr key={feature}><td>{feature.replaceAll("_", " ")}</td><td>{(value * 100).toFixed(2)}%</td></tr>)}</tbody></table></div><p className="subhead">{metrics.note}</p></> : <p>{loading ? "Loading model metrics…" : "Model metrics are unavailable. Train the model first."}</p>}</section><section className="page-panel"><h2>Run a transaction-risk prediction</h2><p className="subhead">Enter a hypothetical transaction. The model returns a score and review flag; it does not make a fraud determination.</p><form className="prediction-form" onSubmit={runPrediction}>{([ ["amount", "Amount (GHS)"], ["hour_of_day", "Hour of day (0–23)"], ["device_age_days", "Device age (days)"], ["failed_attempts_24h", "Failed attempts (24h)"], ["customer_tenure_days", "Customer tenure (days)"] ] as [keyof typeof prediction, string][]).map(([key, label]) => <label key={key}>{label}<input type="number" min="0" step={key === "amount" ? "0.01" : "1"} value={prediction[key]} onChange={(e) => setPrediction((old) => ({ ...old, [key]: e.target.value }))} required={key !== "device_age_days" && key !== "customer_tenure_days"}/></label>)}<label>Transaction type<select value={prediction.transaction_type} onChange={(e) => setPrediction((old) => ({ ...old, transaction_type: e.target.value }))}><option value="transfer">Transfer</option><option value="cash_out">Cash out</option><option value="cash_in">Cash in</option><option value="bill_payment">Bill payment</option><option value="merchant_payment">Merchant payment</option></select></label><label>Channel<select value={prediction.channel} onChange={(e) => setPrediction((old) => ({ ...old, channel: e.target.value }))}><option>APP</option><option>USSD</option><option>AGENT</option></select></label><button className="button primary" disabled={asking}>Score transaction</button></form>{predictionResult && <div className="prediction-result"><span className="eyebrow">MODEL OUTPUT</span><strong>{(predictionResult.risk_score * 100).toFixed(2)}% risk score</strong><p>Risk band: <b>{predictionResult.risk_band}</b> · {predictionResult.flagged_for_review ? "Flagged for human review" : "Below review threshold"}</p><small>{predictionResult.recommendation}</small></div>}</section><p className="disclaimer">Synthetic demonstration only. The model has limited discrimination and scores are not calibrated probabilities. Never use this output as a standalone basis for blocking a customer or transaction.</p></>}
    {page === "reports" && <><section className="page-panel"><h2>Business performance snapshot</h2><p className="subhead">Database-backed indicators for this business workspace.</p>{report && <><p className="report-date">Generated {new Date(report.generated_at).toLocaleString()}</p><div className="quality-grid"><strong>{report.summary.transactions.toLocaleString()}<small>transactions</small></strong><strong>{money(report.summary.transaction_value)}<small>transaction value</small></strong><strong>{report.summary.labelled_fraud.toLocaleString()}<small>labelled fraud records</small></strong><strong>{report.summary.high_failed_attempts.toLocaleString()}<small>2+ failed attempts</small></strong></div><ul className="report-notes">{report.notes.map((note) => <li key={note}>{note}</li>)}</ul></>}</section><section className="page-panel"><h2>Generate an AI management report</h2><p className="subhead">Snwolley receives aggregate database findings and model evaluation context, not individual customer records.</p><form className="report-form" onSubmit={generateAIReport}><textarea value={question} onChange={(e) => setQuestion(e.target.value)} minLength={8} maxLength={2000} rows={3}/><div className="action-row"><button className="button primary" disabled={asking}>{asking ? "Generating…" : "Generate AI report"}</button><button className="button" type="button" disabled={asking} onClick={downloadPDF}>Generate PDF report</button></div></form>{aiReport && <article className="ai-report"><p className="report-date">{new Date(aiReport.generated_at).toLocaleString()}</p><h3>{aiReport.title}</h3>{readable(aiReport.narrative).split("\n").map((line, index) => line.trim() ? <p key={index}>{line}</p> : <div className="answer-gap" key={index}/>)}<small>{aiReport.disclaimer}</small></article>}</section></>}
    {page === "workspace" && <section className="page-panel"><h2>Business workspace</h2><p className="subhead">Your account is scoped to business ID {user.business_id}. Workspaces are isolated by business membership.</p><form className="workspace-form" onSubmit={createWorkspace}><label>New workspace name<input required minLength={2} value={newWorkspace} onChange={(e) => setNewWorkspace(e.target.value)} placeholder="e.g. Sales Forecasting"/></label><button className="button primary">Create workspace</button></form>{workspaceMessage && <p className="upload-message">{workspaceMessage}</p>}<div className="workspace-list">{workspaces.map((workspace) => <article key={workspace.workspace_id}><strong>{workspace.workspace_name}</strong><p>{workspace.description || "No description provided"}</p><small>Workspace #{workspace.workspace_id} · {new Date(workspace.created_at).toLocaleDateString()}</small></article>)}</div></section>}
    <footer>NEXUS ANALYTICS <span>Secure business workspace · v0.2.0</span></footer></section></main>;
}
