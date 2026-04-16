import Search from "./Search";

export type GameSearchResult = {
    appid: number;
    name: string;
    image?: string | null;
};

export default function App() {
    return (
        <div className="app">
            <Search />
        </div>
    );
}
