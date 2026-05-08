import { useEffect, useState } from "react";
import type { GameSearchResult } from "./App";

type ReviewFilters = {
    dateFrom: string;
    dateTo: string;
    language: string;
    purchaseType: string;
    limit: number;
};

type ReviewItem = {
    recommendationid: string | number | null;
    steamid: string | number | null;
    playtime_forever_minutes: number | null;
    voted_up: boolean;
    votes_up: number | null;
    review_text: string;
    created_at: string | null;
    language: string | null;
    steam_purchase: boolean | null;
};

type ReviewJobStatus = {
    job_id: string;
    app_id: number;
    status: "queued" | "running" | "completed" | "failed";
    progress_percent: number;
    fetched_count: number;
    matched_count: number;
    total_requested: number;
    error: string | null;
};

type StartJobResponse = {
    job_id: string;
    status: ReviewJobStatus["status"];
};

type ResultResponse = {
    job_id: string;
    app_id: number;
    reviews: ReviewItem[];
    total_reviews: number;
    filters: ReviewFilters;
};

type SentimentRecord = {
    count: number;
    pct: number;
    weighted_pct: number;
};

type AspectRecord = {
    aspect: string;
    source: "predefined" | "bertopic";
    mention_count: number;
    sentiment: {
        positive: SentimentRecord;
        neutral: SentimentRecord;
        negative: SentimentRecord;
    };
    average_confidence: number;
    net_score: number;
    examples: {
        positive: string[];
        neutral: string[];
        negative: string[];
    };
    keywords?: string[];
    cluster_id?: number;
};

type AnalysisMetadata = {
    app_id: number;
    game_name: string;
    model: string;
    reviews_loaded: number;
    reviews_kept_after_english_filter: number;
    reviews_dropped_non_english_or_short: number;
    sentences_analyzed: number;
    predefined_pairs: number;
    discovered_pairs: number;
    discovered_topic_count: number;
    runtime_seconds?: number;
    bertopic_skipped?: boolean;
    error?: string;
};

type AnalysisReport = {
    metadata: AnalysisMetadata;
    predefined_aspects: AspectRecord[];
    discovered_topics: AspectRecord[];
};

type AnalysisJobStatus = {
    job_id: string;
    app_id: number;
    status: "queued" | "running" | "completed" | "failed";
    progress_percent: number;
    status_message: string;
    error: string | null;
};

