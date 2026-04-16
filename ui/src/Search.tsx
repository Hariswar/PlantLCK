import { useState } from "react";
import SearchIcon from "./assets/icons/search.svg?react";
import type { GameSearchResult } from "./App";
import Results from "./Results";

type SearchResponse = {
    query: string;
    results: GameSearchResult[];
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export default function Search() {
    const [query, setQuery] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [message, setMessage] = useState("");
    const [results, setResults] = useState<GameSearchResult[]>([]);
    const [hasSearched, setHasSearched] = useState(false);

    const runSearch = async () => {
        const trimmed = query.trim();
        if (!trimmed) {
            setResults([]);
            setHasSearched(false);
            setMessage("");
            return;
        }

        setIsLoading(true);
        setMessage("");

        try {
            const response = await fetch(`${API_BASE_URL}/search?query=${encodeURIComponent(trimmed)}`);
            const payload = (await response.json()) as SearchResponse | { detail?: string };

            if (!response.ok) {
                const errorDetail =
                    typeof payload === "object" &&
                    payload !== null &&
                    "detail" in payload &&
                    typeof payload.detail === "string"
                        ? payload.detail
                        : "Search failed.";

                setMessage(errorDetail);
                setHasSearched(true);
                setResults([]);
                return;
            }

            const searchPayload = payload as SearchResponse;
            setResults(searchPayload.results);
            setHasSearched(true);
        } catch {
            setMessage("Unable to reach backend. Please check if API is running.");
            setHasSearched(true);
            setResults([]);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="search">
            <div className="search-content">
                <div className="search-input">
                    <input
                        type="text"
                        placeholder="Search for a game or enter a 6-digit ID..."
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === "Enter") {
                                void runSearch();
                            }
                        }}
                        disabled={isLoading}
                    />
                    <button
                        type="button"
                        onClick={() => void runSearch()}
                        className="search-icon-button"
                        disabled={isLoading}
                        aria-label="Search"
                    >
                        {isLoading ? (
                            <div className="loading-spinner" aria-hidden="true" />
                        ) : (
                            <SearchIcon className="search-icon" aria-hidden="true" />
                        )}
                    </button>
                </div>
                {message && <p>{message}</p>}

                {hasSearched ? <Results results={results} /> : null}
            </div>
        </div>
    );
}
