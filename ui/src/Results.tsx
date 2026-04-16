import type { GameSearchResult } from "./App";

type ResultsProps = {
    results: GameSearchResult[];
};

export default function Results({ results }: ResultsProps) {
    return (
        <div className="results">
            {results.length === 0 ? (
                <p>No games found.</p>
            ) : (
                <div className="results-list">
                    {results.map((game) => (
                        <article key={game.appid} className="result-card">
                            {game.image ? <img src={game.image} alt={game.name} className="result-image" /> : null}
                            <div>
                                <p>{game.name}</p>
                                <p>App ID: {game.appid}</p>
                            </div>
                        </article>
                    ))}
                </div>
            )}
        </div>
    );
}