type AnalysisStartResponse = {
    job_id: string;
    status: AnalysisJobStatus["status"];
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const NLP_BASE_URL = import.meta.env.VITE_NLP_BASE_URL ?? "http://localhost:8001";

const DEFAULT_FILTERS: ReviewFilters = {
    dateFrom: "",
    dateTo: "",
    language: "english",
    purchaseType: "all",
    limit: 500,
};

function formatReviewDate(value: string | null) {
    if (!value) {
        return "Unknown date";
    }

    const parsedDate = new Date(value);
    return Number.isNaN(parsedDate.getTime()) ? value : parsedDate.toLocaleString();
}

export default function GameDetails({ game, onBack }: { game: GameSearchResult; onBack: () => void }) {
    const [filters, setFilters] = useState<ReviewFilters>(DEFAULT_FILTERS);
    const [tab, setTab] = useState<"search" | "reviews" | "analysis">("search");
    const [job, setJob] = useState<ReviewJobStatus | null>(null);
    const [reviews, setReviews] = useState<ReviewItem[]>([]);
    const [analysisJob, setAnalysisJob] = useState<AnalysisJobStatus | null>(null);
    const [analysisReport, setAnalysisReport] = useState<AnalysisReport | null>(null);
    const [error, setError] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);
    const hasReviews = reviews.length > 0;
    const isSearchRunning = Boolean(job && (job.status === "queued" || job.status === "running"));
    const hasCompletedSearch = hasReviews || Boolean(job && job.status === "completed");
    const isAnalysisRunning = Boolean(
        analysisJob && (analysisJob.status === "queued" || analysisJob.status === "running"),
    );

    useEffect(() => {
        if (!job || (job.status !== "queued" && job.status !== "running")) {
            return undefined;
        }

        const intervalId = window.setInterval(async () => {
            try {
                const response = await fetch(`${API_BASE_URL}/reviews/jobs/${job.job_id}`);
                const payload = (await response.json()) as ReviewJobStatus | { detail?: string };

                if (!response.ok) {
                    const detail =
                        typeof payload === "object" &&
                        payload !== null &&
                        "detail" in payload &&
                        typeof payload.detail === "string"
                            ? payload.detail
                            : "Unable to fetch review progress.";
                    setError(detail);
                    setJob((current) => (current ? { ...current, status: "failed", error: detail } : current));
                    return;
                }

                const latestJob = payload as ReviewJobStatus;
                setJob(latestJob);

                if (latestJob.status === "completed") {
                    const resultResponse = await fetch(`${API_BASE_URL}/reviews/jobs/${job.job_id}/result`);
                    const resultPayload = (await resultResponse.json()) as ResultResponse | { detail?: string };

                    if (!resultResponse.ok) {
                        const detail =
                            typeof resultPayload === "object" &&
                            resultPayload !== null &&
                            "detail" in resultPayload &&
                            typeof resultPayload.detail === "string"
                                ? resultPayload.detail
                                : "Unable to load reviews.";
                        setError(detail);
                        setJob((current) => (current ? { ...current, status: "failed", error: detail } : current));
                        return;
                    }

                    const result = resultPayload as ResultResponse;
                    setReviews(result.reviews);
                    setTab("reviews");
                }

                if (latestJob.status === "failed") {
                    setError(latestJob.error ?? "Review fetch failed.");
                }
            } catch {
                setError("Unable to reach backend while checking progress.");
                setJob((current) =>
                    current ? { ...current, status: "failed", error: "Progress polling failed." } : current,
                );
            }
        }, 1500);

        return () => window.clearInterval(intervalId);
    }, [job]);

    useEffect(() => {
        if (!analysisJob || (analysisJob.status !== "queued" && analysisJob.status !== "running")) {
            return undefined;
        }

        const intervalId = window.setInterval(async () => {
            try {
                const response = await fetch(`${NLP_BASE_URL}/analyze/${analysisJob.job_id}`);
                const payload = (await response.json()) as AnalysisJobStatus | { detail?: string };

                if (!response.ok) {
                    const detail =
                        typeof payload === "object" &&
                        payload !== null &&
                        "detail" in payload &&
                        typeof payload.detail === "string"
                            ? payload.detail
                            : "Unable to fetch analysis progress.";
                    setError(detail);
                    setAnalysisJob((current) => (current ? { ...current, status: "failed", error: detail } : current));
                    return;
                }

                const latestJob = payload as AnalysisJobStatus;
                setAnalysisJob(latestJob);

                if (latestJob.status === "completed") {
                    const resultResponse = await fetch(`${NLP_BASE_URL}/analyze/${analysisJob.job_id}/result`);
                    const resultPayload = (await resultResponse.json()) as AnalysisReport | { detail?: string };

                    if (!resultResponse.ok) {
                        const detail =
                            typeof resultPayload === "object" &&
                            resultPayload !== null &&
                            "detail" in resultPayload &&
                            typeof resultPayload.detail === "string"
                                ? resultPayload.detail
                                : "Unable to load analysis results.";
                        setError(detail);
                        setAnalysisJob((current) =>
                            current ? { ...current, status: "failed", error: detail } : current,
                        );
                        return;
                    }

                    const result = resultPayload as AnalysisReport;
                    setAnalysisReport(result);
                }

                if (latestJob.status === "failed") {
                    setError(latestJob.error ?? "Analysis failed.");
                }
            } catch {
                setError("Unable to reach backend while checking analysis progress.");
                setAnalysisJob((current) =>
                    current ? { ...current, status: "failed", error: "Progress polling failed." } : current,
                );
            }
        }, 1500);

        return () => window.clearInterval(intervalId);
    }, [analysisJob]);

    const startAnalysis = async () => {
        setError("");
        setAnalysisReport(null);

        try {
            // If we have fetched reviews already, post them directly to the NLP service
            const response = await fetch(`${NLP_BASE_URL}/analyze`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    app_id: game.appid,
                    reviews: reviews,
                }),
            });

            const payload = (await response.json()) as AnalysisStartResponse | { detail?: string };
            if (!response.ok) {
                const detail =
                    typeof payload === "object" &&
                    payload !== null &&
                    "detail" in payload &&
                    typeof payload.detail === "string"
                        ? payload.detail
                        : "Unable to start analysis.";
                setError(detail);
                return;
            }

            const startedJob = payload as AnalysisStartResponse;
            setAnalysisJob({
                job_id: startedJob.job_id,
                app_id: game.appid,
                status: startedJob.status,
                progress_percent: 0,
                status_message: "Queued",
                error: null,
            });
        } catch {
            setError("Unable to reach backend to start analysis.");
        }
    };

    const startReviewFetch = async () => {
        if (filters.dateFrom && filters.dateTo && filters.dateFrom > filters.dateTo) {
            setError("The start date must be on or before the end date.");
            return;
        }

        setIsSubmitting(true);
        setError("");
        setReviews([]);

        try {
            const response = await fetch(`${API_BASE_URL}/reviews/jobs`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    app_id: game.appid,
                    limit: filters.limit,
                    date_from: filters.dateFrom || null,
                    date_to: filters.dateTo || null,
                    language: filters.language,
                    purchase_type: filters.purchaseType,
                }),
            });

            const payload = (await response.json()) as StartJobResponse | { detail?: string };
            if (!response.ok) {
                const detail =
                    typeof payload === "object" &&
                    payload !== null &&
                    "detail" in payload &&
                    typeof payload.detail === "string"
                        ? payload.detail
                        : "Unable to start the review download.";
                setError(detail);
                return;
            }

            const startedJob = payload as StartJobResponse;
            setJob({
                job_id: startedJob.job_id,
                app_id: game.appid,
                status: startedJob.status,
                progress_percent: 0,
                fetched_count: 0,
                matched_count: 0,
                total_requested: filters.limit,
                error: null,
            });
            setTab("search");
        } catch {
            setError("Unable to reach backend to start the review download.");
        } finally {
            setIsSubmitting(false);
        }
    };

    const clearReviews = () => {
        setReviews([]);
        setJob(null);
        setAnalysisJob(null);
        setAnalysisReport(null);
        setError("");
        setTab("search");
    };

    return (
        <div className="game-details-shell">
            <aside className="game-sidebar">
                <button type="button" className="back-button" onClick={onBack}>
                    Back to search
                </button>
                {game.image ? <img src={game.image} alt={game.name} className="detail-cover" /> : null}
                <div className="game-meta">
                    <h1>{game.name}</h1>
                    <p>App ID: {game.appid}</p>
                </div>
            </aside>

            <section className="game-main">
                <div className="content-panel">
                    <div className="tabs" role="tablist" aria-label="Game detail tabs">
                        <button
                            type="button"
                            className={tab === "search" ? "tab active" : "tab"}
                            onClick={() => setTab("search")}
                        >
                            Search
                        </button>
                        <button
                            type="button"
                            className={tab === "reviews" ? "tab active" : "tab"}
                            onClick={() => setTab("reviews")}
                            disabled={!hasCompletedSearch}
                            aria-disabled={!hasCompletedSearch}
                        >
                            Reviews
                        </button>
                        <button
                            type="button"
                            className={tab === "analysis" ? "tab active" : "tab"}
                            onClick={() => setTab("analysis")}
                            disabled={!hasCompletedSearch}
                            aria-disabled={!hasCompletedSearch}
                        >
                            Analysis
                        </button>
                    </div>

                    {tab === "search" ? (
                        <div className="search-tab-panel">
                            {hasReviews ? (
                                <>
                                    <div className="search-locked-actions">
                                        <button type="button" className="secondary-button" onClick={clearReviews}>
                                            Clear Reviews
                                        </button>
                                    </div>

                                    <p>Reviews are already loaded — view them in the Reviews tab.</p>
                                </>
                            ) : (
                                <>
                                    <div className="filter-grid">
                                        <label>
                                            Start date
                                            <input
                                                type="date"
                                                value={filters.dateFrom}
                                                onChange={(event) =>
                                                    setFilters((current) => ({
                                                        ...current,
                                                        dateFrom: event.target.value,
                                                    }))
                                                }
                                                disabled={isSearchRunning}
                                            />
                                        </label>
                                        <label>
                                            End date
                                            <input
                                                type="date"
                                                value={filters.dateTo}
                                                onChange={(event) =>
                                                    setFilters((current) => ({
                                                        ...current,
                                                        dateTo: event.target.value,
                                                    }))
                                                }
                                                disabled={isSearchRunning}
                                            />
                                        </label>
                                        <label>
                                            Language
                                            <select
                                                value={filters.language}
                                                onChange={(event) =>
                                                    setFilters((current) => ({
                                                        ...current,
                                                        language: event.target.value,
                                                    }))
                                                }
                                                disabled={isSearchRunning}
                                            >
                                                <option value="english">English</option>
                                                <option value="all">All languages</option>
                                            </select>
                                        </label>
                                        <label>
                                            Purchase type
                                            <select
                                                value={filters.purchaseType}
                                                onChange={(event) =>
                                                    setFilters((current) => ({
                                                        ...current,
                                                        purchaseType: event.target.value,
                                                    }))
                                                }
                                                disabled={isSearchRunning}
                                            >
                                                <option value="all">All purchases</option>
                                                <option value="steam">Steam purchase</option>
                                                <option value="non_steam">Non-Steam purchase</option>
                                            </select>
                                        </label>
                                        <label>
                                            Max reviews
                                            <input
                                                type="number"
                                                min={1}
                                                step={1}
                                                value={filters.limit}
                                                onChange={(event) =>
                                                    setFilters((current) => ({
                                                        ...current,
                                                        limit: Number.parseInt(event.target.value, 10) || 1,
                                                    }))
                                                }
                                                disabled={isSearchRunning}
                                            />
                                        </label>
                                    </div>

                                    <button
                                        type="button"
                                        className="primary-button"
                                        onClick={() => void startReviewFetch()}
                                        disabled={isSubmitting || isSearchRunning}
                                    >
                                        {isSubmitting || isSearchRunning ? "Searching..." : "Fetch reviews"}
                                    </button>

                                    {isSearchRunning ? (
                                        <div className="progress-block" aria-live="polite">
                                            <div className="progress-row">
                                                <span>{job ? job.status : "idle"}</span>
                                                <span>{job ? `${Math.round(job.progress_percent)}%` : "0%"}</span>
                                            </div>
                                            <div className="progress-bar">
                                                <div
                                                    className="progress-bar-fill"
                                                    style={{
                                                        width: `${job ? Math.min(100, Math.max(0, job.progress_percent)) : 0}%`,
                                                    }}
                                                />
                                            </div>
                                            <p>
                                                {job
                                                    ? `${job.fetched_count} fetched, ${job.matched_count} matched`
                                                    : null}
                                            </p>
                                        </div>
                                    ) : null}

                                    {error ? <p className="error-text">{error}</p> : null}
                                </>
                            )}
                        </div>
                    ) : null}

                    {tab === "reviews" ? (
                        <div className="reviews-panel">
                            {reviews.length === 0 ? (
                                <p>
                                    {hasCompletedSearch && (filters.dateFrom || filters.dateTo)
                                        ? "No reviews matched the selected date range. Try widening the date filter or increasing the review limit."
                                        : hasCompletedSearch
                                          ? "No reviews matched the selected filters. Try adjusting the filters and fetching again."
                                          : "Fetched reviews will appear here after the Steam download completes."}
                                </p>
                            ) : (
                                <>
                                    <div className="search-locked-actions">
                                        <button type="button" className="secondary-button" onClick={clearReviews}>
                                            Clear Reviews
                                        </button>
                                    </div>
                                    <div className="reviews-list">
                                        {reviews.map((review, index) => (
                                            <article
                                                key={`${review.recommendationid ?? index}`}
                                                className="review-card"
                                            >
                                                <p className="review-text">
                                                    {review.review_text || "No review text available."}
                                                </p>
                                                <div className="review-meta review-meta-data">
                                                    <span>{review.voted_up ? "Recommended" : "Not recommended"}</span>
                                                    <span>Playtime: {review.playtime_forever_minutes ?? 0} min</span>
                                                    <span>Helpful votes: {review.votes_up ?? 0}</span>
                                                    <span>Language: {review.language ?? "unknown"}</span>
                                                    <span>{formatReviewDate(review.created_at)}</span>
                                                </div>
                                            </article>
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>
                    ) : null}

                    {tab === "analysis" ? (
                        <div className="analysis-panel">
                            {!analysisReport && !isAnalysisRunning ? (
                                <div className="analysis-start-section">
                                    <h3>Sentiment Analysis</h3>
                                    <p>
                                        Analyze the fetched reviews to extract aspect-based sentiment using advanced
                                        NLP. This will identify what aspects of the game players are discussing and
                                        their sentiment towards each.
                                    </p>
                                    <button
                                        type="button"
                                        className="primary-button"
                                        onClick={() => void startAnalysis()}
                                        disabled={!hasCompletedSearch}
                                    >
                                        Start Analysis
                                    </button>
                                    {!hasCompletedSearch && (
                                        <p className="error-text">
                                            Please fetch reviews first before running analysis.
                                        </p>
                                    )}
                                </div>
                            ) : null}

                            {isAnalysisRunning ? (
                                <div className="progress-block" aria-live="polite">
                                    <h3>Analysis in Progress</h3>
                                    <div className="progress-row">
                                        <span>{analysisJob?.status}</span>
                                        <span>
                                            {analysisJob ? `${Math.round(analysisJob.progress_percent)}%` : "0%"}
                                        </span>
                                    </div>
                                    <div className="progress-bar">
                                        <div
                                            className="progress-bar-fill"
                                            style={{
                                                width: `${analysisJob ? Math.min(100, Math.max(0, analysisJob.progress_percent)) : 0}%`,
                                            }}
                                        />
                                    </div>
                                    <p>{analysisJob?.status_message || "Processing..."}</p>
                                </div>
                            ) : null}

                            {analysisReport && (
                                <div className="analysis-results">
                                    <h3>Sentiment Analysis Results</h3>

                                    <div className="analysis-metadata">
                                        <h4>Analysis Summary</h4>
                                        <div className="metadata-grid">
                                            <div>
                                                <strong>Reviews Analyzed:</strong>
                                                <p>{analysisReport.metadata.reviews_loaded}</p>
                                            </div>
                                            <div>
                                                <strong>After English Filter:</strong>
                                                <p>{analysisReport.metadata.reviews_kept_after_english_filter}</p>
                                            </div>
                                            <div>
                                                <strong>Sentences Analyzed:</strong>
                                                <p>{analysisReport.metadata.sentences_analyzed}</p>
                                            </div>
                                            <div>
                                                <strong>Aspect Mentions:</strong>
                                                <p>{analysisReport.metadata.predefined_pairs}</p>
                                            </div>
                                            <div>
                                                <strong>Topics Discovered:</strong>
                                                <p>{analysisReport.metadata.discovered_topic_count}</p>
                                            </div>
                                            <div>
                                                <strong>Model:</strong>
                                                <p className="model-name">
                                                    {analysisReport.metadata.model.split("/")[1]}
                                                </p>
                                            </div>
                                        </div>
                                    </div>

                                    {analysisReport.predefined_aspects.length > 0 && (
                                        <div className="aspects-section">
                                            <h4>Key Game Aspects</h4>
                                            <div className="aspects-list">
                                                {analysisReport.predefined_aspects.map((aspect) => (
                                                    <AspectCard key={aspect.aspect} aspect={aspect} />
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {analysisReport.discovered_topics.length > 0 && (
                                        <div className="topics-section">
                                            <h4>Discovered Topics</h4>
                                            <p className="section-description">
                                                These topics were discovered by analyzing patterns in the reviews and
                                                may represent emerging gameplay features, bugs, or community
                                                discussions.
                                            </p>
                                            <div className="topics-list">
                                                {analysisReport.discovered_topics.map((topic) => (
                                                    <TopicCard key={topic.cluster_id ?? topic.aspect} topic={topic} />
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    <button
                                        type="button"
                                        className="secondary-button"
                                        onClick={() => {
                                            setAnalysisReport(null);
                                            setAnalysisJob(null);
                                        }}
                                    >
                                        Clear Results
                                    </button>
                                </div>
                            )}

                            {error && analysisJob?.status === "failed" ? <p className="error-text">{error}</p> : null}
                        </div>
                    ) : null}
                </div>
            </section>
        </div>
    );
}

function AspectCard({ aspect }: { aspect: AspectRecord }) {
    const sentiment = aspect.sentiment;
    const totalMentions = sentiment.positive.count + sentiment.neutral.count + sentiment.negative.count;
    const positivePercent = totalMentions > 0 ? (sentiment.positive.weighted_pct / 100) * 100 : 0;
    const neutralPercent = totalMentions > 0 ? (sentiment.neutral.weighted_pct / 100) * 100 : 0;
    const negativePercent = totalMentions > 0 ? (sentiment.negative.weighted_pct / 100) * 100 : 0;

    return (
        <div className="aspect-card">
            <div className="aspect-header">
                <h5>{aspect.aspect}</h5>
                <div className="aspect-meta">
                    <span className="mention-count">{aspect.mention_count} mentions</span>
                    <span className="confidence">Confidence: {(aspect.average_confidence * 100).toFixed(1)}%</span>
                    <span
                        className={`net-score ${aspect.net_score > 0 ? "positive" : aspect.net_score < 0 ? "negative" : "neutral"}`}
                    >
                        Score: {aspect.net_score.toFixed(2)}
                    </span>
                </div>
            </div>

            <div className="sentiment-bar">
                <div
                    className="bar-segment positive"
                    style={{ width: `${positivePercent}%` }}
                    title={`Positive: ${sentiment.positive.weighted_pct.toFixed(1)}%`}
                />
                <div
                    className="bar-segment neutral"
                    style={{ width: `${neutralPercent}%` }}
                    title={`Neutral: ${sentiment.neutral.weighted_pct.toFixed(1)}%`}
                />
                <div
                    className="bar-segment negative"
                    style={{ width: `${negativePercent}%` }}
                    title={`Negative: ${sentiment.negative.weighted_pct.toFixed(1)}%`}
                />
            </div>

            <div className="sentiment-breakdown">
                <span className="sentiment positive">
                    <strong>Positive:</strong> {sentiment.positive.weighted_pct.toFixed(1)}%
                </span>
                <span className="sentiment neutral">
                    <strong>Neutral:</strong> {sentiment.neutral.weighted_pct.toFixed(1)}%
                </span>
                <span className="sentiment negative">
                    <strong>Negative:</strong> {sentiment.negative.weighted_pct.toFixed(1)}%
                </span>
            </div>

            {aspect.examples && (
                <div className="examples">
                    {aspect.examples.positive.length > 0 && (
                        <div className="example-group positive">
                            <strong>Positive examples:</strong>
                            <ul>
                                {aspect.examples.positive.map((ex, idx) => (
                                    <li key={idx}>{ex}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {aspect.examples.negative.length > 0 && (
                        <div className="example-group negative">
                            <strong>Negative examples:</strong>
                            <ul>
                                {aspect.examples.negative.map((ex, idx) => (
                                    <li key={idx}>{ex}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function TopicCard({ topic }: { topic: AspectRecord }) {
    const sentiment = topic.sentiment;
    const totalMentions = sentiment.positive.count + sentiment.neutral.count + sentiment.negative.count;
    const positivePercent = totalMentions > 0 ? (sentiment.positive.weighted_pct / 100) * 100 : 0;
    const neutralPercent = totalMentions > 0 ? (sentiment.neutral.weighted_pct / 100) * 100 : 0;
    const negativePercent = totalMentions > 0 ? (sentiment.negative.weighted_pct / 100) * 100 : 0;

    return (
        <div className="topic-card">
            <div className="topic-header">
                <h5>{topic.aspect}</h5>
                {topic.keywords && topic.keywords.length > 0 && (
                    <div className="keywords">
                        {topic.keywords.map((kw) => (
                            <span key={kw} className="keyword-tag">
                                {kw}
                            </span>
                        ))}
                    </div>
                )}
                <div className="topic-meta">
                    <span className="mention-count">{topic.mention_count} mentions</span>
                    <span className="confidence">Confidence: {(topic.average_confidence * 100).toFixed(1)}%</span>
                    <span
                        className={`net-score ${topic.net_score > 0 ? "positive" : topic.net_score < 0 ? "negative" : "neutral"}`}
                    >
                        Score: {topic.net_score.toFixed(2)}
                    </span>
                </div>
            </div>

            <div className="sentiment-bar">
                <div
                    className="bar-segment positive"
                    style={{ width: `${positivePercent}%` }}
                    title={`Positive: ${sentiment.positive.weighted_pct.toFixed(1)}%`}
                />
                <div
                    className="bar-segment neutral"
                    style={{ width: `${neutralPercent}%` }}
                    title={`Neutral: ${sentiment.neutral.weighted_pct.toFixed(1)}%`}
                />
                <div
                    className="bar-segment negative"
                    style={{ width: `${negativePercent}%` }}
                    title={`Negative: ${sentiment.negative.weighted_pct.toFixed(1)}%`}
                />
            </div>

            <div className="sentiment-breakdown">
                <span className="sentiment positive">
                    <strong>Positive:</strong> {sentiment.positive.weighted_pct.toFixed(1)}%
                </span>
                <span className="sentiment neutral">
                    <strong>Neutral:</strong> {sentiment.neutral.weighted_pct.toFixed(1)}%
                </span>
                <span className="sentiment negative">
                    <strong>Negative:</strong> {sentiment.negative.weighted_pct.toFixed(1)}%
                </span>
            </div>

            {topic.examples && (
                <div className="examples">
                    {topic.examples.positive.length > 0 && (
                        <div className="example-group positive">
                            <strong>Positive examples:</strong>
                            <ul>
                                {topic.examples.positive.map((ex, idx) => (
                                    <li key={idx}>{ex}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {topic.examples.negative.length > 0 && (
                        <div className="example-group negative">
                            <strong>Negative examples:</strong>
                            <ul>
                                {topic.examples.negative.map((ex, idx) => (
                                    <li key={idx}>{ex}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
