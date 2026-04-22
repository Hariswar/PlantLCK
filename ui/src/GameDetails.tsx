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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
    const [error, setError] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);
    const isSearchRunning = Boolean(job && (job.status === "queued" || job.status === "running"));
    const hasCompletedSearch = Boolean(job && job.status === "completed");

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
                            <div className="filter-grid">
                                <label>
                                    Start date
                                    <input
                                        type="date"
                                        value={filters.dateFrom}
                                        onChange={(event) =>
                                            setFilters((current) => ({ ...current, dateFrom: event.target.value }))
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
                                            setFilters((current) => ({ ...current, dateTo: event.target.value }))
                                        }
                                        disabled={isSearchRunning}
                                    />
                                </label>
                                <label>
                                    Language
                                    <select
                                        value={filters.language}
                                        onChange={(event) =>
                                            setFilters((current) => ({ ...current, language: event.target.value }))
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
                                            setFilters((current) => ({ ...current, purchaseType: event.target.value }))
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
                                    <p>{job ? `${job.fetched_count} fetched, ${job.matched_count} matched` : null}</p>
                                </div>
                            ) : null}

                            {error ? <p className="error-text">{error}</p> : null}
                        </div>
                    ) : null}

                    {tab === "reviews" ? (
                        <div className="reviews-panel">
                            {reviews.length === 0 ? (
                                <p>Fetched reviews will appear here after the Steam download completes.</p>
                            ) : (
                                <div className="reviews-list">
                                    {reviews.map((review, index) => (
                                        <article key={`${review.recommendationid ?? index}`} className="review-card">
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
                            )}
                        </div>
                    ) : null}

                    {tab === "analysis" ? (
                        <div className="analysis-panel">
                            <h3>Analysis</h3>
                            <p>
                                NLP analysis is not implemented yet. This tab is reserved for the future Steam review
                                analysis output.
                            </p>
                        </div>
                    ) : null}
                </div>
            </section>
        </div>
    );
}
